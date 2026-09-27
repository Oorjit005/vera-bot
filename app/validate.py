import difflib
import re

GLOBAL_TABOO = {"guaranteed", "miracle", "best in city", "100% safe", "completely cure", "cure"}

URL_RE = re.compile(r"(https?://|www\.|\.com\b|\.in\b|bit\.ly)", re.IGNORECASE)
NUM_TOKEN_RE = re.compile(r"₹?\d[\d,]*(?:\.\d+)?%?")
PREAMBLE_RE = re.compile(r"hope you|i am reaching out|i'm reaching out|this is vera|vera here|my name is", re.IGNORECASE)
JARGON_WORDS_RE = re.compile(r"\b(placeholder|payload|trigger|suppression|signal|delta)\b", re.IGNORECASE)
DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
TIME_UNIT_RE = re.compile(r"^\s*(min|mins|minute|minutes|hr|hrs|hour|hours|sec)\b", re.IGNORECASE)
CTA_COMBINED_RE = re.compile(r"reply\s+yes|reply\s+confirm|reply\s+stop|reply\s+karein", re.IGNORECASE)
SLOT_REPLY_RE = re.compile(r"reply\s+\d", re.IGNORECASE)

# The 10 judge-scored anchor bodies from magicpin-ai-challenge/examples/case-studies.md.
# Near-duplicates of these are penalized as plagiarism (PLAN §9 rule 11).
CASE_STUDY_BODIES = [
    "Dr. Meera, JIDA's Oct issue landed. One item relevant to your high-risk adult "
    "patients — 2,100-patient trial showed 3-month fluoride recall cuts caries "
    "recurrence 38% better than 6-month. Worth a look (2-min abstract). Want me "
    "to pull it + draft a patient-ed WhatsApp you can share? — JIDA Oct 2026 p.14",

    "Hi Priya, Dr. Meera's clinic here \U0001f9b7 It's been 5 months since your last visit "
    "— your 6-month cleaning recall is due. Apke liye 2 slots ready hain: Wed 5 "
    "Nov, 6pm ya Thu 6 Nov, 5pm. ₹299 cleaning + complimentary fluoride. Reply 1 "
    "for Wed, 2 for Thu, or tell us a time that works.",

    "Hi Kavya \U0001f48d Lakshmi from Studio11 Kapra here. 196 days to your wedding — perfect "
    "window to start the 30-day skin-prep program before serious bridal bookings "
    "roll in. ₹2,499 covers 4 sessions + a take-home kit. Want me to block your "
    "preferred Saturday 4pm slot for the first session next week?",

    "Hi Lakshmi! Quick check — what service has been most asked-for this week "
    "at Studio11? I'll turn the answer into a Google post + a 4-line WhatsApp "
    "reply you can use when customers ask about pricing. Takes 5 min.",

    "Quick heads-up Suresh — DC vs MI at Arun Jaitley tonight, 7:30pm. Important: "
    "Saturday IPL matches usually shift -12% restaurant covers (people watch at "
    "home). Skip the match-night promo today; instead push your BOGO pizza "
    "(already active) as a delivery-only Saturday special. Want me to draft the "
    "Swiggy banner + an Insta story? Live in 10 min.",

    "Suresh, here's a starter version — you can edit: Mylari Corporate Thali — for "
    "offices in Indiranagar - 10 thalis @ ₹125 each (₹25 off retail) + free delivery "
    "- 25 thalis @ ₹115 each + 2 free filter coffees - 50+: ₹105 each + 1 free dosa "
    "platter - WhatsApp the day-before by 5pm; we deliver between 12:30-1pm 3 "
    "offices in Indiranagar are in your delivery radius (Embassy Tech, RMZ Eco, "
    "Sigma Soft). Want me to draft a 3-line WhatsApp to send their facilities managers?",

    "Karthik, your views are down 30% this week — but I want to flag this is the "
    "normal April-June acquisition lull (every metro gym sees -25 to -35% in this "
    "window). Action: skip ad spend now, save it for Sept-Oct when conversion is "
    "2x. For now, focus retention on your 245 members. Want me to draft a "
    "\"summer attendance challenge\" to keep them through the dip?",

    "Hi Rashmi \U0001f44b Karthik from PowerHouse here. It's been about 8 weeks — happens "
    "to most members at some point, no judgment. We've added a Tue/Thu evening "
    "HIIT class that fits weight-loss goals well (45 min, 6:30pm). Want me to "
    "hold a free trial spot for you next Tue, 30 Apr? Reply YES — no commitment, no auto-charge.",

    "Ramesh, urgent: voluntary recall on 2 atorvastatin batches (AT2024-1102, "
    "AT2024-1108) by Mfr Z — sub-potency, no safety risk, but customers should be "
    "informed for replacement. Pulled your repeat-Rx list: 22 of your chronic-Rx "
    "customers were dispensed these batches in last 90 days. Want me to draft "
    "their WhatsApp note + the replacement-pickup workflow?",

    "Namaste — Apollo Health Plus Malviya Nagar yahan. Sharma ji ki 3 monthly "
    "medicines (metformin, atorvastatin, telmisartan) 28 April ko khatam hongi. "
    "Same dose, same brand pack ready hai. Senior discount 15% applied — total "
    "₹1,420 (₹240 saved). Free home delivery to saved address by 5pm tomorrow. "
    "Reply CONFIRM to dispatch, or call 9876543210 if any change in dosage.",
]


def _normalize_num(tok: str) -> str:
    t = tok.replace("₹", "").replace("%", "").replace(",", "")
    if t.endswith(".0"):
        t = t[:-2]
    return t


def _brief_allowed_numbers(brief):
    texts = [brief.why_now or "", brief.deliverable or ""]
    texts.extend(brief.evidence or [])
    for extra in (brief.merchant_anchor, brief.judgment, brief.offer, brief.cta_question,
                  brief.source_citation, brief.salutation, brief.sender_line):
        if extra:
            texts.append(str(extra))
    texts.extend(brief.slot_options or [])
    texts.extend(brief.facts_text or [])
    allowed = set()
    for t in texts:
        for m in NUM_TOKEN_RE.findall(t):
            allowed.add(_normalize_num(m))
    return allowed


def _salutation_numbers(brief):
    nums = set()
    if brief.salutation:
        for m in NUM_TOKEN_RE.findall(brief.salutation):
            nums.add(_normalize_num(m))
    return nums


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def check_length(body):
    if not body or not body.strip():
        return ["EMPTY"]
    if len(body) > 700:
        return ["TOO_LONG"]
    return []


def check_url(body):
    return ["URL"] if URL_RE.search(body) else []


def check_taboo(body, brief):
    errors = []
    taboo_words = set(brief.taboo or []) | GLOBAL_TABOO
    body_lower = body.lower()
    for w in sorted(taboo_words):
        pattern = r"\b" + re.escape(w.lower()) + r"\b"
        if re.search(pattern, body_lower):
            errors.append(f"TABOO:{w}")
    return errors


def check_ungrounded(body, brief):
    errors = []
    allowed = _brief_allowed_numbers(brief)
    salutation_nums = _salutation_numbers(brief)
    for m in NUM_TOKEN_RE.finditer(body):
        tok = m.group(0)
        norm = _normalize_num(tok)
        if not norm:
            continue
        if norm in salutation_nums:
            continue
        start, end = m.span()
        try:
            val = float(norm)
        except ValueError:
            val = None
        after = body[end:end + 12]
        if val is not None and val <= 60 and TIME_UNIT_RE.match(after):
            continue
        before = body[max(0, start - 10):start]
        if norm in ("1", "2", "3") and re.search(r"reply\s*$", before, re.IGNORECASE):
            continue
        if norm in allowed:
            continue
        errors.append(f"UNGROUNDED:{tok}")
    return errors


def check_salutation_present(body, brief):
    sal = (brief.salutation or "").strip()
    if not sal:
        return []
    name_part = sal
    changed = True
    while changed:
        changed = False
        for p in ("Hi ", "Namaste ", "Vanakkam ", "Namaskaram ", "Namaskara ", "Dr. "):
            if name_part.startswith(p):
                name_part = name_part[len(p):]
                changed = True
        for suf in (" team", " ji"):
            if name_part.endswith(suf):
                name_part = name_part[: -len(suf)]
                changed = True
    name_part = name_part.strip()
    if not name_part:
        return []
    return [] if name_part.lower() in body.lower() else ["NO_SALUTATION"]


def check_multi_cta(body, brief):
    body_lower = body.lower()
    count = len(CTA_COMBINED_RE.findall(body_lower))
    if brief.cta == "multi_choice_slot" and SLOT_REPLY_RE.search(body_lower):
        count += 1
    return ["MULTI_CTA"] if count > 1 else []


def _last_sentence(body):
    body = body.strip()
    if not body:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", body)
    parts = [p for p in parts if p.strip()]
    return parts[-1] if parts else body


def check_cta_not_last(body, brief):
    if brief.cta == "none":
        return []
    last = _last_sentence(body)
    if "?" in last:
        return []
    if re.search(r"\b(Reply|CONFIRM|YES)\b", last, re.IGNORECASE):
        return []
    return ["CTA_NOT_LAST"]


def check_preamble(body):
    return ["PREAMBLE"] if PREAMBLE_RE.search(body) else []


def check_jargon(body):
    if "_" in body:
        return ["JARGON"]
    return ["JARGON"] if JARGON_WORDS_RE.search(body) else []


def check_repeat(body, conv_bodies):
    norm = _norm_ws(body)
    for b in conv_bodies or ():
        if _norm_ws(b) == norm:
            return ["REPEAT"]
    return []


def check_plagiarism(body):
    body_lower = body.lower()
    for cs in CASE_STUDY_BODIES:
        ratio = difflib.SequenceMatcher(None, body_lower, cs.lower()).ratio()
        if ratio >= 0.55:
            return ["PLAGIARISM"]
    return []


def check_devanagari(body):
    return ["DEVANAGARI"] if DEVANAGARI_RE.search(body) else []


def check_action_mode(body, reply_mode):
    if reply_mode != "action":
        return []
    errors = []
    body_lower = body.lower()
    if re.search(r"would you|do you|can you tell|what if|how about", body_lower):
        errors.append("QUALIFYING")
    if not re.search(r"\b(done|sending|draft|here|confirm|proceed|next)\b", body_lower):
        errors.append("NO_ACTION_WORD")
    return errors


def validate_reply(body, reply_mode=None, conv_bodies=()):
    """Brief-independent subset of `validate` for reply-turn bodies, where
    there is no Brief (category taboo/vocab, grounding facts) to check
    against. Used to sanity-check LLM-written replies before accepting them."""
    if body is None:
        return ["EMPTY"]
    errors = check_length(body)
    if "EMPTY" in errors:
        return errors
    errors += check_url(body)
    body_lower = body.lower()
    for w in sorted(GLOBAL_TABOO):
        if re.search(r"\b" + re.escape(w) + r"\b", body_lower):
            errors.append(f"TABOO:{w}")
    errors += check_preamble(body)
    errors += check_jargon(body)
    errors += check_repeat(body, conv_bodies)
    errors += check_plagiarism(body)
    errors += check_devanagari(body)
    errors += check_action_mode(body, reply_mode)
    return errors


def validate(body, brief, conv_bodies=(), reply_mode=None):
    if body is None:
        return ["EMPTY"]
    errors = check_length(body)
    if "EMPTY" in errors:
        return errors
    errors += check_url(body)
    errors += check_taboo(body, brief)
    errors += check_ungrounded(body, brief)
    errors += check_salutation_present(body, brief)
    errors += check_multi_cta(body, brief)
    errors += check_cta_not_last(body, brief)
    errors += check_preamble(body)
    errors += check_jargon(body)
    errors += check_repeat(body, conv_bodies)
    errors += check_plagiarism(body)
    errors += check_devanagari(body)
    errors += check_action_mode(body, reply_mode)
    return errors
