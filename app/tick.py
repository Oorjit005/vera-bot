import asyncio
from datetime import datetime, timezone

from app import config
from app.compose import compose
from app.facts import _parse_iso
from app.store import Conversation, store

TICK_MAX_ACTIONS = 20


def _now_dt(now_iso):
    return _parse_iso(now_iso) or datetime.now(timezone.utc)


def _select(now_dt, available_triggers):
    candidates = []
    for tid in available_triggers or []:
        trigger = store.trigger(tid)
        if trigger is None:
            continue
        urgency = trigger.get("urgency", 1)
        if not isinstance(urgency, int) or isinstance(urgency, bool):
            urgency = 1
        candidates.append((urgency, tid, trigger))
    candidates.sort(key=lambda t: (-t[0], t[1]))

    selected = []
    merchants_used = set()
    customers_used = set()

    for _urgency, tid, trigger in candidates:
        if len(selected) >= TICK_MAX_ACTIONS:
            break
        merchant_id = trigger.get("merchant_id")
        customer_id = trigger.get("customer_id")
        scope = trigger.get("scope", "merchant")
        is_merchant_facing = scope != "customer"

        merchant = store.merchant(merchant_id) if merchant_id else None
        category = store.category(merchant.get("category_slug")) if merchant else None
        if merchant is None or category is None:
            continue

        customer = None
        if not is_merchant_facing:
            if not customer_id:
                continue
            customer = store.customer(customer_id)
            if customer is None:
                continue

        suppression_key = trigger.get("suppression_key") or ""
        if suppression_key and suppression_key in store.sent_suppression_keys:
            continue

        mstate = store.merchant_state(merchant_id)
        if mstate.opted_out:
            continue
        if is_merchant_facing and mstate.parked_until:
            parked_dt = _parse_iso(mstate.parked_until)
            if parked_dt and parked_dt > now_dt:
                continue
        if is_merchant_facing and mstate.unanswered_proactive >= 3:
            continue

        if is_merchant_facing:
            if merchant_id in merchants_used:
                continue
        else:
            if customer_id in customers_used:
                continue

        selected.append((tid, trigger, merchant, merchant_id, category, customer, customer_id, is_merchant_facing))
        if is_merchant_facing:
            merchants_used.add(merchant_id)
        else:
            customers_used.add(customer_id)

    return selected


async def _compose_one(item, now):
    tid, trigger, merchant, merchant_id, category, customer, customer_id, is_merchant_facing = item
    try:
        result = await compose(category, merchant, trigger, customer, now=now)
    except Exception:
        return None
    if "skip" in result:
        return None
    return (tid, trigger, merchant_id, customer_id, is_merchant_facing, result)


def _make_conversation_id(base_id):
    conv_id = base_id
    suffix = 2
    while conv_id in store.used_conversation_ids:
        conv_id = f"{base_id}_{suffix}"
        suffix += 1
    return conv_id


async def select_and_compose(now, available_triggers):
    store.last_now = now
    now_dt = _now_dt(now)
    selected = _select(now_dt, available_triggers)

    async def _bounded():
        return await asyncio.gather(*[_compose_one(item, now) for item in selected])

    try:
        results = await asyncio.wait_for(_bounded(), timeout=config.TICK_DEADLINE_S)
    except asyncio.TimeoutError:
        results = []

    actions = []
    for r in results:
        if r is None:
            continue
        if len(actions) >= TICK_MAX_ACTIONS:
            break
        tid, trigger, merchant_id, customer_id, is_merchant_facing, result = r
        kind = trigger.get("kind", "")
        if is_merchant_facing:
            base_id = f"conv_{merchant_id}_{kind}_{now_dt.strftime('%Y%m%d')}"
        else:
            base_id = f"conv_{customer_id}_{kind}_{now_dt.strftime('%Y%m')}"
        conv_id = _make_conversation_id(base_id)
        store.used_conversation_ids.add(conv_id)

        template_params = result.get("template_params") or []
        deliverable = template_params[3] if len(template_params) > 3 else ""
        store.conversations[conv_id] = Conversation(
            id=conv_id, merchant_id=merchant_id, customer_id=customer_id, trigger_id=tid,
            kind=kind, send_as=result["send_as"], language="", deliverable=deliverable,
            bodies_sent=[result["body"]],
        )

        sk = result.get("suppression_key") or ""
        if sk:
            store.sent_suppression_keys.add(sk)
        if is_merchant_facing:
            store.merchant_state(merchant_id).unanswered_proactive += 1

        actions.append({
            "conversation_id": conv_id, "merchant_id": merchant_id, "customer_id": customer_id,
            "send_as": result["send_as"], "trigger_id": tid,
            "template_name": result["template_name"], "template_params": result["template_params"],
            "body": result["body"], "cta": result["cta"],
            "suppression_key": sk, "rationale": result["rationale"],
        })

    return actions


_SEM = None


def _get_sem():
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(config.LLM_CONCURRENCY)
    return _SEM


async def _precompose(trigger_id):
    try:
        async with _get_sem():
            trigger = store.trigger(trigger_id)
            if trigger is None:
                return
            merchant_id = trigger.get("merchant_id")
            customer_id = trigger.get("customer_id")
            merchant = store.merchant(merchant_id) if merchant_id else None
            category = store.category(merchant.get("category_slug")) if merchant else None
            customer = store.customer(customer_id) if customer_id else None
            if merchant is None or category is None:
                return
            await compose(category, merchant, trigger, customer, now=store.last_now)
    except Exception:
        pass


def precompose_schedule_for(scope, context_id):
    affected = set()
    if scope == "trigger":
        affected.add(context_id)
    elif scope == "merchant":
        affected |= store.triggers_by_merchant.get(context_id, set())
    elif scope == "customer":
        affected |= store.triggers_by_customer.get(context_id, set())
    elif scope == "category":
        for merchant_id in store.merchants_by_category.get(context_id, set()):
            affected |= store.triggers_by_merchant.get(merchant_id, set())
    if not affected:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    for tid in affected:
        loop.create_task(_precompose(tid))
