from app.brief import Brief

ALIASES = {
    "research_digest_release": "research_digest",
    "category_research_digest_release": "research_digest",
    "recall_reminder": "recall_due",
    "bridal_followup": "wedding_package_followup",
    "customer_winback": "customer_lapsed_hard",
    "appointment_reminder": "appointment_tomorrow",
    "unplanned_slot_open": "recall_due",
    "category_trend_movement": "curious_ask_due",
    "compliance_update": "regulation_change",
    "new_competitor": "competitor_opened",
}

GLOBAL_TABOO = {"guaranteed", "miracle", "best in city", "100% safe", "completely cure", "cure"}

EMOJI_BY_CATEGORY = {
    "dentists": "\U0001f9b7", "salons": "✨", "restaurants": "\U0001f37d️",
    "gyms": "\U0001f4aa", "pharmacies": "\U0001f48a",
}

CUSTOMER_KINDS = {
    "recall_due", "appointment_tomorrow", "chronic_refill_due", "customer_lapsed_soft",
    "customer_lapsed_hard", "trial_followup", "wedding_package_followup",
}


def is_placeholder(trigger, primary_keys):
    payload = (trigger or {}).get("payload", {}) or {}
    if payload.get("placeholder") is True:
        return True
    if not primary_keys:
        return False
    for k in primary_keys:
        if payload.get(k) in (None, "", [], {}):
            return True
    return False


def common_fields(kind, facts, category, merchant, trigger, customer, audience):
    from app import lang as lang_mod

    category = category or {}
    merchant = merchant or {}
    trigger = trigger or {}
    voice = category.get("voice", {}) or {}
    taboo = sorted(set(voice.get("vocab_taboo", []) or []) | GLOBAL_TABOO)
    vocab_allowed = voice.get("vocab_allowed", []) or []
    tone_parts = [p for p in [voice.get("tone"), voice.get("register")] if p]
    tone = " ".join(tone_parts)
    urgency_raw = trigger.get("urgency", 1)
    urgency = urgency_raw if isinstance(urgency_raw, int) and not isinstance(urgency_raw, bool) else 1
    source = trigger.get("source", "") or ""
    suppression_key = trigger.get("suppression_key") or (
        f"{kind}:{merchant.get('merchant_id', '')}:{(customer or {}).get('customer_id', '') if customer else ''}"
    )

    if audience == "merchant":
        language = lang_mod.merchant_lang(merchant, category)
        salutation = facts.salutation() or "there"
        sender_line = None
    else:
        result = lang_mod.customer_lang(customer)
        greet_key = result[1] if isinstance(result, tuple) else result
        language = f"en:{greet_key}" if isinstance(result, tuple) else result
        name = ((customer or {}).get("identity", {}) or {}).get("name") or "there"
        salutation = lang_mod.greeting_for(customer, greet_key, name)
        full_name = facts.merchant_name()
        emoji = EMOJI_BY_CATEGORY.get(category.get("slug"), "")
        sender_line = (f"{full_name} here" + (f" {emoji}" if emoji else "")) if full_name else None

    return {
        "language": language, "salutation": salutation, "sender_line": sender_line,
        "taboo": taboo, "tone": tone, "vocab_hint": vocab_allowed[:4],
        "urgency": urgency, "source": source, "suppression_key": suppression_key,
    }


def make_brief(kind, audience, send_as, common, trigger, merchant, customer, **kw):
    trigger = trigger or {}
    return Brief(
        kind=kind, audience=audience, send_as=send_as,
        language=common["language"], salutation=common["salutation"], sender_line=common.get("sender_line"),
        why_now=kw.get("why_now", "") or "", evidence=kw.get("evidence") or [],
        merchant_anchor=kw.get("merchant_anchor"), judgment=kw.get("judgment"),
        offer=kw.get("offer"), offer_is_suggestion=bool(kw.get("offer_is_suggestion", False)),
        deliverable=kw.get("deliverable", "") or "", cta=kw.get("cta", "none"),
        cta_question=kw.get("cta_question"), slot_options=kw.get("slot_options") or [],
        levers=kw.get("levers") or [], source_citation=kw.get("source_citation"),
        vocab_hint=common.get("vocab_hint") or [], taboo=common.get("taboo") or [], tone=common.get("tone", ""),
        facts_text=[t for t in (kw.get("facts_text") or []) if t], skip=kw.get("skip"),
        trigger_id=trigger.get("id", ""), merchant_id=(merchant or {}).get("merchant_id", ""),
        customer_id=(customer or {}).get("customer_id") if customer else None,
        suppression_key=common.get("suppression_key", ""), urgency=common.get("urgency", 1),
        source=common.get("source", ""),
    )


def make_skip(kind, audience, send_as, common, trigger, merchant, customer, reason):
    return make_brief(kind, audience, send_as, common, trigger, merchant, customer, skip=reason)


def degrade_to(target_kind, original_kind, facts, category, merchant, trigger, customer, common):
    """PLAN §6.1: when a placeholder trigger has no usable signal, build the
    degrade target's Brief instead, keeping the original trigger_id/suppression_key."""
    from app.playbook import conversation

    builders = {"curious_ask_due": conversation.build_curious_ask_due}
    builder = builders.get(target_kind)
    if builder is None:
        return make_skip(original_kind, "merchant", "vera", common, trigger, merchant, customer,
                          f"no_degrade_target:{target_kind}")
    brief = builder(target_kind, facts, category, merchant, trigger, customer)
    brief.trigger_id = (trigger or {}).get("id", brief.trigger_id)
    brief.suppression_key = common.get("suppression_key", brief.suppression_key)
    return brief
