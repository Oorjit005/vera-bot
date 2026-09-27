"""Compose a message for every trigger in DATASET_DIR and write out/all_messages.md.

Usage: PYTHONUTF8=1 python scripts/run_all_triggers.py [--llm] [--only-test-pairs]
"""
import argparse
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
    out = {}
    if not os.path.isdir(path):
        return out
    for fn in sorted(os.listdir(path)):
        if fn.endswith(".json"):
            data = _load(os.path.join(path, fn))
            out[fn[:-5]] = data
    return out


async def _run(dataset_dir, only_ids=None):
    from app import config
    from app.compose import compose

    categories = _load_dir(os.path.join(dataset_dir, "categories"))
    merchants = _load_dir(os.path.join(dataset_dir, "merchants"))
    customers = _load_dir(os.path.join(dataset_dir, "customers"))
    triggers = _load_dir(os.path.join(dataset_dir, "triggers"))

    cat_by_slug = {v.get("slug"): v for v in categories.values()}

    entries = sorted(triggers.items())
    if only_ids is not None:
        entries = [(tid, t) for tid, t in entries if tid in only_ids]

    results = []
    for trigger_id, trigger in entries:
        merchant_id = trigger.get("merchant_id")
        customer_id = trigger.get("customer_id")
        merchant = merchants.get(merchant_id)
        category = cat_by_slug.get(merchant.get("category_slug")) if merchant else None
        customer = customers.get(customer_id) if customer_id else None

        result = await compose(category, merchant, trigger, customer, now=DEFAULT_NOW)
        results.append((trigger_id, trigger, result))

    return results


def _write_report(results, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lines = ["# All triggers\n"]
    skipped, ok = 0, 0
    for trigger_id, trigger, result in results:
        lines.append(f"## {trigger_id} ({trigger.get('kind')})\n")
        if "skip" in result:
            skipped += 1
            lines.append(f"- SKIPPED: {result['skip']}\n")
        else:
            ok += 1
            lines.append(f"- body: {result['body']}\n")
            lines.append(f"- cta: {result['cta']}  send_as: {result['send_as']}\n")
            lines.append(f"- rationale: {result['rationale']}\n")
        lines.append("\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("".join(lines))
    print(f"Wrote {out_path}: {ok} composed, {skipped} skipped")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--only-test-pairs", action="store_true")
    args = ap.parse_args()

    if args.llm:
        os.environ["LLM_ENABLED"] = "1"
    else:
        os.environ["LLM_ENABLED"] = "0"

    only_ids = None
    if args.only_test_pairs:
        pairs_path = os.path.join(args.dataset_dir, "test_pairs.json")
        with open(pairs_path, encoding="utf-8") as f:
            pairs = json.load(f)["pairs"]
        only_ids = {p["trigger_id"] for p in pairs}

    results = asyncio.run(_run(args.dataset_dir, only_ids))
    out_path = os.path.join(_REPO_ROOT, "out", "all_messages.md")
    _write_report(results, out_path)


if __name__ == "__main__":
    main()
