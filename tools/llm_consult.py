"""Ask Gemini and/or ChatGPT for a second opinion.

Keys are read from the environment only (never from files or arguments):
    GEMINI_API_KEY  - Google AI Studio key (free tier available)
    OPENAI_API_KEY  - OpenAI key (always billed per token)

Cost guard: OpenAI is only called with --allow-paid, because every OpenAI API
call costs money. Gemini is called by default (free-tier model).

Usage:
    python tools/llm_consult.py "Frage" [--provider gemini|openai|all] [--allow-paid]

Output: JSON {provider: {"ok": bool, "text"|"error": str}}. Exit code 0 if at
least one provider answered, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Callable, Dict, Optional, Sequence

logger = logging.getLogger("llm_consult")

GEMINI_MODEL = "gemini-2.5-flash"
OPENAI_MODEL = "gpt-4o-mini"
TIMEOUT_S = 60

# (url, headers, body) -> parsed JSON response; injectable for tests.
Transport = Callable[[str, Dict[str, str], dict], dict]


def http_post(url: str, headers: Dict[str, str], body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask_gemini(prompt: str, key: str, post: Transport = http_post) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    data = post(url, {"x-goog-api-key": key}, {"contents": [{"parts": [{"text": prompt}]}]})
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def ask_openai(prompt: str, key: str, post: Transport = http_post) -> str:
    data = post(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {"model": OPENAI_MODEL, "messages": [{"role": "user", "content": prompt}]},
    )
    return data["choices"][0]["message"]["content"]


def consult(
    prompt: str,
    providers: Sequence[str],
    allow_paid: bool = False,
    env: Optional[Dict[str, str]] = None,
    post: Transport = http_post,
) -> Dict[str, dict]:
    env = os.environ if env is None else env
    table = {
        "gemini": ("GEMINI_API_KEY", ask_gemini, False),
        "openai": ("OPENAI_API_KEY", ask_openai, True),
    }
    results: Dict[str, dict] = {}
    for name in providers:
        var, fn, paid = table[name]
        if paid and not allow_paid:
            results[name] = {"ok": False, "error": "skipped: paid API, pass --allow-paid"}
            continue
        key = env.get(var)
        if not key:
            results[name] = {"ok": False, "error": f"{var} not set"}
            continue
        try:
            results[name] = {"ok": True, "text": fn(prompt, key, post)}
        except (urllib.error.URLError, KeyError, IndexError, ValueError, OSError) as exc:
            logger.warning("%s failed: %s", name, exc)
            results[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prompt")
    parser.add_argument("--provider", choices=["gemini", "openai", "all"], default="gemini")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
    providers = ["gemini", "openai"] if args.provider == "all" else [args.provider]
    results = consult(args.prompt, providers, args.allow_paid)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if any(r["ok"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
