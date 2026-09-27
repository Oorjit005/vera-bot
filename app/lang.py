import re

CTA_EN = {
    "binary_yes_stop": "Reply YES and I'll get {d} ready.",
    "open_ended": "{q}",
    "binary_confirm_cancel": "Reply CONFIRM to go ahead.",
    "multi_choice_slot": "Reply {opts}, or tell us a time that works.",
    "none": "",
}
CTA_HI = {
    "binary_yes_stop": "Bas YES reply karein, main {d} ready kar dungi.",
    "binary_confirm_cancel": "CONFIRM reply karein, main aage badhati hoon.",
    "multi_choice_slot": "{opts} reply karein, ya apna time bata dijiye.",
}
GREET_CUSTOMER = {
    "en": "Hi {name}",
    "hinglish": "Hi {name}",
    "hindi": "Namaste {name} ji",
    "ta": "Vanakkam {name}",
    "te": "Namaskaram {name}",
    "kn": "Namaskara {name}",
}

_HINGLISH_WORDS = {
    "hai", "hain", "nahi", "nahin", "karo", "karna", "kya", "haan", "mujhe", "aap", "aapka",
    "chahiye", "bhej", "bhejo", "ji", "theek", "thik", "kar", "mein", "hoon", "raha", "rahi",
    "abhi", "kal", "acha", "accha", "bhai",
}
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_WORD_RE = re.compile(r"[a-zA-Z']+")


def merchant_lang(merchant, category):
    """D11: English body + Hinglish closing CTA when the merchant speaks Hindi
    and the category's voice code-mixes naturally. Gyms are English-only."""
    if not merchant or not category:
        return "en"
    if category.get("slug") == "gyms":
        return "en"
    languages = (merchant.get("identity", {}) or {}).get("languages") or []
    code_mix = (category.get("voice", {}) or {}).get("code_mix")
    if "hi" in languages and code_mix == "hindi_english_natural":
        return "en+hi_cta"
    return "en"


def customer_lang(customer):
    """D12. Returns a plain lang string, or ("en", greeting_key) for the
    Tamil/Telugu/Kannada regional greetings (PLAN §5.4)."""
    if not customer:
        return "en"
    pref = ((customer.get("identity", {}) or {}).get("language_pref") or "").strip().lower()
    if pref == "hi-en mix":
        return "hinglish"
    if pref == "hi":
        return "hindi"
    if pref in ("en", "english"):
        return "en"
    if pref == "ta-en mix":
        return ("en", "ta")
    if pref == "te-en mix":
        return ("en", "te")
    if pref == "kn-en mix":
        return ("en", "kn")
    return "en"


def detect_reply_lang(text):
    if not text:
        return "en"
    if _DEVANAGARI_RE.search(text):
        return "hinglish"
    words = {w.lower() for w in _WORD_RE.findall(text)}
    return "hinglish" if len(words & _HINGLISH_WORDS) >= 2 else "en"


def greeting_for(customer, lang_key, name):
    """Apply the senior-citizen / grandparent override (D12 note) on top of
    GREET_CUSTOMER. Not a named function in PLAN §5.4, but the rule needs a
    home; app/playbook/customer.py (S3) calls this."""
    is_senior = bool((customer or {}).get("identity", {}).get("senior_citizen"))
    is_grandparent = "grandfather" in (name or "").lower()
    if is_senior or is_grandparent:
        return f"Namaste {name} ji"
    template = GREET_CUSTOMER.get(lang_key, "Hi {name}")
    return template.format(name=name)
