import asyncio
import hashlib
import time

from app import config, templates
from app.playbook import build_brief
from app.validate import validate


def _variant_for(merchant_id: str, kind: str) -> int:
    h = hashlib.sha256(f"{merchant_id}{kind}".encode("utf-8")).hexdigest()
    return int(h, 16) % 2


async def compose(category, merchant, trigger, customer=None, now=None, conv_bodies=()):
    kind = (trigger or {}).get("kind", "")
    brief = build_brief(kind, category, merchant, trigger, customer, now)
    if brief.skip:
        return {"skip": brief.skip}

    cta_line = templates.cta_sentence(brief)
    template_name = ("vera_" if brief.audience == "merchant" else "merchant_") + brief.kind + "_v1"
    template_params = [brief.salutation, brief.why_now, brief.evidence[0] if brief.evidence else "",
                        brief.deliverable, cta_line]

    body = None
    rationale = None
    t0 = time.monotonic()
    try:
        from app import writer
        if config.LLM_ENABLED:
            text = writer.get_cached(brief)
            if text is None:
                text = await writer.write(brief)
            if text and isinstance(text, dict) and text.get("body"):
                errors = validate(text["body"], brief, conv_bodies)
                if not errors:
                    body = text["body"]
                    rationale = text.get("rationale") or brief.rationale()
                elif time.monotonic() - t0 < 4.0:
                    # PLAN §8 retry policy: one retry with the validator's
                    # complaints folded into the prompt, if there's still time.
                    retry_text = await writer.write(brief, extra_rules=", ".join(errors))
                    if retry_text and isinstance(retry_text, dict) and retry_text.get("body"):
                        retry_errors = validate(retry_text["body"], brief, conv_bodies)
                        if not retry_errors:
                            body = retry_text["body"]
                            rationale = retry_text.get("rationale") or brief.rationale()
    except ImportError:
        pass
    except Exception:
        pass

    if body is None:
        variant = _variant_for(brief.merchant_id, brief.kind)
        rendered_body, _ = templates.render(brief, variant)
        errors = validate(rendered_body, brief, conv_bodies)
        if errors:
            rendered_body, _ = templates.render(brief, 1 - variant)
            errors = validate(rendered_body, brief, conv_bodies)
        if errors:
            rendered_body, _ = templates.minimal(brief)
        body = rendered_body
        rationale = brief.rationale()

    return {
        "body": body, "cta": brief.cta, "send_as": brief.send_as,
        "suppression_key": brief.suppression_key, "rationale": rationale,
        "template_name": template_name, "template_params": template_params,
        "trigger_id": brief.trigger_id, "merchant_id": brief.merchant_id, "customer_id": brief.customer_id,
    }


def compose_sync(category, merchant, trigger, customer=None, now=None, conv_bodies=()):
    return asyncio.run(compose(category, merchant, trigger, customer, now, conv_bodies))


class _Precompose:
    def schedule_for(self, scope, context_id):
        try:
            from app.tick import precompose_schedule_for
            precompose_schedule_for(scope, context_id)
        except ImportError:
            pass
        except Exception:
            pass


precompose = _Precompose()
