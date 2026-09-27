import re

from app.playbook._shared import common_fields, make_brief, make_skip


def build_research_digest(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    top_id = payload.get("top_item_id")
    item = facts.digest(top_id) if top_id else None
    if not item:
        item = facts.digest_by_kind("research") or facts.digest_by_kind("trend")
    if not item:
        return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_digest_item")

    why_now = item.get("title", "")
    summary = item.get("summary", "") or ""
    trial_n = item.get("trial_n")
    source_citation = item.get("source")

    ca = merchant.get("customer_aggregate", {}) or {}
    patient_segment = item.get("patient_segment", "") or ""
    anchor = None
    if "high_risk" in patient_segment and ca.get("high_risk_adult_count"):
        anchor = f"your {ca['high_risk_adult_count']} high-risk adult patients"
    elif ca.get("total_unique_ytd"):
        anchor = f"your {ca['total_unique_ytd']} patients this year"

    judgment = None
    if "no effect in low-risk" in summary.lower():
        judgment = "most relevant if your case-mix has active-decay adults"

    evidence = [summary] if summary else []
    if trial_n:
        facts.derive("research_trial_n", trial_n)

    facts_text = [why_now, summary] + ([anchor] if anchor else []) + ([judgment] if judgment else [])
    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=judgment,
        offer=None, offer_is_suggestion=False,
        deliverable="the 2-min abstract plus a patient-education WhatsApp draft",
        cta="binary_yes_stop", levers=["specificity", "curiosity", "reciprocity"],
        source_citation=source_citation, facts_text=facts_text,
    )


def build_regulation_change(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    top_id = payload.get("top_item_id")
    item = facts.digest(top_id) if top_id else None
    if not item:
        item = facts.digest_by_kind("compliance")
    if not item:
        return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_digest_item")

    deadline_iso = payload.get("deadline_iso")
    deadline_str = facts.fmt_date(deadline_iso) if deadline_iso else None
    title = item.get("title", "")
    why_now = f"{title}, effective {deadline_str}" if deadline_str else title
    summary = item.get("summary", "") or ""
    source_citation = item.get("source")
    evidence = [summary] if summary else []
    anchor = f"{facts.short_name()} X-ray setup" if facts.short_name() else None
    judgment = "check plainly what passes and what fails so you can self-audit"
    facts_text = [why_now, summary] + ([anchor] if anchor else [])

    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=judgment,
        offer=None, offer_is_suggestion=False,
        deliverable="a 5-point X-ray compliance checklist and an SOP line",
        cta="binary_yes_stop", levers=["loss_aversion", "specificity"],
        source_citation=source_citation, facts_text=facts_text,
    )


def build_cde_opportunity(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    item_id = payload.get("digest_item_id")
    item = facts.digest(item_id) if item_id else None
    if not item:
        item = facts.digest_by_kind("cde")
    if not item:
        return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_digest_item")

    title = item.get("title", "")
    date_iso = item.get("date") or payload.get("date")
    date_str = facts.fmt_date(date_iso) if date_iso else None
    time_str = None
    if date_iso and "T" in date_iso:
        day_time = facts.fmt_day_time(date_iso)
        if day_time:
            time_str = day_time.split(", ")[-1]

    why_now = title
    if date_str:
        why_now += f", {date_str}"
    if time_str:
        why_now += f" {time_str}"

    credits = payload.get("credits") or item.get("credits")
    fee = payload.get("fee")
    summary = item.get("summary", "") or ""
    speaker_m = re.search(r"Speaker:\s*([^.]+)\.", summary)
    speaker = speaker_m.group(1).strip() if speaker_m else None

    ev_parts = []
    if credits:
        ev_parts.append(f"{credits} CDE credits")
    if fee:
        ev_parts.append(str(fee).replace("_", " "))
    if speaker:
        ev_parts.append(f"speaker {speaker}")
    evidence = [", ".join(ev_parts)] if ev_parts else ([summary] if summary else [])
    facts_text = [why_now] + evidence

    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=None, judgment=None,
        offer=None, offer_is_suggestion=False,
        deliverable="the registration details and a calendar reminder",
        cta="binary_yes_stop", levers=["curiosity", "low_effort"],
        source_citation=item.get("source"), facts_text=facts_text,
    )


def build_supply_alert(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "merchant")
    payload = (trigger or {}).get("payload", {}) or {}
    molecule = payload.get("molecule")
    batches = payload.get("affected_batches") or []
    manufacturer = payload.get("manufacturer")
    item = facts.digest_by_kind("alert")

    if molecule and batches and manufacturer:
        batches_str = ", ".join(batches)
        why_now = f"voluntary recall: {molecule} batches {batches_str} ({manufacturer})"
        summary = (item or {}).get("summary", "") or ""
        ev_phrases = [p for p in ("sub-potency", "no safety risk") if p in summary.lower()]
        evidence = [", ".join(ev_phrases)] if ev_phrases else ([summary] if summary else [])
        source_citation = (item or {}).get("source")
    else:
        if not item:
            return make_skip(kind, "merchant", "vera", common, trigger, merchant, customer, "no_alert_data")
        why_now = item.get("title", "")
        summary = item.get("summary", "") or ""
        evidence = [summary] if summary else []
        source_citation = item.get("source")

    ca = merchant.get("customer_aggregate", {}) or {}
    anchor = f"your {ca['chronic_rx_count']} chronic-Rx customers" if ca.get("chronic_rx_count") else None
    judgment = "I won't share an affected-customer count here; want me to pull the list instead?"
    facts_text = [why_now] + evidence + ([anchor] if anchor else [])

    return make_brief(
        kind, "merchant", "vera", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=judgment,
        offer=None, offer_is_suggestion=False,
        deliverable="the customer WhatsApp note and a replacement-pickup workflow",
        cta="binary_yes_stop", levers=["urgency", "effort_externalization"],
        source_citation=source_citation, facts_text=facts_text,
    )
