import asyncio
import json
import os

from app.compose import compose

DEFAULT_NOW = "2026-04-26T10:00:00Z"

# 03-dataset.md quirk #10: these numbers/names appear in the case-study examples
# but are NOT in the actual dataset. If they ever appear in a composed body, the
# composer fabricated them.
FORBIDDEN_STRINGS = ["1,420", "240 saved", "2,499 skin-prep", "Embassy Tech", "RMZ Eco", "Sigma Soft"]


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_dir(path):
    out = {}
    for fn in sorted(os.listdir(path)):
        if fn.endswith(".json"):
            out[fn[:-5]] = _load(os.path.join(path, fn))
    return out


def test_no_fabricated_case_study_numbers(dataset_dir):
    os.environ["LLM_ENABLED"] = "0"
    categories = _load_dir(os.path.join(dataset_dir, "categories"))
    merchants = _load_dir(os.path.join(dataset_dir, "merchants"))
    customers = _load_dir(os.path.join(dataset_dir, "customers"))
    triggers = _load_dir(os.path.join(dataset_dir, "triggers"))
    cat_by_slug = {v.get("slug"): v for v in categories.values()}

    for trigger_id, trigger in sorted(triggers.items()):
        merchant = merchants.get(trigger.get("merchant_id"))
        category = cat_by_slug.get(merchant.get("category_slug")) if merchant else None
        customer = customers.get(trigger.get("customer_id")) if trigger.get("customer_id") else None

        result = asyncio.run(compose(category, merchant, trigger, customer, now=DEFAULT_NOW))
        if "skip" in result:
            continue
        body = result["body"]
        for forbidden in FORBIDDEN_STRINGS:
            assert forbidden not in body, f"{trigger_id}: fabricated '{forbidden}' in {body!r}"


def test_every_number_in_body_is_grounded(dataset_dir):
    """Belt-and-suspenders: validate.UNGROUNDED already checks this per-message
    inside test_compose_all, but assert it directly here for a documented sample."""
    os.environ["LLM_ENABLED"] = "0"
    from app.facts import FactSet
    from app.playbook import build_brief
    from app.validate import validate

    categories = _load_dir(os.path.join(dataset_dir, "categories"))
    merchants = _load_dir(os.path.join(dataset_dir, "merchants"))
    triggers = _load_dir(os.path.join(dataset_dir, "triggers"))
    cat_by_slug = {v.get("slug"): v for v in categories.values()}

    trigger = triggers["trg_001_research_digest_dentists"]
    merchant = merchants["m_001_drmeera_dentist_delhi"]
    category = cat_by_slug["dentists"]

    result = asyncio.run(compose(category, merchant, trigger, None, now=DEFAULT_NOW))
    assert "skip" not in result
    brief = build_brief(trigger["kind"], category, merchant, trigger, None, DEFAULT_NOW)
    errors = [e for e in validate(result["body"], brief) if e.startswith("UNGROUNDED")]
    assert not errors, errors
