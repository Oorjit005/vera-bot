from app.playbook._shared import common_fields, is_placeholder, make_brief, make_skip


def build_dormant_with_vera(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    now_dt = facts.ref_now
    month = now_dt.month if now_dt else None
    beat = facts.seasonal_beat(month) if month else None
    trend = facts.trend_top()

    why_now = None
    evidence = []
    if beat and beat.get("note"):
        why_now = beat["note"]
        if trend and trend.get("query"):
            evidence = [f"'{trend['query']}' searches up {facts.fmt_pct(trend.get('delta_yoy'))} YoY"]
    elif trend and trend.get("query"):
        why_now = f"'{trend['query']}' searches up {facts.fmt_pct(trend.get('delta_yoy'))} YoY"
        if beat and beat.get("note"):
            evidence = [beat["note"]]
    else:
        return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_signal")

    gap_views = facts.peer_gap("views")
    ca = merchant.get("customer_aggregate", {}) or {}
    anchor = None
    if gap_views and gap_views["direction"] == "below":
        anchor = f"{gap_views['mine']} {facts.plain('views')} vs {gap_views['peer']} peer average"
    elif ca.get("lapsed_180d_plus"):
        anchor = f"{ca['lapsed_180d_plus']} customers lapsed 180+ days"
    elif ca.get("lapsed_90d_plus"):
        anchor = f"{ca['lapsed_90d_plus']} customers lapsed 90+ days"

    active = facts.active_offers()
    offer = active[0] if active else facts.catalog_offer(kind)
    offer_is_suggestion = not bool(active) and bool(offer)

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=None,
        offer=offer, offer_is_suggestion=offer_is_suggestion,
        deliverable="a Google post built on that trend",
        cta="binary_yes_stop", levers=["reciprocity", "curiosity"], facts_text=facts_text,
    )


def build_renewal_due(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["days_remaining", "plan"])
    sub = merchant.get("subscription", {}) or {}

    if not placeholder:
        plan = payload.get("plan")
        days_remaining = payload.get("days_remaining")
        renewal_amount = payload.get("renewal_amount")
    else:
        plan = sub.get("plan")
        days_remaining = sub.get("days_remaining")
        renewal_amount = None
        if not plan or days_remaining is None:
            return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_subscription_data")

    why_now = f"{plan} plan renews in {days_remaining} days"
    if renewal_amount:
        why_now += f" at {facts.fmt_inr(renewal_amount)}"

    perf = merchant.get("performance", {}) or {}
    views, calls, directions = perf.get("views"), perf.get("calls"), perf.get("directions")
    evidence = []
    if views is not None and calls is not None and directions is not None:
        evidence = [f"last 30 days: {views} views, {calls} calls, {directions} direction requests"]

    anchor = "listing boosts and campaigns pause if it lapses"
    facts_text = [why_now] + evidence + [anchor]
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=None,
        offer=None, offer_is_suggestion=False,
        deliverable="the renewal, processed at your go-ahead",
        cta="binary_yes_stop", levers=["loss_aversion"], facts_text=facts_text,
    )


def build_winback_eligible(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["days_since_expiry"])
    sub = merchant.get("subscription", {}) or {}

    days_since_expiry = payload.get("days_since_expiry") if not placeholder else sub.get("days_since_expiry")
    if days_since_expiry is None:
        return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_expiry_data")
    why_now = f"{days_since_expiry} days since your plan lapsed"

    evidence = []
    lapsed_added = payload.get("lapsed_customers_added_since_expiry")
    if lapsed_added:
        evidence.append(f"{lapsed_added} more customers went inactive since then")
    neg = facts.strongest_negative()
    if neg:
        kind_of, metric, value = neg
        if kind_of == "delta":
            evidence.append(f"{facts.plain(metric)} down {facts.fmt_pct(value).lstrip('-')}")
        else:
            evidence.append(f"{value['mine']} {facts.plain(metric)} vs {value['peer']} peer average")

    ca = merchant.get("customer_aggregate", {}) or {}
    anchor = f"{ca['lapsed_90d_plus']} customers lapsed 90+ days" if ca.get("lapsed_90d_plus") else None

    offer = facts.catalog_offer("winback") or facts.catalog_offer(kind)
    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor,
        judgment="here's what the lapse is costing you, in your own numbers",
        offer=offer, offer_is_suggestion=bool(offer),
        deliverable="a comeback offer post and your profile reactivated",
        cta="binary_yes_stop", levers=["loss_aversion"], facts_text=facts_text,
    )


def build_gbp_unverified(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["verification_path"])

    verified = (merchant.get("identity", {}) or {}).get("verified")
    if verified:
        return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "already_verified")

    why_now = "your profile is still unverified"
    evidence = []
    if not placeholder:
        path = payload.get("verification_path")
        uplift = payload.get("estimated_uplift_pct")
        path_plain = (path or "").replace("_", " ")
        if path_plain and uplift is not None:
            evidence = [f"verification via {path_plain}: can lift visibility ~{facts.fmt_pct(uplift)}"]
        elif path_plain:
            evidence = [f"verification via {path_plain}"]

    views = (merchant.get("performance", {}) or {}).get("views")
    anchor = f"{views} people viewed you in 30 days" if views is not None else None

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor,
        judgment="it's a small step to knock out",
        offer=None, offer_is_suggestion=False,
        deliverable="step-by-step verification help, starting today",
        cta="binary_yes_stop", levers=["loss_aversion", "effort_externalization"], facts_text=facts_text,
    )
