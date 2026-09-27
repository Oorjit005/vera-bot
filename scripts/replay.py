"""Run 6 scripted conversations against a live bot URL and print transcripts.

Usage: PYTHONUTF8=1 python scripts/replay.py --url http://localhost:8080
"""
import argparse
import json
import urllib.error
import urllib.request

NOW = "2026-04-26T10:35:00Z"
MERCHANT_ID = "m_001_drmeera_dentist_delhi"
CUSTOMER_ID = "c_001_priya_for_m001"


def _post(url, path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode("utf-8")}


def _reply(url, conv_id, message, turn, from_role="merchant", customer_id=None):
    body = {
        "conversation_id": conv_id, "merchant_id": MERCHANT_ID, "customer_id": customer_id,
        "from_role": from_role, "message": message, "received_at": NOW, "turn_number": turn,
    }
    r = _post(url, "/v1/reply", body)
    print(f"  [{conv_id} turn {turn}] {message!r} -> {r}")
    return r


def scenario_engaged(url):
    print("\n=== Scenario: engaged merchant ===")
    _reply(url, "conv_replay_engaged", "Yes please send the abstract. Also draft the patient WhatsApp.", 2)
    _reply(url, "conv_replay_engaged", "Thanks!", 3)


def scenario_auto_reply(url):
    print("\n=== Scenario: auto-reply x4 ===")
    msg = "Thank you for contacting us! Our team will respond shortly."
    for i, conv in enumerate(["conv_replay_auto_1", "conv_replay_auto_2", "conv_replay_auto_3", "conv_replay_auto_4"], start=2):
        _reply(url, conv, msg, i)


def scenario_intent_after_questions(url):
    print("\n=== Scenario: intent transition after 2 questions ===")
    _reply(url, "conv_replay_intent", "What's the source for this?", 2)
    _reply(url, "conv_replay_intent", "How long will this take?", 3)
    _reply(url, "conv_replay_intent", "Ok lets do it. Whats next?", 4)


def scenario_hostile_then_gst(url):
    print("\n=== Scenario: hostile then GST ===")
    _reply(url, "conv_replay_hostile", "Stop messaging me. This is useless spam.", 2)
    _reply(url, "conv_replay_hostile", "Btw can you help with my GST filing?", 3)


def scenario_hindi_switch(url):
    print("\n=== Scenario: Hindi switch ===")
    _reply(url, "conv_replay_hindi", "Haan theek hai, kar do", 2)
    _reply(url, "conv_replay_hindi", "Kitna time lagega?", 3)


def scenario_customer_slot_booking(url):
    print("\n=== Scenario: customer slot booking ===")
    _reply(url, "conv_replay_booking", "2", 2, from_role="customer", customer_id=CUSTOMER_ID)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    args = ap.parse_args()

    scenario_engaged(args.url)
    scenario_auto_reply(args.url)
    scenario_intent_after_questions(args.url)
    scenario_hostile_then_gst(args.url)
    scenario_hindi_switch(args.url)
    scenario_customer_slot_booking(args.url)


if __name__ == "__main__":
    main()
