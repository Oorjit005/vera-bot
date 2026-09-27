import re

from app.playbook._shared import common_fields, is_placeholder, make_brief, make_skip

TREND_NAME_MAP = {"ors": "ORS", "sunscreen": "sunscreen", "antifungal": "anti-fungal"}


def _parse_trend_entry(entry):
    m = re.match(r"^([a-zA-Z_]+)_demand_([+-]\d+)$", entry)
    if not m:
        return None, None
    key = m.group(1).lower()
    pct = int(m.group(2))
    if "cold" in key or "cough" in key:
        label = "cold & cough"
    else:
        label = TREND_NAME_MAP.get(key, key.replace("_", " "))
    return label, pct


def build_category_seasonal(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["trends"])

    item = facts.digest_by_kind("seasonal")
    now_dt = facts.ref_now
    beat = facts.seasonal_beat(now_dt.month) if now_dt else None

    parsed = []
    if not placeholder:
        for entry in payload.get("trends", []):
            label, pct = _parse_trend_entry(entry)
            if label is not None:
                parsed.append((label, pct))

    if parsed:
        risers = sorted([p for p in parsed if p[1] > 0], key=lambda p: -p[1])
        fallers = sorted([p for p in parsed if p[1] < 0], key=lambda p: p[1])
        why_now = ", ".join(f"{label} {'+' if pct > 0 else ''}{pct}%" for label, pct in parsed)
    else:
        if not item:
            return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_seasonal_data")
        why_now = item.get("title", "")
        risers, fallers = [], []

    if item and item.get("title") and item.get("title") != why_now:
        evidence = [item["title"]]
    elif beat and beat.get("note"):
        evidence = [beat["note"]]
    else:
        evidence = []

    ca = merchant.get("customer_aggregate", {}) or {}
    anchor = f"{facts.fmt_pct(ca['repeat_customer_pct'])} repeat customers" if ca.get("repeat_customer_pct") else None

    top_riser = risers[0][0] if risers else None
    judgment = "stock up the top risers, trim the faller" if (risers or fallers) else None
    deliverable = f"a restock checklist and a Google post for {top_riser}" if top_riser else "a restock checklist and a Google post"

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=judgment,
        offer=None, offer_is_suggestion=False, deliverable=deliverable,
        cta="binary_yes_stop", levers=["specificity", "loss_aversion"], facts_text=facts_text,
    )


def build_competitor_opened(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["competitor_name", "distance_km", "opened_date"])
    active = facts.active_offers()

    if not placeholder:
        name = payload.get("competitor_name")
        distance = payload.get("distance_km")
        opened = payload.get("opened_date")
        their_offer = payload.get("their_offer")
        why_now = f"{name} opened {distance} km away on {facts.fmt_date(opened)}"
        if their_offer:
            why_now += f", running {their_offer}"
        evidence = [f"your '{active[0]}' vs their '{their_offer}'"] if active and their_offer else []
    else:
        worst = None
        for metric in ["views", "calls", "directions", "ctr", "reviews"]:
            gap = facts.peer_gap(metric)
            if gap and gap["direction"] == "below" and (worst is None or gap["pct"] < worst[1]["pct"]):
                worst = (metric, gap)
        if not worst:
            return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_competitor_data")
        metric, gap = worst
        peer_reviews = facts.peer("reviews")
        peer_ctr = facts.peer("ctr")
        why_now = (
            f"metro peers average {peer_reviews} reviews / {facts.fmt_pct(peer_ctr)} CTR "
            f"vs your {gap['mine']} {facts.plain(metric)}"
        )
        evidence = []

    pos_theme = facts.review_theme("pos")
    anchor = None
    if pos_theme and pos_theme.get("common_quote"):
        q = pos_theme["common_quote"]
        anchor = f'"{q[:57] + "..." if len(q) > 60 else q}"'

    offer = active[0] if active else facts.catalog_offer(kind)
    offer_is_suggestion = not bool(active) and bool(offer)

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor,
        judgment="don't start a price war; compete on the differentiator",
        offer=offer, offer_is_suggestion=offer_is_suggestion,
        deliverable="a differentiation Google post",
        cta="binary_yes_stop", levers=["loss_aversion", "social_proof"], facts_text=facts_text,
    )


def build_festival_upcoming(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["festival", "date"])
    now_dt = facts.ref_now

    if not placeholder:
        festival = payload.get("festival")
        date_iso = payload.get("date")
        days_until = payload.get("days_until")
        if days_until is None and date_iso:
            days_until = facts.days_between(facts.now_iso, date_iso)
        why_now = f"{festival} is on {facts.fmt_date(date_iso)}: {days_until} days out"
        month_for_beat = int(date_iso[5:7]) if date_iso and len(date_iso) >= 7 else None
    else:
        next_month = (now_dt.month % 12) + 1 if now_dt else None
        beat = facts.seasonal_beat(next_month) if next_month else None
        if not beat:
            return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_festival_data")
        why_now = beat.get("note", "")
        days_until = None
        month_for_beat = next_month

    beat = facts.seasonal_beat(month_for_beat) if month_for_beat else None
    evidence = [beat.get("note")] if beat and beat.get("note") else []

    active = facts.active_offers()
    anchor = active[0] if active else None

    judgment = None
    if days_until is not None:
        judgment = "early-bird planning works in your favour" if days_until > 45 else "lock it in this week"

    offer = active[0] if active else facts.catalog_offer(kind)
    offer_is_suggestion = not bool(active) and bool(offer)

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=judgment,
        offer=offer, offer_is_suggestion=offer_is_suggestion,
        deliverable="a festive offer and post draft",
        cta="binary_yes_stop", levers=["urgency", "specificity"], facts_text=facts_text,
    )


def build_ipl_match_today(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["match", "venue"])

    item = facts.digest_by_kind("seasonal")
    if not item:
        for it in category.get("digest", []) or []:
            if "ipl" in (it.get("id", "") or "").lower():
                item = it
                break

    if placeholder:
        if not item:
            return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_ipl_data")
        why_now = item.get("title", "")
        is_weeknight = None
        summary = item.get("summary", "") or ""
    else:
        match = payload.get("match")
        venue = payload.get("venue")
        match_time_iso = payload.get("match_time_iso")
        is_weeknight = payload.get("is_weeknight")
        time_str = ""
        if match_time_iso:
            day_time = facts.fmt_day_time(match_time_iso)
            time_str = day_time.split(", ")[-1] if day_time else ""
        why_now = f"{match} at {venue} tonight, {time_str}".strip()
        summary = (item or {}).get("summary", "") or ""

    evidence = []
    if summary:
        if is_weeknight is False and "-12%" in summary:
            evidence = ["Saturday IPL covers run ~12% below a normal Saturday"]
        elif is_weeknight is True and "+18%" in summary:
            evidence = ["weeknight matches drive ~18% more covers"]
        else:
            evidence = [summary]

    active = facts.active_offers()
    offer = active[0] if active else None
    anchor = offer

    if is_weeknight is False:
        judgment = (f"skip a dine-in match promo; push {offer} as a delivery special" if offer
                    else "skip a dine-in match promo; push delivery instead")
    elif is_weeknight is True:
        judgment = "push a Match-night Combo tonight"
    else:
        judgment = None

    facts_text = [why_now] + evidence + ([anchor] if anchor else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=judgment,
        offer=offer, offer_is_suggestion=False,
        deliverable="a delivery banner and an Insta story",
        cta="binary_yes_stop", levers=["counter_intuitive_data", "loss_aversion"], facts_text=facts_text,
    )
