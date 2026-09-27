from app.playbook._shared import common_fields, is_placeholder, make_brief, make_skip


def build_recall_due(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "customer")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["service_due", "last_service_date"])
    rel = customer.get("relationship", {}) or {}

    if not placeholder:
        service_due = payload.get("service_due", "")
        last_service_date = payload.get("last_service_date")
        service_plain = service_due.replace("_", " ")
        months = facts.months_since(last_service_date) if last_service_date else None
        if months is not None:
            why_now = f"it's been {months} months since your last visit on {facts.fmt_date(last_service_date)}; your {service_plain} is due"
        else:
            why_now = f"your {service_plain} is due"
        slots = payload.get("available_slots") or []
    else:
        last_visit = rel.get("last_visit")
        months = facts.months_since(last_visit) if last_visit else None
        services = rel.get("services_received") or []
        service_plain = services[-1].replace("_", " ") if services else "next visit"
        if months is not None and last_visit:
            why_now = f"it's been {months} months since your last visit on {facts.fmt_date(last_visit)}; your {service_plain} is due"
        else:
            why_now = "it's time for your next visit"
        slots = []

    is_dentist = category.get("slug") == "dentists"
    judgment = None if is_dentist else "time for your next session"

    active = facts.active_offers()
    offer = active[0] if active else None
    evidence = [offer] if offer else []

    slot_labels = [s.get("label") for s in slots if s.get("label")]
    if len(slot_labels) >= 2:
        cta = "multi_choice_slot"
        slot_options = [f"{i + 1} for {label}" for i, label in enumerate(slot_labels[:2])]
    else:
        cta = "binary_yes_stop"
        slot_options = []

    deliverable = f"your {service_plain} booking" if slot_labels else "a call to fix a time"

    facts_text = [why_now] + evidence + slot_labels
    return make_brief(
        kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=None, judgment=judgment,
        offer=offer, offer_is_suggestion=False, deliverable=deliverable,
        cta=cta, slot_options=slot_options,
        levers=["specificity", "reciprocity"], facts_text=facts_text,
    )


def build_appointment_tomorrow(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "customer")
    payload = (trigger or {}).get("payload", {}) or {}
    time_val = payload.get("time") or payload.get("appointment_time")
    why_now = f"your appointment tomorrow at {time_val}" if time_val else "you're booked with us tomorrow"

    facts_text = [why_now]
    return make_brief(
        kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer,
        why_now=why_now, evidence=[], merchant_anchor=None, judgment=None,
        offer=None, offer_is_suggestion=False, deliverable="your appointment, confirmed",
        cta="binary_confirm_cancel", levers=["specificity"], facts_text=facts_text,
    )


def build_chronic_refill_due(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "customer")
    payload = (trigger or {}).get("payload", {}) or {}
    is_pharmacy = category.get("slug") == "pharmacies"
    molecules = payload.get("molecule_list") or []
    stock_runs_out = payload.get("stock_runs_out_iso")

    if is_pharmacy and molecules and stock_runs_out:
        why_now = f"your {len(molecules)} monthly medicines ({', '.join(molecules)}) run out on {facts.fmt_date(stock_runs_out)}"
    else:
        rel = customer.get("relationship", {}) or {}
        last_visit = rel.get("last_visit")
        months = facts.months_since(last_visit) if last_visit else None
        if months is not None:
            why_now = f"it's been {months} months since your last visit on {facts.fmt_date(last_visit)}; time for a follow-up"
        else:
            why_now = "time for a follow-up"

    active = facts.active_offers()
    evidence = []
    is_senior = bool((customer.get("identity", {}) or {}).get("senior_citizen"))
    delivery_saved = bool(payload.get("delivery_address_saved"))
    delivery_offer = next((o for o in active if "delivery" in o.lower()), None)
    senior_offer = next((o for o in active if "senior" in o.lower()), None)

    if delivery_saved and delivery_offer:
        evidence.append(f"{delivery_offer} to your saved address")
    if is_senior and senior_offer:
        evidence.append(senior_offer)

    facts_text = [why_now] + evidence
    return make_brief(
        kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=None, judgment=None,
        offer=None, offer_is_suggestion=False,
        deliverable="your refill, dispatched" if (is_pharmacy and molecules) else "your next visit, booked",
        cta="binary_yes_stop", levers=["specificity", "effort_externalization"], facts_text=facts_text,
    )


def build_customer_lapsed_soft(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "customer")
    payload = (trigger or {}).get("payload", {}) or {}
    weeks = payload.get("weeks_since_last_visit")
    rel = customer.get("relationship", {}) or {}
    if weeks is None:
        last_visit = rel.get("last_visit")
        days = facts.days_between(last_visit, facts.now_iso) if last_visit else None
        weeks = (days // 7) if days is not None else None
    if weeks is None:
        return make_skip(kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer, "no_visit_data")
    why_now = f"it's been {weeks} weeks since your last visit"

    active = facts.active_offers()
    offer = active[0] if active else None
    evidence = [offer] if offer else []

    facts_text = [why_now] + evidence
    return make_brief(
        kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=None,
        judgment="no pressure, just a friendly check-in",
        offer=offer, offer_is_suggestion=False, deliverable="your next visit, booked",
        cta="binary_yes_stop", levers=["reciprocity"], facts_text=facts_text,
    )


def build_customer_lapsed_hard(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "customer")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["days_since_last_visit"])

    if not placeholder:
        days = payload.get("days_since_last_visit")
        weeks = round(days / 7) if days is not None else None
        previous_focus = payload.get("previous_focus")
    else:
        rel = customer.get("relationship", {}) or {}
        last_visit = rel.get("last_visit")
        days = facts.days_between(last_visit, facts.now_iso) if last_visit else None
        weeks = round(days / 7) if days is not None else None
        previous_focus = None

    if weeks is None:
        return make_skip(kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer, "no_visit_data")

    why_now = f"it's been about {weeks} weeks: happens to most members, no judgment"
    focus_plain = previous_focus.replace("_", " ") if previous_focus else None
    judgment = f"picking up your {focus_plain} goal, no-commitment framing" if focus_plain else "no-commitment framing"

    active = facts.active_offers()
    offer = active[0] if active else None
    evidence = [offer] if offer else []

    facts_text = [why_now] + evidence + ([focus_plain] if focus_plain else [])
    return make_brief(
        kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=None, judgment=judgment,
        offer=offer, offer_is_suggestion=False, deliverable="a free trial spot, held for you",
        cta="binary_yes_stop", levers=["reciprocity"], facts_text=facts_text,
    )


def build_trial_followup(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "customer")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["trial_date"])
    name = ((customer.get("identity", {}) or {}).get("name")) or "there"

    if not placeholder:
        trial_date = payload.get("trial_date")
        why_now = f"hope {name} enjoyed the trial on {facts.fmt_date(trial_date)}"
        slots = payload.get("next_session_options") or []
    else:
        rel = customer.get("relationship", {}) or {}
        last_visit = rel.get("last_visit")
        why_now = f"hope {name} enjoyed the trial on {facts.fmt_date(last_visit)}" if last_visit else f"hope {name} enjoyed the trial"
        slots = []

    slot_labels = [s.get("label") for s in slots if s.get("label")]
    if len(slot_labels) >= 2:
        cta = "multi_choice_slot"
        slot_options = [f"{i + 1} for {label}" for i, label in enumerate(slot_labels[:2])]
    else:
        cta = "binary_yes_stop"
        slot_options = []

    active = facts.active_offers()
    offer = active[0] if active else None
    evidence = [offer] if offer else []

    facts_text = [why_now] + evidence + slot_labels
    return make_brief(
        kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=None,
        judgment="offering your next session", offer=offer, offer_is_suggestion=False,
        deliverable="your next session, booked", cta=cta, slot_options=slot_options,
        levers=["reciprocity"], facts_text=facts_text,
    )


def build_wedding_package_followup(kind, facts, category, merchant, trigger, customer):
    common = common_fields(kind, facts, category, merchant, trigger, customer, "customer")
    payload = (trigger or {}).get("payload", {}) or {}
    placeholder = is_placeholder(trigger, ["wedding_date"])

    if not placeholder:
        days = payload.get("days_to_wedding")
        window = payload.get("next_step_window_open")
        if days is None:
            wedding_date = payload.get("wedding_date")
            days = facts.days_between(facts.now_iso, wedding_date) if wedding_date else None
        if days is not None:
            facts.derive("wedding_days", days)
        window_plain = (window or "").replace("_", " ")
        if days is not None and window_plain:
            why_now = f"{days} days to your wedding: the {window_plain} window is open now"
        elif days is not None:
            why_now = f"{days} days to your wedding"
        else:
            why_now = "your wedding window is open now"
    else:
        wedding_date = (customer.get("preferences", {}) or {}).get("wedding_date")
        if not wedding_date:
            return make_skip(kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer, "no_wedding_date")
        days = facts.days_between(facts.now_iso, wedding_date)
        facts.derive("wedding_days", days)
        why_now = f"{days} days to your wedding"

    active = facts.active_offers()
    offer = active[0] if active else None
    evidence = [offer] if offer else []

    facts_text = [why_now] + evidence
    return make_brief(
        kind, "customer", "merchant_on_behalf", common, trigger, merchant, customer,
        why_now=why_now, evidence=evidence, merchant_anchor=None, judgment=None,
        offer=offer, offer_is_suggestion=False, deliverable="your next step, booked",
        cta="binary_yes_stop", levers=["urgency"], facts_text=facts_text,
    )
