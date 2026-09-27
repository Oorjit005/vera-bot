---
title: Vera Bot
emoji: 💬
colorFrom: green
colorTo: gray
sdk: docker
app_port: 8080
pinned: false
---

# Vera Bot

WhatsApp merchant-growth assistant for magicpin's AI challenge. `POST /v1/context`,
`POST /v1/tick`, `POST /v1/reply`, `GET /v1/healthz`, `GET /v1/metadata`.

## Approach

A two-stage composer, not a single prompt:

1. **Brief** (`app/facts.py` + `app/playbook/*`) — deterministic code picks the fact,
   the judgment, the offer, the deliverable and the CTA from the pushed category/
   merchant/trigger/customer context. This is the "decision" the judge scores, and
   it's fully auditable: same input always produces the same Brief.
2. **Writer** (`app/writer.py`) — Gemini phrases the Brief into a WhatsApp message.
   It cannot add facts; the prompt restricts it to `Brief.facts_text` and friends.
3. **Validator** (`app/validate.py`) — checks every number in the output against a
   registry built from the actual pushed contexts, plus taboo words, URLs, CTA
   placement, repetition, and near-duplicates of the 10 published case studies.
4. **Template fallback** (`app/templates.py`) — a deterministic sentence-assembly
   renderer from the same Brief. If the writer is disabled, times out, or its
   output fails validation, this renders the message instead. It's good enough to
   submit on its own, which is what most of this build was tested against.

Replies (`app/reply/`) are a rules-first classifier (auto-reply detection keyed per
merchant so it survives the judge's conversation-ID-per-turn scenario, accept/intent
transition, hostile/off-topic, thanks) over a small state machine, with the writer as
an optional upgrade for the "answer"/"action"/"offtopic" reply modes and a
deterministic fallback for each.

## Model choice

**Gemini** (`gemini-2.0-flash` by default, `WRITER_MODEL` env override) via the plain
REST API over stdlib `urllib` — no SDK dependency. The build spec originally called
for Claude Sonnet 5; it was switched to Gemini's free tier partway through so the
bot has zero per-message cost. Since the decision logic lives entirely in the
deterministic Brief, the writer is replaceable by design — swapping providers only
touched `app/writer.py` and `app/config.py`.

## Tradeoffs

- **In-memory state, 1 worker.** Simplest correct choice for a single evaluation
  window; a restart loses conversation history, so the Space is never redeployed
  during evaluation.
- **Templates as the real safety net, not a fig leaf.** Every one of the 100
  expanded triggers composes to either an explicit skip-with-reason or a
  zero-validation-error template body (`tests/test_compose_all.py`). The writer is
  a quality upgrade on top, not a dependency.
- **Output cache keyed on `sha256(brief_json + prompt_version)`.** Gemini isn't
  pinned to temperature 0 either, so determinism for repeated identical Briefs
  comes from the cache, matching what the spec's precompose-on-push design assumes.
- **Precompose on context push, cache read on tick.** `/v1/context` has a 5s budget
  and `/v1/tick` a 10s one; warming the writer cache in the background when a
  trigger (or its merchant/category) is pushed means tick usually just reads a
  cache hit.
- **Reply fallbacks lack a live Brief.** Keyword-based answers ("I'll share the
  price...") are conservative placeholders when the writer is off, since the reply
  endpoint doesn't carry the original trigger's Brief forward. Wiring
  `Conversation.brief_summary` with the original facts would sharpen these.

## What extra context would help

- Real slot inventory instead of only the 1-2 slots a trigger happens to include.
- Per-service demand data (which service, not just which category, is trending).
- A live competitor feed — the current data intentionally never invents a
  competitor, so `competitor_opened` on generated (placeholder) merchants falls
  back to a peer-benchmark framing instead.
- The merchant's actual reply history, to personalize levers beyond category
  defaults (e.g., which CTA style a specific merchant tends to act on).
