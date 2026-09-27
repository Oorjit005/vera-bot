from app.playbook._shared import CUSTOMER_KINDS, common_fields, make_brief


def build(kind, facts, category, merchant, trigger, customer):
    audience = "customer" if kind in CUSTOMER_KINDS else "merchant"
    send_as = "merchant_on_behalf" if audience == "customer" else "vera"
    common = common_fields(kind, facts, category, merchant, trigger, customer, audience)
    payload = (trigger or {}).get("payload", {}) or {}

    kind_plain = kind.replace("_", " ")
    scalar_parts = []
    for k in sorted(payload.keys()):
        if len(scalar_parts) >= 3:
            break
        v = payload.get(k)
        if isinstance(v, bool) or "id" in k.lower():
            continue
        if isinstance(v, (str, int, float)):
            scalar_parts.append(f"{k.replace('_', ' ')}: {v}")
    why_now = kind_plain
    if scalar_parts:
        why_now += " (" + "; ".join(scalar_parts) + ")"

    now_dt = facts.ref_now
    beat = facts.seasonal_beat(now_dt.month) if now_dt else None
    evidence = [beat.get("note")] if beat and beat.get("note") else []

    active = facts.active_offers() if merchant else []
    anchor = active[0] if active else None
    if not anchor and merchant:
        for metric in ["views", "calls", "ctr"]:
            gap = facts.peer_gap(metric)
            if gap:
                anchor = f"{gap['mine']} {facts.plain(metric)} vs {gap['peer']} peer average"
                break

    payload_lines = [
        f"{k}: {v}" for k, v in sorted(payload.items())
        if isinstance(v, (str, int, float)) and not isinstance(v, bool)
    ]
    facts_text = [why_now] + evidence + ([anchor] if anchor else []) + payload_lines

    return make_brief(
        kind, audience, send_as, common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=anchor, judgment=None,
        offer=active[0] if active else None, offer_is_suggestion=False,
        deliverable="a timely Google post and offer tweak",
        cta="binary_yes_stop", levers=["specificity"], facts_text=facts_text,
    )
