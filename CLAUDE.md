# Vera Bot — Agent rules (copied verbatim from PLAN.md §A)

1. Python 3.12. Only these dependencies: `fastapi`, `uvicorn[standard]`, `pytest`, `pytest-asyncio`. Nothing else, and no pydantic models at the API boundary. The writer (`app/writer.py`) calls the Gemini REST API directly over stdlib `urllib`, so no SDK dependency is needed. (Originally spec'd for `claude-sonnet-5` via the `anthropic` SDK; switched to Gemini's free API per the user's later instruction.)
2. **Never invent data in the bot's output.** Every number, name, date, price or source in a message must come from the pushed contexts or from a value registered through `FactSet.derive()`.
3. **Never let an endpoint crash or time out.** Every route has a try/except returning the documented fallback shape (§4).
4. Deterministic code everywhere except the single LLM call in `app/writer.py`. Sort dict keys, sort lists before iterating, and never use `random` or `datetime.now()` inside composition. Time comes from the `now` argument.
5. Whenever you run Python on Windows, set `PYTHONUTF8=1` first.
6. Use ASCII quotes in code. Use Roman-script Hinglish; never Devanagari.
7. If a spec detail is ambiguous, choose the **more conservative** option (send less, claim less) and add a `# SPEC-GAP:` comment.
8. Don't change the files in `magicpin-ai-challenge/` except the config block of `judge_simulator.py` (§11.2).
9. After every session, `pytest -q` must pass fully. Commit with the message `S<N>: <summary>`.
