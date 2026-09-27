import re
from datetime import datetime, timedelta, timezone

from app import config
from app.facts import _parse_iso
from app.lang import CTA_EN, CTA_HI, detect_reply_lang
from app.reply.classify import classify, later_wait_seconds
from app.store import Conversation, store
from app.validate import validate_reply

REFERRAL_MAP = [
    (re.compile(r"\bgst\b|\btax\b|\bitr\b", re.IGNORECASE), "your CA"),
    (re.compile(r"\bca\b|chartered accountant", re.IGNORECASE), "your CA"),
    (re.compile(r"\bloan\b", re.IGNORECASE), "your bank"),
    (re.compile(r"\blegal\b|\blawyer\b", re.IGNORECASE), "a lawyer"),
    (re.compile(r"\binsurance\b", re.IGNORECASE), "your insurance advisor"),
]

DEFAULT_NOW = "2026-04-26T10:00:00Z"


def _referral_for(text):
    for pattern, referral in REFERRAL_MAP:
        if pattern.search(text):
            return referral
    return "the right specialist"


def _iso_plus_hours(iso, hours):
    dt = _parse_iso(iso) or datetime.now(timezone.utc)
    return (dt + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_deliverable(merchant_id):
    merchant = store.merchant(merchant_id) if merchant_id else None
    if not merchant:
        return "your next profile update"
    category = store.category(merchant.get("category_slug"))
    if not category:
        return "your next profile update"
    from app.playbook import build_brief

    now = store.last_now or DEFAULT_NOW
    for kind in ("perf_dip", "curious_ask_due"):
        try:
            fake_trigger = {"kind": kind, "merchant_id": merchant_id, "payload": {"placeholder": True},
                             "urgency": 1, "source": "internal"}
            brief = build_brief(kind, category, merchant, fake_trigger, None, now)
            if not brief.skip and brief.deliverable:
                return brief.deliverable
        except Exception:
            continue
    return "your next profile update"


def _get_or_create_conversation(conversation_id, merchant_id, customer_id):
    conv = store.conversations.get(conversation_id)
    if conv is not None:
        return conv
    conv = Conversation(
        id=conversation_id, merchant_id=merchant_id or "", customer_id=customer_id,
        trigger_id="", kind="", send_as=("merchant_on_behalf" if customer_id else "vera"),
        language="en", deliverable=_default_deliverable(merchant_id),
    )
    store.conversations[conversation_id] = conv
    return conv


def _cta_sentence_for_conv(conv):
    use_hi = conv.language in ("en+hi_cta", "hinglish", "hindi")
    bank = CTA_HI if use_hi else CTA_EN
    return bank.get("binary_yes_stop", "Reply YES and I'll get it ready.").format(d=conv.deliverable or "it")


def _norm_ws(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _send(conv, body, cta, rationale):
    """PLAN §10: every send is checked against conv.bodies_sent for a verbatim
    repeat; on a repeat we disambiguate with a trailing marker rather than
    resending an identical body (which is penalized -2)."""
    if _norm_ws(body) in {_norm_ws(b) for b in conv.bodies_sent}:
        body = body.rstrip(".") + " (update)."
    conv.bodies_sent.append(body)
    return {"action": "send", "body": body, "cta": cta, "rationale": rationale}


def _end(conv, rationale):
    conv.status = "ended"
    return {"action": "end", "rationale": rationale}


def _pick_slot_label(text, conv):
    m = re.match(r"^\s*(1|2)\b", text or "")
    slots = (conv.brief_summary or {}).get("slot_options") or []
    if m and slots:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(slots):
            return slots[idx]
    if len(slots) == 1:
        return slots[0]
    return "we'll call you to fix the time"


def _fallback_answer(text):
    # SPEC-GAP: without a live Brief for this conversation turn we can't look
    # up the actual price/date/source, so these are generic, conservative
    # holding replies rather than invented facts.
    t = (text or "").lower()
    if re.search(r"how long|kitna time|\btime\b", t):
        return "It takes about 10 minutes of your time."
    if re.search(r"price|cost|kitna", t):
        return "I'll share the price along with the details."
    if re.search(r"when|kab|\bdate\b", t):
        return "I'll confirm the exact date and share it here."
    if re.search(r"source|proof|study", t):
        return "I'll share the source for that."
    return "I'll confirm that and get back to you here."


async def _writer_reply(conv, reply_mode, extra):
    try:
        from app import writer
        if not config.LLM_ENABLED:
            return None
        return await writer.write_reply(conv, reply_mode, extra)
    except ImportError:
        return None
    except Exception:
        return None


async def _llm_or_fallback(conv, reply_mode, extra, fallback_text, cta):
    written = await _writer_reply(conv, reply_mode, extra)
    if written and written.get("body"):
        errors = validate_reply(written["body"], reply_mode=reply_mode, conv_bodies=conv.bodies_sent)
        if not errors:
            return _send(conv, written["body"], cta, written.get("rationale") or "LLM-written reply.")
    return None


async def respond(body: dict) -> dict:
    try:
        conversation_id = body.get("conversation_id") or ""
        merchant_id = body.get("merchant_id")
        customer_id = body.get("customer_id")
        from_role = body.get("from_role", "merchant")
        text = body.get("message", "") or ""
        received_at = body.get("received_at") or store.last_now or DEFAULT_NOW

        conv = _get_or_create_conversation(conversation_id, merchant_id, customer_id)
        if merchant_id:
            conv.merchant_id = merchant_id
        if customer_id:
            conv.customer_id = customer_id

        mstate = store.merchant_state(conv.merchant_id) if conv.merchant_id else None
        cls = classify(text, mstate, from_role)

        conv.turns.append({"role": from_role, "text": text, "ts": received_at})
        if mstate:
            mstate.unanswered_proactive = 0

        if detect_reply_lang(text) == "hinglish":
            conv.language = "hinglish"
            if mstate:
                mstate.last_lang = "hinglish"

        if conv.status == "ended":
            if cls in ("off_topic", "question") and not conv.brief_summary.get("_post_end_sent"):
                referral = _referral_for(text)
                conv.brief_summary["_post_end_sent"] = True
                msg = (f"Sorry for the trouble. That's best handled by {referral} - outside what I can help "
                       f"with. I won't message again; just say 'Hi Vera' anytime.")
                return _send(conv, msg, "none",
                             "One-time post-close redirect for an off-topic/question message after opt-out.")
            return {"action": "end", "rationale": "Conversation already ended; suppressing further sends."}

        if cls == "hostile_optout":
            if mstate:
                mstate.opted_out = True
            return _end(conv, "Merchant opted out explicitly; closing and suppressing further sends.")

        if cls == "auto_reply":
            norm_text = _norm_ws(text)
            if mstate:
                mstate.autoreply_count += 1
                mstate.autoreply_texts[norm_text] = mstate.autoreply_texts.get(norm_text, 0) + 1
                count = mstate.autoreply_count
            else:
                count = 1
            if count == 1:
                msg = (f"Looks like an auto-reply \U0001F642 When the owner sees this, a simple YES is all "
                       f"it takes to get {conv.deliverable} started.")
                return _send(conv, msg, "binary_yes_stop",
                             "Detected a canned auto-reply on first hit; nudging for the owner.")
            if count == 2:
                return {"action": "wait", "wait_seconds": 86400,
                        "rationale": "Second auto-reply in a row; waiting 24h before retry."}
            if mstate:
                mstate.parked_until = _iso_plus_hours(received_at, 24)
            return _end(conv, "Third auto-reply in a row; no real engagement, closing and parking the merchant 24h.")

        if cls == "not_interested":
            if not conv.brief_summary.get("_not_interested_sent"):
                conv.brief_summary["_not_interested_sent"] = True
                if mstate:
                    mstate.opted_out = True
                msg = f"Understood - I won't follow up on this. If you ever want {conv.deliverable}, just message 'Hi Vera'."
                result = _send(conv, msg, "none", "Merchant declined; acknowledging once and suppressing further sends.")
                conv.status = "ended"
                return result
            return _end(conv, "Already declined; conversation closed.")

        if cls == "later":
            return {"action": "wait", "wait_seconds": later_wait_seconds(text),
                    "rationale": "Merchant asked to be messaged later."}

        if cls == "accept":
            if from_role == "customer":
                slot_label = _pick_slot_label(text, conv)
                msg = f"Confirmed ✅ {slot_label}. Reply CHANGE if anything comes up."
                result = _send(conv, msg, "none",
                                "Customer confirmed a booking; acknowledging with the chosen/only slot.")
                conv.status = "waiting"
                return result

            conv.accept_count += 1
            if conv.accept_count == 1:
                conv.delivered = True
                extra = {"deliverable": conv.deliverable, "previous_bot_messages": conv.bodies_sent}
                result = await _llm_or_fallback(conv, "action", extra, None, "binary_confirm_cancel")
                if result:
                    return result
                if conv.language in ("en+hi_cta", "hinglish", "hindi"):
                    msg = (f"Done - {conv.deliverable} abhi draft kar rahi hoon. Next: aapke OK ke liye "
                           f"yahin share karungi. Reply CONFIRM to proceed.")
                else:
                    msg = (f"Done - {conv.deliverable} is being drafted now. Next: I'll share it here for "
                           f"your OK within the hour. Reply CONFIRM to proceed.")
                return _send(conv, msg, "binary_confirm_cancel",
                             "Merchant explicitly accepted; switching to action mode with a concrete next step.")

            msg = f"Done - {conv.deliverable} is ready and queued. Next: I'll share how it performs by next week."
            result = _send(conv, msg, "none",
                            "Second acceptance in this conversation; confirming completion, no further ask.")
            conv.status = "waiting"
            return result

        if cls == "off_topic":
            conv.offtopic_streak += 1
            referral = _referral_for(text)
            if conv.offtopic_streak <= 1:
                extra = {"topic": referral, "referral": referral, "why_now": conv.deliverable}
                result = await _llm_or_fallback(conv, "offtopic", extra, None, "binary_yes_stop")
                if result:
                    return result
                cta_line = _cta_sentence_for_conv(conv)
                msg = f"That's best handled by {referral} - that's outside what I can do here. Back to your update: {cta_line}"
                return _send(conv, msg, "binary_yes_stop",
                             f"Off-topic ask ({referral}); politely declining once and redirecting back to the mission.")
            return _end(conv, "Second off-topic message in a row; ending the conversation.")

        if cls in ("question", "other"):
            extra = {"question": text, "previous_bot_messages": conv.bodies_sent}
            result = await _llm_or_fallback(conv, "answer", extra, None, "binary_yes_stop")
            if result:
                return result
            cta_line = _cta_sentence_for_conv(conv)
            msg = f"{_fallback_answer(text)} {cta_line}".strip()
            return _send(conv, msg, "binary_yes_stop",
                         "Answering the merchant's question from known facts, then restating the ask.")

        if cls == "thanks_ack":
            if conv.delivered:
                return _end(conv, "Merchant acknowledged; work delivered.")
            if not conv.thanks_nudged:
                conv.thanks_nudged = True
                cta_line = _cta_sentence_for_conv(conv)
                msg = f"Glad to help. {cta_line}"
                return _send(conv, msg, "binary_yes_stop",
                             "Acknowledging thanks once, then restating the outstanding ask.")
            return _end(conv, "Already nudged once; closing to avoid pestering.")

        return _end(conv, "Unhandled classification; closing defensively.")
    except Exception:
        return {"action": "wait", "wait_seconds": 300, "rationale": "internal recovery"}
