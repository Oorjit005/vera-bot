import json
from dataclasses import asdict, dataclass, field


@dataclass
class Brief:
    kind: str
    audience: str
    send_as: str
    language: str
    salutation: str
    sender_line: "str | None"
    why_now: str
    evidence: list
    merchant_anchor: "str | None"
    judgment: "str | None"
    offer: "str | None"
    offer_is_suggestion: bool
    deliverable: str
    cta: str
    cta_question: "str | None"
    slot_options: list
    levers: list
    source_citation: "str | None"
    vocab_hint: list
    taboo: list
    tone: str
    facts_text: list
    skip: "str | None" = None
    trigger_id: str = ""
    merchant_id: str = ""
    customer_id: "str | None" = None
    suppression_key: str = ""
    urgency: int = 1
    source: str = ""

    def canonical(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)

    def rationale(self) -> str:
        why_now_short = (self.why_now or "")[:120]
        anchor_short = (self.merchant_anchor or self.judgment or "")[:60]
        levers_str = ", ".join(self.levers or [])
        text = (
            f"{self.kind} ({self.source}, urgency {self.urgency}): {why_now_short}; "
            f"personalised via {anchor_short}; lever: {levers_str}; CTA {self.cta}; lang {self.language}."
        )
        return text[:300]
