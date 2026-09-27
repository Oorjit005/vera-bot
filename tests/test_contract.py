import json
import os


def _load(dataset_dir, *parts):
    with open(os.path.join(dataset_dir, *parts), encoding="utf-8") as f:
        return json.load(f)


# --- 1.1 healthz before anything is pushed ---

def test_healthz_initial_zero_counts(client):
    status, body = client.get("/v1/healthz")
    assert status == 200
    assert body["status"] == "ok"
    assert isinstance(body["uptime_seconds"], int)
    assert body["contexts_loaded"] == {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}


# --- 1.2 metadata ---

def test_metadata_shape(client):
    status, body = client.get("/v1/metadata")
    assert status == 200
    for key in ("team_name", "team_members", "model", "approach", "contact_email", "version", "submitted_at"):
        assert key in body
    assert isinstance(body["team_members"], list)


# --- 1.3 push category ---

def test_push_category(client, dataset_dir):
    payload = _load(dataset_dir, "categories", "dentists.json")
    status, body = client.post("/v1/context", {
        "scope": "category", "context_id": "dentists", "version": 1, "payload": payload,
    })
    assert status == 200
    assert body["accepted"] is True
    assert body["ack_id"] == "ack_dentists_v1"
    assert body["stored_at"].endswith("Z")


# --- 1.4 push merchant ---

def test_push_merchant(client, dataset_dir):
    mfile = sorted(os.listdir(os.path.join(dataset_dir, "merchants")))[0]
    payload = _load(dataset_dir, "merchants", mfile)
    mid = payload["merchant_id"]
    status, body = client.post("/v1/context", {
        "scope": "merchant", "context_id": mid, "version": 1, "payload": payload,
    })
    assert status == 200
    assert body["accepted"] is True
    assert body["ack_id"] == f"ack_{mid}_v1"


# --- 1.5 same version re-push -> 409 ---

def test_stale_version_same_version(client, dataset_dir):
    payload = _load(dataset_dir, "merchants", "m_001_drmeera_dentist_delhi.json")
    mid = payload["merchant_id"]
    body1 = {"scope": "merchant", "context_id": mid, "version": 1, "payload": payload}
    status, resp = client.post("/v1/context", body1)
    assert status == 200

    status2, resp2 = client.post("/v1/context", body1)
    assert status2 == 409
    assert resp2["accepted"] is False
    assert resp2["reason"] == "stale_version"
    assert resp2["current_version"] == 1


def test_stale_version_lower_version(client, dataset_dir):
    payload = _load(dataset_dir, "merchants", "m_001_drmeera_dentist_delhi.json")
    mid = payload["merchant_id"]
    client.post("/v1/context", {"scope": "merchant", "context_id": mid, "version": 2, "payload": payload})

    status, resp = client.post("/v1/context", {"scope": "merchant", "context_id": mid, "version": 1, "payload": payload})
    assert status == 409
    assert resp["reason"] == "stale_version"
    assert resp["current_version"] == 2


# --- 1.6 version bump replaces ---

def test_version_bump_replaces(client, dataset_dir):
    payload = _load(dataset_dir, "merchants", "m_001_drmeera_dentist_delhi.json")
    mid = payload["merchant_id"]
    status1, resp1 = client.post("/v1/context", {"scope": "merchant", "context_id": mid, "version": 1, "payload": payload})
    assert status1 == 200

    payload2 = dict(payload)
    payload2["performance"] = dict(payload["performance"])
    payload2["performance"]["views"] = 2580
    status2, resp2 = client.post("/v1/context", {"scope": "merchant", "context_id": mid, "version": 2, "payload": payload2})
    assert status2 == 200
    assert resp2["ack_id"] == f"ack_{mid}_v2"

    _, health = client.get("/v1/healthz")
    assert health["contexts_loaded"]["merchant"] == 1


# --- 400s: invalid scope / invalid payload; never 422 ---

def test_invalid_scope(client):
    status, body = client.post("/v1/context", {"scope": "bogus", "context_id": "x", "version": 1, "payload": {}})
    assert status == 400
    assert body["accepted"] is False
    assert body["reason"] == "invalid_scope"


def test_invalid_payload_variants(client):
    bad_bodies = [
        {"scope": "merchant", "context_id": "", "version": 1, "payload": {}},
        {"scope": "merchant", "context_id": "m1", "version": True, "payload": {}},
        {"scope": "merchant", "context_id": "m1", "version": 1, "payload": "not-a-dict"},
        {"scope": "merchant", "context_id": "m1", "payload": {}},
        {"scope": "merchant", "version": 1, "payload": {}},
    ]
    for bad in bad_bodies:
        status, body = client.post("/v1/context", bad)
        assert status == 400, bad
        assert body["accepted"] is False
        assert body["reason"] == "invalid_payload"


def test_malformed_json_never_422(client):
    status, body = client.post_raw("/v1/context", b"not json{{{")
    assert status == 400
    assert status != 422
    assert body["accepted"] is False


def test_tick_malformed_json_never_crashes(client):
    status, body = client.post_raw("/v1/tick", b"{not valid")
    assert status == 200
    assert body == {"actions": []}


def test_reply_malformed_json_never_crashes(client):
    status, body = client.post_raw("/v1/reply", b"{not valid")
    assert status == 200
    assert body["action"] in ("wait", "end", "send")


# --- 1.7 healthz after full warmup ---

def test_healthz_after_warmup(client, dataset_dir):
    categories = [f for f in sorted(os.listdir(os.path.join(dataset_dir, "categories"))) if f.endswith(".json")]
    merchants = [f for f in sorted(os.listdir(os.path.join(dataset_dir, "merchants"))) if f.endswith(".json")]
    customers = [f for f in sorted(os.listdir(os.path.join(dataset_dir, "customers"))) if f.endswith(".json")]

    for fn in categories:
        p = _load(dataset_dir, "categories", fn)
        client.post("/v1/context", {"scope": "category", "context_id": p["slug"], "version": 1, "payload": p})
    for fn in merchants:
        p = _load(dataset_dir, "merchants", fn)
        client.post("/v1/context", {"scope": "merchant", "context_id": p["merchant_id"], "version": 1, "payload": p})
    for fn in customers:
        p = _load(dataset_dir, "customers", fn)
        client.post("/v1/context", {"scope": "customer", "context_id": p["customer_id"], "version": 1, "payload": p})

    status, health = client.get("/v1/healthz")
    assert status == 200
    assert health["contexts_loaded"] == {
        "category": len(categories), "merchant": len(merchants), "customer": len(customers), "trigger": 0,
    }


# --- tick stub (S1: always empty actions) ---

def test_tick_returns_actions_list(client):
    status, body = client.post("/v1/tick", {"now": "2026-04-26T10:35:00Z", "available_triggers": []})
    assert status == 200
    assert body == {"actions": []}


def test_tick_missing_now_uses_default(client):
    status, body = client.post("/v1/tick", {"available_triggers": []})
    assert status == 200
    assert body == {"actions": []}


# --- reply stub (S1: wait 60) ---

def test_reply_stub_shape(client):
    status, body = client.post("/v1/reply", {
        "conversation_id": "conv_1", "merchant_id": "m_1", "customer_id": None,
        "from_role": "merchant", "message": "hi", "received_at": "2026-04-26T10:42:00Z", "turn_number": 1,
    })
    assert status == 200
    assert body["action"] in ("wait", "send", "end")
    if body["action"] == "wait":
        assert isinstance(body["wait_seconds"], int)
    assert "rationale" in body


# --- teardown ---

def test_teardown_clears_store(client, dataset_dir):
    payload = _load(dataset_dir, "categories", "dentists.json")
    client.post("/v1/context", {"scope": "category", "context_id": "dentists", "version": 1, "payload": payload})

    status, body = client.post("/v1/teardown")
    assert status == 200
    assert body == {"ok": True}

    _, health = client.get("/v1/healthz")
    assert health["contexts_loaded"] == {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
