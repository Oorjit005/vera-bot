"""Gemini-backed writer. Uses the plain REST API via urllib (no extra
dependency) so the bot's dependency list stays at fastapi/uvicorn/pytest."""
import asyncio
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from app import config

GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

BODY_SCHEMA = {
    "type": "OBJECT",
    "properties": {"body": {"type": "STRING"}, "rationale": {"type": "STRING"}},
    "required": ["body", "rationale"],
}

SYSTEM_PROMPT = """You write ONE WhatsApp message for Vera, magicpin's merchant-growth assistant in India.
You receive a BRIEF (JSON). The decision is already made; your job is wording only.

HARD RULES
1. Use ONLY facts in BRIEF.facts_text / why_now / evidence / merchant_anchor / judgment / offer / slot_options.
   Every number, date, price, name and source you write must appear there. Never add a statistic,
   competitor, study, price, time, or customer count that is not in the brief.
2. Open with BRIEF.salutation (merchant) or the greeting + sender_line (customer). No preamble,
   no "hope you're well", never introduce yourself or say "Vera here".
3. 2-4 sentences, 200-420 characters for merchants, 180-380 for customers.
4. Structure: why-now fact -> supporting evidence/judgment -> what I'll do (deliverable) -> ONE call to action.
   The call to action is the LAST sentence and matches BRIEF.cta:
   binary_yes_stop -> ends with a clear "Reply YES" style ask; open_ended -> ends with BRIEF.cta_question;
   multi_choice_slot -> list BRIEF.slot_options then "or tell us a time that works";
   binary_confirm_cancel -> ends with "Reply CONFIRM"; none -> no ask.
5. Voice: BRIEF.tone. Use 1-2 terms from BRIEF.vocab_hint naturally when they fit. Never use any word in BRIEF.taboo.
   Peer-to-peer, specific, zero hype, no exclamation-mark spam, no ALL CAPS words except YES/CONFIRM/STOP.
6. Language = BRIEF.language:
   "en" -> English. "en+hi_cta" -> English body, final CTA sentence in natural Roman-script Hinglish
   (feminine first person: "kar dungi"). "hinglish" -> natural Roman-script Hindi-English mix throughout.
   "hindi" -> mostly Roman-script Hindi, respectful ("ji"). "en:ta"/"en:te"/"en:kn" -> English, greeting as given.
7. If BRIEF.offer_is_suggestion is true, present the offer as a suggestion ("want me to list ..."), never as
   something the merchant already runs. If BRIEF.source_citation is set, cite it verbatim once.
8. No URLs, no hashtags, no markdown, no bullet lists unless BRIEF.kind is active_planning_intent
   (then up to 4 short lines starting with "- " are allowed). Emoji: only if present in sender_line.
9. rationale: one sentence (<=240 chars) naming the trigger, the key fact used, and the lever.
Return JSON {"body": "...", "rationale": "..."} only."""

REPLY_SYSTEM_PROMPT = """You are replying inside an ongoing WhatsApp conversation for Vera, magicpin's
merchant-growth assistant in India. EXTRA tells you the reply mode:
- "action": the merchant said yes. Confirm you are doing EXTRA.deliverable NOW. Start with "Done" or "On it".
  Include the word "next" and state the concrete next step. End with "Reply CONFIRM to proceed."
  NEVER ask a question; never use: "would you", "do you", "can you tell", "what if", "how about".
- "answer": answer EXTRA.question using only facts you are given; if the answer is not available say
  "I'll confirm that and get back to you here" - then restate the outstanding call to action as the last sentence.
- "offtopic": say the topic is best handled by EXTRA.referral (e.g. "your CA"), it's outside what you can do here,
  then bring it back to EXTRA.why_now in one line and end with a call to action.
80-380 characters. No URLs, no markdown, no preamble, never re-introduce yourself.
Do not repeat any sentence from EXTRA.previous_bot_messages. Do not greet again.
Return JSON {"body": "...", "rationale": "..."} only."""

_CACHE: dict = {}
_calls_made = 0
_usage_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "llm_usage.jsonl")


def reset_writer_state():
    global _calls_made
    _CACHE.clear()
    _calls_made = 0


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_cached(brief):
    key = _cache_key(brief.canonical() + config.PROMPT_VERSION)
    return _CACHE.get(key)


def _log_usage(kind: str, usage: dict):
    try:
        os.makedirs(os.path.dirname(_usage_log_path), exist_ok=True)
        with open(_usage_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, "ts": time.time(), **usage}) + "\n")
    except Exception:
        pass


def _call_gemini_sync(system_text: str, user_text: str, schema: dict, timeout_s: float):
    if not config.GEMINI_API_KEY:
        return None
    url = GEMINI_URL_TMPL.format(model=config.WRITER_MODEL, key=config.GEMINI_API_KEY)
    body = {
        "system_instruction": {"parts": [{"text": system_text}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "maxOutputTokens": 1024,
            # Gemini 3.x models "think" by default, which eats maxOutputTokens
            # before the actual JSON is written and truncates the response.
            # The decision logic already lives in the deterministic Brief, so
            # the writer only needs to phrase it - no reasoning budget needed.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    except Exception:
        return None

    try:
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts") or []
        text = next((p.get("text") for p in parts if p.get("text")), None)
        if not text:
            return None
        out = json.loads(text)
        usage = data.get("usageMetadata", {})
        return out, usage
    except Exception:
        return None


async def write(brief, extra_rules: str = ""):
    global _calls_made
    if not config.LLM_ENABLED or _calls_made >= config.LLM_MAX_CALLS:
        return None
    key = _cache_key(brief.canonical() + config.PROMPT_VERSION + extra_rules)
    if key in _CACHE:
        return _CACHE[key]

    user_text = "BRIEF:\n" + brief.canonical()
    if extra_rules:
        user_text += "\n\nFIX THESE PROBLEMS FROM YOUR LAST DRAFT:\n" + extra_rules

    result = await asyncio.to_thread(_call_gemini_sync, SYSTEM_PROMPT, user_text, BODY_SCHEMA, config.LLM_TIMEOUT_S)
    if result is None:
        return None
    out, usage = result
    _calls_made += 1
    _log_usage("write", usage)
    _CACHE[key] = out
    return out


async def write_reply(conv, reply_mode: str, extra: dict):
    global _calls_made
    if not config.LLM_ENABLED or _calls_made >= config.LLM_MAX_CALLS:
        return None
    payload = {
        "reply_mode": reply_mode, "language": conv.language, "deliverable": conv.deliverable,
        **{k: v for k, v in extra.items() if k != "previous_bot_messages"},
        "previous_bot_messages": (extra.get("previous_bot_messages") or [])[-3:],
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    key = _cache_key("reply:" + canonical + config.PROMPT_VERSION)
    if key in _CACHE:
        return _CACHE[key]

    user_text = "EXTRA:\n" + canonical
    result = await asyncio.to_thread(
        _call_gemini_sync, REPLY_SYSTEM_PROMPT, user_text, BODY_SCHEMA, config.LLM_TIMEOUT_S
    )
    if result is None:
        return None
    out, usage = result
    _calls_made += 1
    _log_usage("write_reply", usage)
    _CACHE[key] = out
    return out
