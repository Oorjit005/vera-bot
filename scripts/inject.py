"""Push adaptive-injection updates (new digest item, changed performance, a new
customer + recall_due trigger, and a new trigger kind) against a live bot,
then tick and print what it does with them.

Usage: PYTHONUTF8=1 python scripts/inject.py --url http://localhost:8080
"""
import argparse
import json
import os
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATASET_DIR = os.environ.get(
    "DATASET_DIR", os.path.normpath(os.path.join(_HERE, "..", "..", "magicpin-ai-challenge", "expanded"))
)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _post(url, path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode("utf-8")}


def push_context(url, scope, context_id, version, payload):
    r = _post(url, "/v1/context", {"scope": scope, "context_id": context_id, "version": version, "payload": payload})
    print(f"push {scope} {context_id} v{version} -> {r}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR)
    args = ap.parse_args()
    url, dataset_dir = args.url, args.dataset_dir

    # 1. dentists v2: add a new compliance digest item
    dentists = _load(os.path.join(dataset_dir, "categories", "dentists.json"))
    dentists_v2 = json.loads(json.dumps(dentists))
    dentists_v2["digest"].append({
        "id": "d_2026W18_NEW_compliance", "kind": "compliance",
        "title": "New DCI advisory on sterilisation logs effective 2026-07-01",
        "source": "DCI circular 2026-05-01",
        "summary": "Weekly autoclave log now mandatory; spot audits from July.",
    })
    push_context(url, "category", "dentists", 2, dentists_v2)

    # 2. m_002 v2: performance change
    m002 = _load(os.path.join(dataset_dir, "merchants", "m_002_bharat_dentist_mumbai.json"))
    m002_v2 = json.loads(json.dumps(m002))
    perf = m002_v2["performance"]
    perf["views"] = int(perf["views"] * 1.4)
    perf["calls"] = int(perf["calls"] * 0.7)
    perf.setdefault("delta_7d", {})["views_pct"] = 0.40
    perf["delta_7d"]["calls_pct"] = -0.30
    push_context(url, "merchant", "m_002_bharat_dentist_mumbai", 2, m002_v2)

    # 3. a new customer + recall_due trigger
    new_customer = {
        "customer_id": "c_inject_new_001", "merchant_id": "m_001_drmeera_dentist_delhi",
        "identity": {"name": "Inject Test", "language_pref": "en"},
        "relationship": {"last_visit": "2025-10-26", "visits_total": 2, "services_received": ["cleaning"]},
        "state": "lapsed_soft",
        "preferences": {"channel": "whatsapp", "reminder_opt_in": True},
        "consent": {"opted_in_at": "2025-01-01", "scope": ["promotional_offers"]},
    }
    push_context(url, "customer", "c_inject_new_001", 1, new_customer)
    new_trigger = {
        "id": "trg_inject_recall_001", "scope": "customer", "kind": "recall_due", "source": "internal",
        "merchant_id": "m_001_drmeera_dentist_delhi", "customer_id": "c_inject_new_001",
        "payload": {"service_due": "6_month_cleaning", "last_service_date": "2025-10-26",
                    "due_date": "2026-04-26", "available_slots": []},
        "urgency": 3, "suppression_key": "recall:c_inject_new_001:6mo", "expires_at": "2099-01-01T00:00:00Z",
    }
    push_context(url, "trigger", "trg_inject_recall_001", 1, new_trigger)

    # 4. a new trigger kind the playbook has never seen by name
    weather_trigger = {
        "id": "trg_inject_weather_001", "scope": "merchant", "kind": "weather_heatwave", "source": "external",
        "merchant_id": "m_009_apollo_pharmacy_jaipur", "customer_id": None,
        "payload": {"temp_c": 44, "advisory": "heatwave_orange"},
        "urgency": 3, "suppression_key": "weather:jaipur:2026W18", "expires_at": "2099-01-01T00:00:00Z",
    }
    push_context(url, "trigger", "trg_inject_weather_001", 1, weather_trigger)

    r = _post(url, "/v1/tick", {
        "now": "2026-04-26T11:00:00Z",
        "available_triggers": ["trg_inject_recall_001", "trg_inject_weather_001"],
    })
    print(f"\ntick -> {len(r.get('actions', []))} actions")
    for a in r.get("actions", []):
        print(f" - {a['trigger_id']}: {a['body']}")


if __name__ == "__main__":
    main()
