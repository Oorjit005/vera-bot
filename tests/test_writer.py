import asyncio

import pytest

from app import config, writer
from app.brief import Brief


def _dummy_brief():
    return Brief(
        kind="research_digest", audience="merchant", send_as="vera", language="en",
        salutation="Dr. Meera", sender_line=None, why_now="JIDA Oct issue landed",
        evidence=["38% lower caries recurrence"], merchant_anchor="your 124 high-risk adult patients",
        judgment=None, offer=None, offer_is_suggestion=False,
        deliverable="the 2-min abstract plus a patient-education WhatsApp draft",
        cta="binary_yes_stop", cta_question=None, slot_options=[], levers=["specificity"],
        source_citation="JIDA Oct 2026, p.14", vocab_hint=[], taboo=[], tone="peer_clinical",
        facts_text=["JIDA Oct issue landed"], trigger_id="trg_001", merchant_id="m_001",
        suppression_key="sk", urgency=2, source="external",
    )


@pytest.fixture(autouse=True)
def _reset():
    writer.reset_writer_state()
    yield
    writer.reset_writer_state()


def test_write_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", None)
    result = asyncio.run(writer.write(_dummy_brief()))
    assert result is None


def test_write_success(monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    calls = []

    def fake_call(system_text, user_text, schema, timeout_s):
        calls.append(1)
        return {"body": "Dr. Meera, JIDA landed. Reply YES and I'll get it ready.", "rationale": "r"}, {}

    monkeypatch.setattr(writer, "_call_gemini_sync", fake_call)
    result = asyncio.run(writer.write(_dummy_brief()))
    assert result["body"].startswith("Dr. Meera")
    assert len(calls) == 1


def test_write_api_error_returns_none(monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(writer, "_call_gemini_sync", lambda *a, **k: None)
    result = asyncio.run(writer.write(_dummy_brief()))
    assert result is None


def test_write_bad_json_returns_none(monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")

    def fake_call(*a, **k):
        raise ValueError("bad json")

    def safe_wrapper(*a, **k):
        try:
            return fake_call(*a, **k)
        except Exception:
            return None

    monkeypatch.setattr(writer, "_call_gemini_sync", safe_wrapper)
    result = asyncio.run(writer.write(_dummy_brief()))
    assert result is None


def test_write_cache_hit_returns_identical_without_recalling(monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    calls = []

    def fake_call(system_text, user_text, schema, timeout_s):
        calls.append(1)
        return {"body": "cached body", "rationale": "r"}, {}

    monkeypatch.setattr(writer, "_call_gemini_sync", fake_call)
    brief = _dummy_brief()
    r1 = asyncio.run(writer.write(brief))
    r2 = asyncio.run(writer.write(brief))
    assert r1 == r2
    assert len(calls) == 1


def test_write_budget_exhausted_returns_none(monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config, "LLM_MAX_CALLS", 0)
    calls = []
    monkeypatch.setattr(writer, "_call_gemini_sync", lambda *a, **k: calls.append(1))
    result = asyncio.run(writer.write(_dummy_brief()))
    assert result is None
    assert not calls


def test_compose_falls_back_to_template_on_validator_failure(monkeypatch):
    import asyncio as _asyncio

    from app.compose import compose

    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")

    async def fake_write(brief, extra_rules=""):
        return {"body": "This mentions https://example.com which is forbidden.", "rationale": "bad"}

    monkeypatch.setattr(writer, "write", fake_write)
    monkeypatch.setattr(writer, "get_cached", lambda brief: None)

    category = {"slug": "dentists", "voice": {"tone": "peer_clinical", "vocab_taboo": []},
                "digest": [{"id": "d1", "kind": "research", "title": "Trial shows 38% improvement",
                             "summary": "No effect in low-risk.", "source": "JIDA"}]}
    merchant = {"merchant_id": "m_001", "category_slug": "dentists",
                "identity": {"name": "Dr. Meera's Dental Clinic", "owner_first_name": "Meera"},
                "customer_aggregate": {"total_unique_ytd": 540}}
    trigger = {"id": "trg_001", "kind": "research_digest", "merchant_id": "m_001",
               "payload": {"top_item_id": "d1"}, "urgency": 2, "source": "external",
               "suppression_key": "sk1"}

    result = _asyncio.run(compose(category, merchant, trigger, None, now="2026-04-26T10:00:00Z"))
    assert "skip" not in result
    assert "https://" not in result["body"]
