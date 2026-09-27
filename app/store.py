from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Entry:
    version: int
    payload: dict
    stored_at: str


@dataclass
class Conversation:
    id: str
    merchant_id: str
    customer_id: Optional[str]
    trigger_id: str
    kind: str
    send_as: str
    language: str
    brief_summary: dict = field(default_factory=dict)
    deliverable: str = ""
    bodies_sent: list = field(default_factory=list)
    turns: list = field(default_factory=list)
    status: str = "open"  # open|ended|waiting
    accept_count: int = 0
    offtopic_streak: int = 0
    thanks_nudged: bool = False
    delivered: bool = False


@dataclass
class MerchantState:
    autoreply_texts: dict = field(default_factory=dict)  # normalized_text -> count
    autoreply_count: int = 0
    opted_out: bool = False
    parked_until: Optional[str] = None
    unanswered_proactive: int = 0
    sent_suppression_keys: set = field(default_factory=set)
    last_lang: str = "en"


class Store:
    def __init__(self):
        self.contexts: dict[tuple[str, str], Entry] = {}
        self.triggers_by_merchant: dict[str, set] = {}
        self.triggers_by_customer: dict[str, set] = {}
        self.merchants_by_category: dict[str, set] = {}
        self.conversations: dict[str, Conversation] = {}
        self.merchant_states: dict[str, MerchantState] = {}
        self.sent_suppression_keys: set = set()
        self.used_conversation_ids: set = set()
        self.last_now: Optional[str] = None
        self.start_time = None

    def put(self, scope: str, context_id: str, version: int, payload: dict, stored_at: str):
        key = (scope, context_id)
        existing = self.contexts.get(key)
        if existing is not None and version <= existing.version:
            return "stale", existing.version
        self.contexts[key] = Entry(version=version, payload=payload, stored_at=stored_at)
        self._index(scope, context_id, payload)
        return "accepted", version

    def _index(self, scope: str, context_id: str, payload: dict):
        if scope == "trigger":
            merchant_id = payload.get("merchant_id")
            customer_id = payload.get("customer_id")
            if merchant_id:
                self.triggers_by_merchant.setdefault(merchant_id, set()).add(context_id)
            if customer_id:
                self.triggers_by_customer.setdefault(customer_id, set()).add(context_id)
        elif scope == "merchant":
            slug = payload.get("category_slug")
            if slug:
                self.merchants_by_category.setdefault(slug, set()).add(context_id)

    def _get(self, scope: str, context_id: str) -> Optional[dict]:
        entry = self.contexts.get((scope, context_id))
        return entry.payload if entry else None

    def category(self, slug: str) -> Optional[dict]:
        return self._get("category", slug)

    def merchant(self, merchant_id: str) -> Optional[dict]:
        return self._get("merchant", merchant_id)

    def customer(self, customer_id: str) -> Optional[dict]:
        return self._get("customer", customer_id)

    def trigger(self, trigger_id: str) -> Optional[dict]:
        return self._get("trigger", trigger_id)

    def counts(self) -> dict:
        out = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _cid) in self.contexts.keys():
            if scope in out:
                out[scope] += 1
        return out

    def version_key(self, *ids: str) -> str:
        parts = []
        for cid in ids:
            for (scope, context_id), entry in self.contexts.items():
                if context_id == cid:
                    parts.append(f"{cid}:{entry.version}")
                    break
            else:
                parts.append(f"{cid}:0")
        return "|".join(parts)

    def merchant_state(self, merchant_id: str) -> MerchantState:
        if merchant_id not in self.merchant_states:
            self.merchant_states[merchant_id] = MerchantState()
        return self.merchant_states[merchant_id]

    def clear(self):
        self.contexts.clear()
        self.triggers_by_merchant.clear()
        self.triggers_by_customer.clear()
        self.merchants_by_category.clear()
        self.conversations.clear()
        self.merchant_states.clear()
        self.sent_suppression_keys.clear()
        self.used_conversation_ids.clear()
        self.last_now = None


store = Store()
