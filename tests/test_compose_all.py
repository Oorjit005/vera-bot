import asyncio
import json
import os

import pytest

from app.compose import compose
from app.validate import validate

DEFAULT_NOW = "2026-04-26T10:00:00Z"


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_dir(path):
    out = {}
    for fn in sorted(os.listdir(path)):
        if fn.endswith(".json"):
            out[fn[:-5]] = _load(os.path.join(path, fn))
    return out


@pytest.fixture(scope="module")
def dataset(dataset_dir):
    categories = _load_dir(os.path.join(dataset_dir, "categories"))
    merchants = _load_dir(os.path.join(dataset_dir, "merchants"))
    customers = _load_dir(os.path.join(dataset_dir, "customers"))
    triggers = _load_dir(os.path.join(dataset_dir, "triggers"))
    cat_by_slug = {v.get("slug"): v for v in categories.values()}
    return cat_by_slug, merchants, customers, triggers


def test_all_100_triggers_skip_or_valid(dataset):
    os.environ["LLM_ENABLED"] = "0"
    cat_by_slug, merchants, customers, triggers = dataset
    assert len(triggers) == 100

    failures = []
    for trigger_id, trigger in sorted(triggers.items()):
        merchant = merchants.get(trigger.get("merchant_id"))
        category = cat_by_slug.get(merchant.get("category_slug")) if merchant else None
        customer = customers.get(trigger.get("customer_id")) if trigger.get("customer_id") else None

        result = asyncio.run(compose(category, merchant, trigger, customer, now=DEFAULT_NOW))

        if "skip" in result:
            if not result["skip"]:
                failures.append(f"{trigger_id}: empty skip reason")
            continue

        body = result["body"]
        from app.playbook import build_brief
        brief = build_brief(trigger.get("kind"), category, merchant, trigger, customer, DEFAULT_NOW)
        errors = validate(body, brief)
        if errors:
            failures.append(f"{trigger_id} ({trigger.get('kind')}): {errors} | body={body!r}")

        for key in ("body", "cta", "send_as", "suppression_key", "rationale", "template_name", "template_params"):
            if key not in result:
                failures.append(f"{trigger_id}: missing action key {key}")

    assert not failures, "\n".join(failures)


def test_30_test_pairs_compose(dataset_dir, dataset):
    os.environ["LLM_ENABLED"] = "0"
    cat_by_slug, merchants, customers, triggers = dataset
    pairs = _load(os.path.join(dataset_dir, "test_pairs.json"))["pairs"]
    assert len(pairs) == 30

    for pair in pairs:
        trigger = triggers.get(pair["trigger_id"])
        assert trigger is not None, pair["trigger_id"]
        merchant = merchants.get(pair["merchant_id"])
        category = cat_by_slug.get(merchant.get("category_slug")) if merchant else None
        customer_id = pair.get("customer_id")
        customer = customers.get(customer_id) if customer_id else None

        result = asyncio.run(compose(category, merchant, trigger, customer, now=DEFAULT_NOW))
        assert "skip" in result or "body" in result
