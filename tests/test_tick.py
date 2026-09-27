import json
import os

NOW = "2026-04-26T10:35:00Z"
ACTION_KEYS = {"conversation_id", "merchant_id", "customer_id", "send_as", "trigger_id",
               "template_name", "template_params", "body", "cta", "suppression_key", "rationale"}


def _load(dataset_dir, *parts):
    with open(os.path.join(dataset_dir, *parts), encoding="utf-8") as f:
        return json.load(f)


def _push_category(client, dataset_dir, slug):
    payload = _load(dataset_dir, "categories", f"{slug}.json")
    status, body = client.post("/v1/context", {"scope": "category", "context_id": slug, "version": 1, "payload": payload})
    assert status == 200, body


def _push_merchant(client, dataset_dir, filename):
    payload = _load(dataset_dir, "merchants", filename)
    mid = payload["merchant_id"]
    status, body = client.post("/v1/context", {"scope": "merchant", "context_id": mid, "version": 1, "payload": payload})
    assert status == 200, body
    return payload


def _push_customer(client, dataset_dir, filename):
    payload = _load(dataset_dir, "customers", filename)
    cid = payload["customer_id"]
    status, body = client.post("/v1/context", {"scope": "customer", "context_id": cid, "version": 1, "payload": payload})
    assert status == 200, body
    return payload


def _push_trigger(client, filename_or_payload, dataset_dir=None):
    payload = filename_or_payload if isinstance(filename_or_payload, dict) else _load(dataset_dir, "triggers", filename_or_payload)
    tid = payload["id"]
    status, body = client.post("/v1/context", {"scope": "trigger", "context_id": tid, "version": 1, "payload": payload})
    assert status == 200, body
    return payload


def _synthetic_trigger(tid, merchant_id, kind="weather_heatwave", scope="merchant", customer_id=None,
                        urgency=1, suppression_key=None):
    return {
        "id": tid, "scope": scope, "kind": kind, "source": "external",
        "merchant_id": merchant_id, "customer_id": customer_id,
        "payload": {"note": "synthetic"}, "urgency": urgency,
        "suppression_key": suppression_key or f"{kind}:{merchant_id}:{customer_id or ''}",
        "expires_at": "2099-01-01T00:00:00Z",
    }


def test_tick_action_has_all_11_keys(client, dataset_dir):
    _push_category(client, dataset_dir, "dentists")
    m = _push_merchant(client, dataset_dir, "m_001_drmeera_dentist_delhi.json")
    trig = _push_trigger(client, "trg_001_research_digest_dentists.json", dataset_dir)

    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [trig["id"]]})
    assert status == 200
    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert set(action.keys()) == ACTION_KEYS
    assert action["merchant_id"] == m["merchant_id"]
    assert action["trigger_id"] == trig["id"]


def test_tick_dedupes_across_ticks(client, dataset_dir):
    _push_category(client, dataset_dir, "dentists")
    _push_merchant(client, dataset_dir, "m_001_drmeera_dentist_delhi.json")
    trig = _push_trigger(client, "trg_001_research_digest_dentists.json", dataset_dir)

    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [trig["id"]]})
    assert len(body["actions"]) == 1

    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [trig["id"]]})
    assert body["actions"] == []


def test_tick_one_action_per_merchant(client, dataset_dir):
    _push_category(client, dataset_dir, "dentists")
    m = _push_merchant(client, dataset_dir, "m_001_drmeera_dentist_delhi.json")
    t1 = _synthetic_trigger("trg_synth_1", m["merchant_id"], kind="weather_heatwave", urgency=5)
    t2 = _synthetic_trigger("trg_synth_2", m["merchant_id"], kind="local_news_event", urgency=3)
    _push_trigger(client, t1)
    _push_trigger(client, t2)

    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [t1["id"], t2["id"]]})
    assert status == 200
    assert len(body["actions"]) == 1
    # higher urgency (5) must win over lower (3)
    assert body["actions"][0]["trigger_id"] == t1["id"]


def test_tick_caps_at_20_actions(client, dataset_dir):
    _push_category(client, dataset_dir, "dentists")
    triggers = []
    for i in range(25):
        mid = f"m_synth_{i}"
        merchant_payload = {
            "merchant_id": mid, "category_slug": "dentists",
            "identity": {"name": f"Synth Clinic {i}", "owner_first_name": f"Owner{i}"},
            "performance": {"views": 100, "calls": 10, "directions": 5, "ctr": 0.02, "delta_7d": {}},
            "offers": [], "customer_aggregate": {}, "signals": [], "review_themes": [],
        }
        status, _ = client.post("/v1/context", {"scope": "merchant", "context_id": mid, "version": 1, "payload": merchant_payload})
        assert status == 200
        t = _synthetic_trigger(f"trg_synth_cap_{i}", mid, kind="weather_heatwave")
        triggers.append(t)
        _push_trigger(client, t)

    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [t["id"] for t in triggers]})
    assert status == 200
    assert len(body["actions"]) <= 20


def test_c015_no_consent_skipped(client, dataset_dir):
    _push_category(client, dataset_dir, "pharmacies")
    m = _push_merchant(client, dataset_dir, "m_010_sunrisepharm_pharmacy_lucknow.json")
    c = _push_customer(client, dataset_dir, "c_015_anonymous_for_m010.json")
    assert c.get("consent", {}).get("scope") in (None, [])

    t = _synthetic_trigger("trg_c015_test", m["merchant_id"], kind="recall_due", scope="customer",
                            customer_id=c["customer_id"])
    _push_trigger(client, t)

    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [t["id"]]})
    assert status == 200
    assert body["actions"] == []


def test_missing_customer_skipped(client, dataset_dir):
    _push_category(client, dataset_dir, "dentists")
    m = _push_merchant(client, dataset_dir, "m_001_drmeera_dentist_delhi.json")
    t = _synthetic_trigger("trg_missing_cust", m["merchant_id"], kind="recall_due", scope="customer",
                            customer_id="c_does_not_exist")
    _push_trigger(client, t)

    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [t["id"]]})
    assert status == 200
    assert body["actions"] == []


def test_opted_out_merchant_skipped(client, dataset_dir):
    _push_category(client, dataset_dir, "dentists")
    m = _push_merchant(client, dataset_dir, "m_001_drmeera_dentist_delhi.json")
    t = _synthetic_trigger("trg_optout_test", m["merchant_id"], kind="weather_heatwave")
    _push_trigger(client, t)

    from app.store import store
    store.merchant_state(m["merchant_id"]).opted_out = True

    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [t["id"]]})
    assert status == 200
    assert body["actions"] == []


def test_conversation_id_uniqueness_within_same_day(client, dataset_dir):
    _push_category(client, dataset_dir, "dentists")
    m = _push_merchant(client, dataset_dir, "m_001_drmeera_dentist_delhi.json")
    t1 = _synthetic_trigger("trg_conv_a", m["merchant_id"], kind="weather_heatwave", suppression_key="sk_a")
    _push_trigger(client, t1)
    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [t1["id"]]})
    conv1 = body["actions"][0]["conversation_id"]

    t2 = _synthetic_trigger("trg_conv_b", m["merchant_id"], kind="weather_heatwave", suppression_key="sk_b")
    _push_trigger(client, t2)
    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [t2["id"]]})
    conv2 = body["actions"][0]["conversation_id"]

    assert conv1 != conv2
    assert conv2 == conv1 + "_2"


def test_deterministic_ordering_by_urgency(client, dataset_dir):
    _push_category(client, dataset_dir, "dentists")
    m1 = _push_merchant(client, dataset_dir, "m_001_drmeera_dentist_delhi.json")
    m2 = _push_merchant(client, dataset_dir, "m_011_dr_sameer_dentist_bangalore.json")
    t_low = _synthetic_trigger("trg_ord_low", m1["merchant_id"], kind="weather_heatwave", urgency=1)
    t_high = _synthetic_trigger("trg_ord_high", m2["merchant_id"], kind="weather_heatwave", urgency=5)
    _push_trigger(client, t_low)
    _push_trigger(client, t_high)

    status, body = client.post("/v1/tick", {"now": NOW, "available_triggers": [t_low["id"], t_high["id"]]})
    assert status == 200
    trigger_ids_in_order = [a["trigger_id"] for a in body["actions"]]
    assert trigger_ids_in_order == [t_high["id"], t_low["id"]]
