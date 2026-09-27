from app.playbook._shared import common_fields, make_brief

ASK_TEMPLATE_QUESTIONS = {
    "what_service_in_demand_this_week": "What service has been most asked-for this week?",
}


def build_curious_ask_due(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    ask_template = payload.get("ask_template")
    if ask_template and ask_template in ASK_TEMPLATE_QUESTIONS:
        question = ASK_TEMPLATE_QUESTIONS[ask_template]
    elif ask_template:
        question = ask_template.replace("_", " ").capitalize() + "?"
    else:
        question = "What's been in most demand this week?"
    why_now = question

    trend = facts.trend_top()
    evidence = (
        [f"'{trend['query']}' up {facts.fmt_pct(trend.get('delta_yoy'))} YoY"]
        if trend and trend.get("query") else []
    )

    active = facts.active_offers()
    anchor = active[0] if active else None

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor,
        judgment="one easy question, and I'll turn the answer into something useful for you",
        offer=None, offer_is_suggestion=False,
        deliverable="a Google post and a ready WhatsApp price reply",
        cta="open_ended", cta_question=question,
        levers=["asking_merchant", "reciprocity"], facts_text=facts_text,
    )


def build_active_planning_intent(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    intent_topic = payload.get("intent_topic") or "plan"
    topic_plain = intent_topic.replace("_", " ")
    why_now = f"here's a first draft of the {topic_plain}"

    active = facts.active_offers()
    offer = active[0] if active else None

    # SPEC-GAP: the golden example (PLAN §13, T01) sketches a multi-tier priced
    # package with named buildings; we only draft from real active offers and
    # catalog titles (never invented tiers/prices/buildings) per the "never
    # fabricate" rule, which is the more conservative reading of "a concrete
    # draft built only from active offers, catalog prices and digest numbers".
    draft_lines = []
    if offer:
        draft_lines.append(f"built around your active '{offer}' offer")
    catalog = category.get("offer_catalog", []) or []
    for item in catalog[:2]:
        title = item.get("title")
        if title and title != offer:
            draft_lines.append(f"can also fold in '{title}' from your catalog")
    if not draft_lines:
        draft_lines.append(f"a simple {topic_plain} outline, ready for your review")

    evidence = draft_lines
    anchor = facts.locality()

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor,
        judgment="delivering the draft now since you already said yes",
        offer=offer, offer_is_suggestion=False,
        deliverable="the outreach message to go with it",
        cta="binary_yes_stop", levers=["effort_externalization", "momentum"], facts_text=facts_text,
    )
