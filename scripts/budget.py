"""Print writer LLM usage from out/llm_usage.jsonl. Gemini free tier: $0 either way."""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(_HERE, "..", "out", "llm_usage.jsonl")


def main():
    if not os.path.exists(LOG_PATH):
        print(f"No usage log at {LOG_PATH} (writer not called yet, or LLM disabled).")
        return
    calls = 0
    prompt_tokens = 0
    output_tokens = 0
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            calls += 1
            usage = row
            prompt_tokens += usage.get("promptTokenCount", 0) or 0
            output_tokens += usage.get("candidatesTokenCount", 0) or 0

    print(f"Writer calls: {calls}")
    print(f"Prompt tokens: {prompt_tokens}")
    print(f"Output tokens: {output_tokens}")
    print("Provider: Gemini free tier -> $0.00")


if __name__ == "__main__":
    main()
