def test_auto_reply_hell_send_wait_end(client, dataset_dir):
    msg = "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly."
    payload_base = {"merchant_id": "m_001_drmeera_dentist_delhi", "from_role": "merchant",
                     "message": msg, "received_at": "2026-04-26T10:42:00Z"}

    status, r1 = client.post("/v1/reply", {**payload_base, "conversation_id": "conv_auto_1", "turn_number": 2})
    assert status == 200
    assert r1["action"] == "send"

    status, r2 = client.post("/v1/reply", {**payload_base, "conversation_id": "conv_auto_2", "turn_number": 3})
    assert r2["action"] == "wait"

    status, r3 = client.post("/v1/reply", {**payload_base, "conversation_id": "conv_auto_3", "turn_number": 4})
    assert r3["action"] == "end"

    status, r4 = client.post("/v1/reply", {**payload_base, "conversation_id": "conv_auto_4", "turn_number": 5})
    assert r4["action"] == "end"


def test_intent_transition_action_words(client):
    status, r = client.post("/v1/reply", {
        "conversation_id": "conv_intent_1", "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant", "message": "Ok lets do it. Whats next?",
        "received_at": "2026-04-26T10:42:00Z", "turn_number": 3,
    })
    assert status == 200
    assert r["action"] == "send"
    body_lower = r["body"].lower()
    assert any(w in body_lower for w in ("done", "sending", "draft", "here", "confirm", "proceed", "next"))
    for banned in ("would you", "do you", "can you tell", "what if", "how about"):
        assert banned not in body_lower


def test_hostile_ends(client):
    status, r = client.post("/v1/reply", {
        "conversation_id": "conv_hostile", "merchant_id": "m_002_bharat_dentist_mumbai",
        "from_role": "merchant", "message": "Stop messaging me. This is useless spam.",
        "received_at": "2026-04-26T10:42:00Z", "turn_number": 2,
    })
    assert status == 200
    if r["action"] == "send":
        body_lower = r["body"].lower()
        assert any(w in body_lower for w in ("sorry", "apolog", "won't", "wont"))
    else:
        assert r["action"] == "end"


def test_gst_off_topic_decline_and_redirect(client):
    status, r = client.post("/v1/reply", {
        "conversation_id": "conv_gst_test", "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant", "message": "Btw can you also help me with my GST filing this month?",
        "received_at": "2026-04-26T10:42:00Z", "turn_number": 2,
    })
    assert status == 200
    assert r["action"] == "send"
    assert "CA" in r["body"] or "ca" in r["body"].lower()


def test_hindi_switch_to_hinglish(client):
    status, r1 = client.post("/v1/reply", {
        "conversation_id": "conv_hindi_test", "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant", "message": "Haan theek hai, kar do",
        "received_at": "2026-04-26T10:42:00Z", "turn_number": 2,
    })
    assert status == 200
    assert r1["action"] == "send"

    from app.store import store
    conv = store.conversations.get("conv_hindi_test")
    assert conv is not None
    assert conv.language == "hinglish"


def test_unknown_conversation_id_handled_gracefully(client):
    status, r = client.post("/v1/reply", {
        "conversation_id": "conv_never_seen_before", "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant", "message": "What is this about?",
        "received_at": "2026-04-26T10:42:00Z", "turn_number": 1,
    })
    assert status == 200
    assert r["action"] in ("send", "wait", "end")


def test_not_interested_then_closed(client):
    payload = {"conversation_id": "conv_not_interested", "merchant_id": "m_002_bharat_dentist_mumbai",
               "from_role": "merchant", "message": "Not interested, no thanks",
               "received_at": "2026-04-26T10:42:00Z", "turn_number": 2}
    status, r1 = client.post("/v1/reply", payload)
    assert r1["action"] == "send"
    status, r2 = client.post("/v1/reply", {**payload, "turn_number": 3})
    assert r2["action"] == "end"


def test_later_wait_seconds(client):
    status, r = client.post("/v1/reply", {
        "conversation_id": "conv_later_test", "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant", "message": "Busy right now, call tomorrow",
        "received_at": "2026-04-26T10:42:00Z", "turn_number": 2,
    })
    assert status == 200
    assert r["action"] == "wait"
    assert r["wait_seconds"] == 86400


def test_customer_slot_booking_accept(client):
    status, r = client.post("/v1/reply", {
        "conversation_id": "conv_customer_booking", "merchant_id": "m_001_drmeera_dentist_delhi",
        "customer_id": "c_001_priya_for_m001", "from_role": "customer", "message": "2",
        "received_at": "2026-04-26T10:42:00Z", "turn_number": 2,
    })
    assert status == 200
    assert r["action"] == "send"
    assert "Confirmed" in r["body"]


def test_thanks_ack_then_end(client):
    payload = {"conversation_id": "conv_thanks_test", "merchant_id": "m_002_bharat_dentist_mumbai",
               "from_role": "merchant", "message": "thanks",
               "received_at": "2026-04-26T10:42:00Z", "turn_number": 2}
    status, r1 = client.post("/v1/reply", payload)
    assert r1["action"] == "send"
    status, r2 = client.post("/v1/reply", {**payload, "turn_number": 3})
    assert r2["action"] == "end"


def test_reply_never_crashes_on_malformed_body(client):
    status, r = client.post_raw("/v1/reply", b"{not json")
    assert status == 200
    assert r["action"] in ("wait", "send", "end")
