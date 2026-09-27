import re

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]+", flags=re.UNICODE
)

HOSTILE_RE = re.compile(
    r"\bstop\b|unsubscribe|don'?t (message|text|contact)|do not message|stop sending|"
    r"\bspam\b|\buseless\b|bothering|harass|\bblock\b|mat bhej|band karo|pareshan|bakwas|"
    r"\bidiot\b|\bstupid\b|\bnonsense\b|shut up|\bbloody\b|\bdamn\b",
    re.IGNORECASE,
)
AUTO_REPLY_RE = re.compile(
    r"thank(s| you) for (contacting|reaching|your message)|"
    r"our team will (get back|respond|contact|reach)|will get back to you|"
    r"we are (currently )?(unavailable|closed|away)|business hours|"
    r"automated (assistant|message|reply|response)|auto-?reply|"
    r"aapki jaankari ke liye|team tak pahuncha|shukriya.*sampark",
    re.IGNORECASE,
)
NOT_INTERESTED_RE = re.compile(
    r"not interested|no thanks|nahi chahiye|interest nahi|we don'?t need|zarurat nahi|no need",
    re.IGNORECASE,
)
LATER_RE = re.compile(r"\bbusy\b|\blater\b|call me later|\btomorrow\b|baad mein|abhi nahi|kal baat", re.IGNORECASE)
LATER_TOMORROW_RE = re.compile(r"\btomorrow\b|\bkal\b", re.IGNORECASE)
ACCEPT_RE = re.compile(
    r"^(yes|haan|ha|ok|okay|sure|yep|yup|done|confirm|1|2)\b|"
    r"go ahead|let'?s do it|lets do it|\bdo it\b|\bproceed\b|please do|sounds good|"
    r"chalega|kar do|\bkaro\b|bhej do|theek hai|\binterested\b|\bjoin\b|judna|sign me up|"
    r"what'?s next|whats next|send (it|me)",
    re.IGNORECASE,
)
OFF_TOPIC_RE = re.compile(
    r"\bgst\b|income tax|\btax\b|\bitr\b|\bloan\b|\bca\b|chartered accountant|"
    r"\blawyer\b|\blegal\b|\bvisa\b|\binsurance\b|\bpassport\b|electricity bill",
    re.IGNORECASE,
)
QUESTION_START_RE = re.compile(
    r"^(what|how|why|when|where|which|who|kya|kaise|kitna|kitne|kab|kaun|can|is|are|does)\b",
    re.IGNORECASE,
)
THANKS_RE = re.compile(r"thanks|thank you|\bthx\b|dhanyavad|shukriya|noted|\U0001F44D|ok thanks", re.IGNORECASE)


def _normalize(text):
    text = text or ""
    text = _EMOJI_RE.sub("", text)
    return re.sub(r"\s+", " ", text.strip().lower())


def classify(text, merchant_state=None, from_role="merchant"):
    norm = _normalize(text)
    if not norm:
        return "other"

    if HOSTILE_RE.search(norm):
        return "hostile_optout"

    if AUTO_REPLY_RE.search(norm):
        return "auto_reply"
    if merchant_state is not None and merchant_state.autoreply_texts.get(norm, 0) >= 1:
        return "auto_reply"

    if NOT_INTERESTED_RE.search(norm):
        return "not_interested"

    if LATER_RE.search(norm):
        return "later"

    if ACCEPT_RE.search(norm):
        return "accept"

    if OFF_TOPIC_RE.search(norm):
        return "off_topic"

    if "?" in norm or QUESTION_START_RE.search(norm):
        return "question"

    if len(norm.split()) <= 5 and THANKS_RE.search(norm):
        return "thanks_ack"

    return "other"


def later_wait_seconds(text):
    norm = _normalize(text)
    return 86400 if LATER_TOMORROW_RE.search(norm) else 14400
