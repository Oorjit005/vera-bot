import os


def _bool(v: str) -> bool:
    return v.strip().lower() not in ("0", "false", "no", "")


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or None
WRITER_MODEL = os.environ.get("WRITER_MODEL", "gemini-3.1-flash-lite")
LLM_ENABLED = _bool(os.environ.get("LLM_ENABLED", "1")) and GEMINI_API_KEY is not None
LLM_MAX_CALLS = int(os.environ.get("LLM_MAX_CALLS", "4000"))
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "8"))
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "7.0"))
TICK_DEADLINE_S = float(os.environ.get("TICK_DEADLINE_S", "8.0"))
REPLY_DEADLINE_S = float(os.environ.get("REPLY_DEADLINE_S", "8.0"))
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "w1")
TEAM_NAME = os.environ.get("TEAM_NAME", "Oorjit Sharma")
TEAM_MEMBERS = [s.strip() for s in os.environ.get("TEAM_MEMBERS", "Oorjit Sharma").split(",") if s.strip()]
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "oorjitsharma99@gmail.com")
BOT_VERSION = os.environ.get("BOT_VERSION", "1.0.0")
SUBMITTED_AT = os.environ.get("SUBMITTED_AT", "")
DATASET_DIR = os.environ.get("DATASET_DIR", "../magicpin-ai-challenge/expanded")
PORT = int(os.environ.get("PORT", "8080"))
APPROACH = (
    "deterministic brief (facts+playbook) -> Gemini writer -> deterministic "
    "validator -> deterministic template fallback; rules-first reply classifier"
)
