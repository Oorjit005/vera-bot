from app.playbook._shared import common_fields, degrade_to, is_placeholder, make_brief, make_skip

MILESTONE_STEPS = [100, 250, 500, 1000, 1500, 2000, 2500, 3000, 5000]


def build_perf_dip(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["metric", "delta_pct"])

    if not placeholder:
        metric = payload.get("metric")
        delta_pct = payload.get("delta_pct")
        vs_baseline = payload.get("vs_baseline")
        pct_str = facts.fmt_pct(delta_pct) if delta_pct is not None else ""
        why_now = f"{facts.plain(metric)} down {pct_str.lstrip('-')} this week"
        if vs_baseline is not None:
            why_now += f" (baseline {vs_baseline})"
    else:
        neg = facts.strongest_negative()
        if not neg:
            return degrade_to("curious_ask_due", kind, facts, category, merchant, trigger, customer, common)
        kind_of, metric, value = neg
        if kind_of == "delta":
            why_now = f"{facts.plain(metric)} down {facts.fmt_pct(value).lstrip('-')} vs last week"
        else:
            why_now = f"{value['mine']} {facts.plain(metric)} vs {value['peer']} peer average"

    stale = facts.signal("stale_posts")
    no_offers = facts.signal("no_active_offers")
    unverified = facts.signal("unverified_gbp")
    gap = facts.peer_gap(metric) if metric else None
    if stale and stale[1] is not None:
        cause = f"last Google post was {stale[1]} days ago"
    elif no_offers:
        cause = "no live offer on your profile"
    elif unverified:
        cause = "profile still unverified"
    elif gap:
        cause = f"{gap['mine']} {facts.plain(metric)} vs {gap['peer']} peer average"
    else:
        cause = ""
    evidence = [cause] if cause else []

    anchor = None
    if gap:
        anchor = f"{gap['mine']} {facts.plain(metric)} vs {gap['peer']} peer average"

    now_dt = facts.ref_now
    judgment = None
    if now_dt:
        beat = facts.seasonal_beat(now_dt.month)
        if beat and any(w in (beat.get("note", "").lower()) for w in ("lowest", "lull", "drop")):
            judgment = "this is the normal seasonal lull, so hold ad spend and focus on retention"

    active = facts.active_offers()
    offer = active[0] if active else facts.catalog_offer(kind)
    offer_is_suggestion = not bool(active) and bool(offer)
    deliverable = f"a fresh Google post plus {offer} pinned on your profile" if offer else "a fresh Google post for your profile"

    facts_text = [why_now] + evidence + ([anchor] if anchor else []) + ([judgment] if judgment else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=judgment,
        offer=offer, offer_is_suggestion=offer_is_suggestion, deliverable=deliverable,
        cta="binary_yes_stop", levers=["loss_aversion", "specificity"], facts_text=facts_text,
    )


def build_seasonal_perf_dip(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["metric", "delta_pct"])

    if not placeholder:
        metric = payload.get("metric")
        delta_pct = payload.get("delta_pct")
        why_now = f"{facts.plain(metric)} down {facts.fmt_pct(delta_pct).lstrip('-')} this week"
    else:
        neg = facts.strongest_negative()
        if not neg:
            return degrade_to("curious_ask_due", kind, facts, category, merchant, trigger, customer, common)
        kind_of, metric, value = neg
        if kind_of == "delta":
            why_now = f"{facts.plain(metric)} down {facts.fmt_pct(value).lstrip('-')} this week"
        else:
            why_now = f"{value['mine']} {facts.plain(metric)} vs {value['peer']} peer average"

    now_dt = facts.ref_now
    beat = facts.seasonal_beat(now_dt.month) if now_dt else None
    evidence = [beat.get("note")] if beat and beat.get("note") else []

    ca = merchant.get("customer_aggregate", {}) or {}
    anchor = f"your {ca['total_active_members']} active members" if ca.get("total_active_members") else None

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor,
        judgment="this is the normal seasonal lull, so hold ad spend and focus on retention",
        offer=None, offer_is_suggestion=False,
        deliverable="a 4-week member retention challenge",
        cta="binary_yes_stop", levers=["anxiety_preemption", "reciprocity"], facts_text=facts_text,
    )


def build_perf_spike(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["metric", "delta_pct"])

    likely_driver = payload.get("likely_driver")
    driver_plain = likely_driver.replace("_", " ") if likely_driver else None

    if not placeholder:
        metric = payload.get("metric")
        delta_pct = payload.get("delta_pct")
        vs_baseline = payload.get("vs_baseline")
        why_now = f"{facts.plain(metric)} up {facts.fmt_pct(delta_pct)} this week"
        if vs_baseline is not None:
            why_now += f" (baseline {vs_baseline})"
        if driver_plain:
            why_now += f", driven by {driver_plain}"
    else:
        pos = facts.strongest_positive()
        if not pos:
            return degrade_to("curious_ask_due", kind, facts, category, merchant, trigger, customer, common)
        kind_of, metric, value = pos
        if kind_of == "delta":
            why_now = f"{facts.plain(metric)} up {facts.fmt_pct(value)} this week"
        else:
            why_now = f"{value['mine']} {facts.plain(metric)} vs {value['peer']} peer average"

    gap = facts.peer_gap(metric)
    evidence = []
    if gap and gap["direction"] == "above":
        evidence = [f"{gap['mine']} {facts.plain(metric)} vs {gap['peer']} peer average"]

    active = facts.active_offers()
    ca = merchant.get("customer_aggregate", {}) or {}
    anchor = active[0] if active else (
        f"your {ca['total_active_members']} active members" if ca.get("total_active_members") else None
    )

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor,
        judgment="double down on what caused it",
        offer=active[0] if active else None, offer_is_suggestion=False,
        deliverable="a repeat of the winning post format",
        cta="binary_yes_stop", levers=["momentum", "social_proof"], facts_text=facts_text,
    )


def build_milestone_reached(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["metric", "value_now", "milestone_value"])
    is_imminent = bool(payload.get("is_imminent", False))

    if not placeholder:
        metric = payload.get("metric")
        value_now = payload.get("value_now")
        milestone_value = payload.get("milestone_value")
        gap = milestone_value - value_now
        facts.derive("milestone_gap", gap)
        why_now = f"{value_now} {facts.plain(metric)}: {gap} away from {milestone_value}"
    else:
        ca = merchant.get("customer_aggregate", {}) or {}
        value_now = ca.get("total_unique_ytd")
        milestone_value = next((m for m in MILESTONE_STEPS if value_now and m > value_now), None) if value_now else None
        if not value_now or not milestone_value:
            return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_milestone_data")
        gap = milestone_value - value_now
        facts.derive("milestone_gap", gap)
        why_now = f"{value_now} customers this year: {gap} short of {milestone_value}"

    peer_reviews = facts.peer("reviews")
    evidence = [f"metro peers average {peer_reviews} reviews"] if peer_reviews else []

    short = facts.short_name()
    anchor = f"that's at {short}" if short else None
    judgment = "worth closing the gap now" if is_imminent else None

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=judgment,
        offer=None, offer_is_suggestion=False,
        deliverable="a review-request WhatsApp for your recent happy customers",
        cta="binary_yes_stop", levers=["goal_gradient", "social_proof"], facts_text=facts_text,
    )


def build_review_theme_emerged(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["theme", "occurrences_30d"])

    if not placeholder:
        theme = payload.get("theme")
        occurrences = payload.get("occurrences_30d")
        trend = payload.get("trend")
        theme_plain = (theme or "").replace("_", " ")
        why_now = f"{occurrences} reviews this month mention {theme_plain}"
        if trend:
            why_now += f", {trend}"
        quote = payload.get("common_quote")
    else:
        theme_item = facts.review_theme("neg") or facts.review_theme("pos")
        if not theme_item:
            return degrade_to("curious_ask_due", kind, facts, category, merchant, trigger, customer, common)
        theme_plain = (theme_item.get("theme") or "").replace("_", " ")
        occurrences = theme_item.get("occurrences_30d")
        why_now = f"{occurrences} reviews this month mention {theme_plain}"
        quote = theme_item.get("common_quote")

    evidence = []
    if quote:
        q = quote if len(quote) <= 60 else quote[:57] + "..."
        evidence = [f'"{q}"']

    pos_theme = facts.review_theme("pos")
    anchor = pos_theme.get("theme", "").replace("_", " ") if pos_theme else None
    judgment = "one operational fix plus a polite public reply keeps this from spreading"

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=judgment,
        offer=None, offer_is_suggestion=False,
        deliverable="a polite public reply and a one-line fix note for staff",
        cta="binary_yes_stop", levers=["loss_aversion", "reciprocity"], facts_text=facts_text,
    )
