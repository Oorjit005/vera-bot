import re

from app.lang import CTA_EN, CTA_HI


def _lowered_first(s):
    if not s:
        return s
    # Leave acronyms/initialisms alone (DCI, IPL, ORS, DC vs MI...): only
    # lowercase when the opening word is normal Title Case, not all-caps.
    if len(s) >= 2 and s[0].isupper() and s[1].isupper():
        return s
    return s[0].lower() + s[1:]


def _dedup_sentences(sentences):
    seen_norms = []
    out = []
    for s in sentences:
        key = re.sub(r"\s+", " ", s.strip().lower()).rstrip(".")
        if key and any(key == prev or (len(key) > 12 and key in prev) for prev in seen_norms):
            continue
        if key:
            seen_norms.append(key)
        out.append(s)
    return out


def cta_sentence(brief):
    lang = brief.language
    use_hi = lang == "en+hi_cta" or lang in ("hinglish", "hindi")
    bank = CTA_HI if (use_hi and brief.cta in CTA_HI) else CTA_EN
    template = bank.get(brief.cta, "")
    if brief.cta == "open_ended":
        return (brief.cta_question or "").strip()
    if brief.cta == "multi_choice_slot":
        opts = ", ".join(brief.slot_options) if brief.slot_options else "1 or 2"
        return template.format(opts=opts)
    if brief.cta == "binary_yes_stop":
        return template.format(d=brief.deliverable or "it")
    if brief.cta == "binary_confirm_cancel":
        return template
    return ""


def _offer_line(brief):
    if not brief.offer:
        return None
    if brief.audience == "merchant":
        if brief.offer_is_suggestion:
            return f"Want me to list '{brief.offer}' on your profile?"
        return f"Your '{brief.offer}' is the right hook here."
    return f"{brief.offer} is on for you."


def render(brief, variant=0):
    cta = cta_sentence(brief)
    cta_is_question = "?" in cta

    ev_sentence = None
    if brief.evidence and brief.evidence[0]:
        ev_sentence = str(brief.evidence[0]).rstrip(".")
        if brief.source_citation:
            ev_sentence += f" ({brief.source_citation})"
        ev_sentence += "."

    jclause = brief.judgment or brief.merchant_anchor
    j_sentence = (str(jclause).rstrip(".") + ".") if jclause else None

    offer_line = _offer_line(brief)
    if offer_line and cta_is_question and "?" in offer_line:
        offer_line = None

    if brief.audience == "customer":
        opener = f"{brief.salutation}, {brief.sender_line}" if brief.sender_line else brief.salutation
        lead = [opener.rstrip(".") + ".", (brief.why_now or "").rstrip(".") + "."]
    else:
        opener = f"{brief.salutation}, {_lowered_first(brief.why_now or '')}"
        lead = [opener.rstrip(".") + "."]

    if variant == 0:
        middle = [s for s in (ev_sentence, j_sentence, offer_line) if s]
    else:
        middle = [s for s in (j_sentence, ev_sentence) if s]  # variant 1 drops the offer line

    parts = _dedup_sentences(lead + middle)
    if cta:
        parts.append(cta)
    body = " ".join(p for p in parts if p)
    return body, cta


def minimal(brief):
    cta = cta_sentence(brief)
    why = (brief.why_now or "").rstrip(".")
    if brief.audience == "customer":
        opener = f"{brief.salutation}, {brief.sender_line}" if brief.sender_line else brief.salutation
        body = f"{opener.rstrip('.')}. {why}."
    else:
        body = f"{brief.salutation}, {why}."
    if cta:
        body += f" {cta}"
    return body, cta
