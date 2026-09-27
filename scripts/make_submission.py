"""Compose all 30 canonical test pairs and write out/submission.jsonl.

Usage: PYTHONUTF8=1 python scripts/make_submission.py
"""
import asyncio
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

DEFAULT_DATASET_DIR = os.environ.get(
    "DATASET_DIR", os.path.normpath(os.path.join(_HERE, "..", "..", "magicpin-ai-challenge", "expanded"))
)
DEFAULT_NOW = "2026-04-26T10:00:00Z"


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_dir(path):
    return {fn[:-5]: _load(os.path.join(path, fn)) for fn in sorted(os.listdir(path)) if fn.endswith(".json")}


async def main():
    from app.compose import compose

    dataset_dir = DEFAULT_DATASET_DIR
    categories = _load_dir(os.path.join(dataset_dir, "categories"))
    merchants = _load_dir(os.path.join(dataset_dir, "merchants"))
    customers = _load_dir(os.path.join(dataset_dir, "customers"))
    triggers = _load_dir(os.path.join(dataset_dir, "triggers"))
    cat_by_slug = {v.get("slug"): v for v in categories.values()}
    pairs = _load(os.path.join(dataset_dir, "test_pairs.json"))["pairs"]

    out_path = os.path.join(_REPO_ROOT, "out", "submission.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    lines = []
    for pair in pairs:
        trigger = triggers.get(pair["trigger_id"])
        merchant = merchants.get(pair["merchant_id"])
        category = cat_by_slug.get(merchant.get("category_slug")) if merchant else None
        customer = customers.get(pair.get("customer_id")) if pair.get("customer_id") else None

        if trigger is None or merchant is None or category is None:
            lines.append({"test_id": pair["test_id"], "skipped": "missing_context"})
            continue

        result = await compose(category, merchant, trigger, customer, now=DEFAULT_NOW)
        if "skip" in result:
            lines.append({"test_id": pair["test_id"], "skipped": result["skip"]})
        else:
            lines.append({
                "test_id": pair["test_id"], "body": result["body"], "cta": result["cta"],
                "send_as": result["send_as"], "suppression_key": result["suppression_key"],
                "rationale": result["rationale"],
            })

    with open(out_path, "w", encoding="utf-8") as f:
        for row in lines:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    skipped = sum(1 for r in lines if "skipped" in r)
    print(f"Wrote {out_path}: {len(lines) - skipped} composed, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(main())
