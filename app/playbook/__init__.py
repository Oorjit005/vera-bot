from app.facts import FactSet
from app.playbook import conversation, customer, generic, knowledge, lifecycle, market, performance
from app.playbook._shared import ALIASES, CUSTOMER_KINDS, common_fields, make_skip

REGISTRY = {
    "research_digest": knowledge.build_research_digest,
    "regulation_change": knowledge.build_regulation_change,
    "cde_opportunity": knowledge.build_cde_opportunity,
    "supply_alert": knowledge.build_supply_alert,
    "perf_dip": performance.build_perf_dip,
    "seasonal_perf_dip": performance.build_seasonal_perf_dip,
    "perf_spike": performance.build_perf_spike,
    "milestone_reached": performance.build_milestone_reached,
    "review_theme_emerged": performance.build_review_theme_emerged,
    "dormant_with_vera": lifecycle.build_dormant_with_vera,
    "renewal_due": lifecycle.build_renewal_due,
    "winback_eligible": lifecycle.build_winback_eligible,
    "gbp_unverified": lifecycle.build_gbp_unverified,
    "category_seasonal": market.build_category_seasonal,
    "competitor_opened": market.build_competitor_opened,
    "festival_upcoming": market.build_festival_upcoming,
    "ipl_match_today": market.build_ipl_match_today,
    "curious_ask_due": conversation.build_curious_ask_due,
    "active_planning_intent": conversation.build_active_planning_intent,
    "recall_due": customer.build_recall_due,
    "appointment_tomorrow": customer.build_appointment_tomorrow,
    "chronic_refill_due": customer.build_chronic_refill_due,
    "customer_lapsed_soft": customer.build_customer_lapsed_soft,
    "customer_lapsed_hard": customer.build_customer_lapsed_hard,
    "trial_followup": customer.build_trial_followup,
    "wedding_package_followup": customer.build_wedding_package_followup,
}


def build_brief(kind, category, merchant, trigger, customer_ctx, now):
    norm_kind = ALIASES.get(kind, kind)
    facts = FactSet(category, merchant, trigger, customer_ctx, now)
    audience = "customer" if norm_kind in CUSTOMER_KINDS else "merchant"
    send_as = "merchant_on_behalf" if audience == "customer" else "vera"

    if category is None or merchant is None:
        common = common_fields(norm_kind, facts, category, merchant, trigger, customer_ctx, audience)
        return make_skip(norm_kind, audience, send_as, common, trigger, merchant, customer_ctx, "missing_context")

    if audience == "customer":
        if customer_ctx is None:
            common = common_fields(norm_kind, facts, category, merchant, trigger, customer_ctx, audience)
            return make_skip(norm_kind, audience, send_as, common, trigger, merchant, customer_ctx, "missing_customer")
        consent = customer_ctx.get("consent", {}) or {}
        prefs = customer_ctx.get("preferences", {}) or {}
        if not consent.get("scope") or prefs.get("reminder_opt_in") is False:
            common = common_fields(norm_kind, facts, category, merchant, trigger, customer_ctx, audience)
            return make_skip(norm_kind, audience, send_as, common, trigger, merchant, customer_ctx, "no_consent")

    builder = REGISTRY.get(norm_kind)
    if builder is None:
        return generic.build(norm_kind, facts, category, merchant, trigger, customer_ctx)
    return builder(norm_kind, facts, category, merchant, trigger, customer_ctx)
