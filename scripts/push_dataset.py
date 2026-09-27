"""Push categories, merchants and customers (v1, no triggers) into a running bot.

Usage: PYTHONUTF8=1 python scripts/push_dataset.py --url http://localhost:8080
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATASET_DIR = os.path.normpath(
    os.path.join(_HERE, "..", "..", "magicpin-ai-challenge", "expanded")
)


def load_dir(path):
    items = []
    for fn in sorted(os.listdir(path)):
        if fn.endswith(".json"):
            with open(os.path.join(path, fn), encoding="utf-8") as f:
                items.append(json.load(f))
    return items


def push(url, scope, context_id, version, payload):
    body = json.dumps({
        "scope": scope, "context_id": context_id, "version": version, "payload": payload,
    }).encode("utf-8")
    req = urllib.request.Request(
        url + "/v1/context", data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        return e.code, (json.loads(raw) if raw else {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--dataset-dir", default=os.environ.get("DATASET_DIR", DEFAULT_DATASET_DIR))
    args = ap.parse_args()

    categories = load_dir(os.path.join(args.dataset_dir, "categories"))
    merchants = load_dir(os.path.join(args.dataset_dir, "merchants"))
    customers = load_dir(os.path.join(args.dataset_dir, "customers"))

    jobs = []
    for c in categories:
        jobs.append(("category", c["slug"], c))
    for m in merchants:
        jobs.append(("merchant", m["merchant_id"], m))
    for cu in customers:
        jobs.append(("customer", cu["customer_id"], cu))

    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {
            ex.submit(push, args.url, scope, cid, 1, payload): (scope, cid)
            for scope, cid, payload in jobs
        }
        for fut in as_completed(futs):
            scope, cid = futs[fut]
            try:
                status, resp = fut.result()
                if status == 200 and resp.get("accepted"):
                    ok += 1
                else:
                    fail += 1
                    print(f"FAIL {scope} {cid}: {status} {resp}")
            except Exception as e:
                fail += 1
                print(f"ERROR {scope} {cid}: {e}")

    print(f"Pushed: {ok} ok, {fail} failed")

    req = urllib.request.Request(args.url + "/v1/healthz", method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        health = json.loads(resp.read().decode("utf-8"))
    print("healthz:", health)

    expected = {
        "category": len(categories), "merchant": len(merchants),
        "customer": len(customers), "trigger": 0,
    }
    counts = health.get("contexts_loaded", {})
    if counts != expected:
        print(f"MISMATCH: expected {expected}, got {counts}")
        sys.exit(1)
    print("OK: healthz counts match", expected)


if __name__ == "__main__":
    main()
