"""Alexa -> JARVIS bridge: gives Alexa voice access to JARVIS commands.

Run:  python -m tools.alexa_jarvis.bridge   (needs HTTPS in front, e.g. ngrok/Lambda)
Env:
  ALEXA_SKILL_ID      required in prod: only requests for this skill are accepted
  ALEXA_ALLOWED_USERS comma-separated Alexa userIds allowed to command JARVIS (empty = all)
  JARVIS_URL          POST {"command": str} -> {"reply": str}   (HTTP mode)
  JARVIS_MODULE       python module exposing handle_command(str)->str (default: jarvis_gemini)
  JARVIS_BLOCKED      comma-separated words that are never forwarded (default: shutdown,format,delete)
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

log = logging.getLogger("alexa_jarvis")
MAX_AGE_S = 150  # Alexa requires rejecting requests older than 150s


def _speech(text: str, end: bool = False, reprompt: str | None = None) -> dict[str, Any]:
    res: dict[str, Any] = {"outputSpeech": {"type": "PlainText", "text": text[:7000]},
                           "shouldEndSession": end}
    if reprompt:
        res["reprompt"] = {"outputSpeech": {"type": "PlainText", "text": reprompt}}
    return {"version": "1.0", "response": res}


def ask_jarvis(command: str) -> str:
    """Forward a spoken command to JARVIS (HTTP if JARVIS_URL set, else local module)."""
    blocked = [w for w in os.getenv("JARVIS_BLOCKED", "shutdown,format,delete").split(",") if w]
    if any(w in command.lower() for w in blocked):
        return "Dieser Befehl ist per Sprache nicht erlaubt."
    url = os.getenv("JARVIS_URL")
    if url:
        req = urllib.request.Request(url, json.dumps({"command": command}).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return str(json.load(r).get("reply", "Erledigt."))
    mod = importlib.import_module(os.getenv("JARVIS_MODULE", "jarvis_gemini"))
    return str(mod.handle_command(command))


def validate(body: dict[str, Any], now: datetime | None = None) -> str | None:
    """Return an error string if the request must be rejected, else None."""
    sess = body.get("session", {})
    skill = os.getenv("ALEXA_SKILL_ID")
    if skill and sess.get("application", {}).get("applicationId") != skill:
        return "wrong skill id"
    allowed = [u for u in os.getenv("ALEXA_ALLOWED_USERS", "").split(",") if u]
    if allowed and sess.get("user", {}).get("userId") not in allowed:
        return "user not allowed"
    ts = body.get("request", {}).get("timestamp")
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return "bad timestamp"
    if abs(((now or datetime.now(timezone.utc)) - t).total_seconds()) > MAX_AGE_S:
        return "stale request"
    return None


def handle_alexa(body: dict[str, Any]) -> dict[str, Any]:
    req = body.get("request", {})
    kind = req.get("type")
    if kind == "LaunchRequest":
        return _speech("Jarvis bereit. Was soll ich tun?", reprompt="Was soll ich tun?")
    if kind == "SessionEndedRequest":
        return _speech("", end=True)
    if kind == "IntentRequest":
        name = req.get("intent", {}).get("name")
        if name in ("AMAZON.StopIntent", "AMAZON.CancelIntent"):
            return _speech("Bis später.", end=True)
        if name == "JarvisCommandIntent":
            cmd = (req["intent"].get("slots", {}).get("command", {}).get("value") or "").strip()
            if not cmd:
                return _speech("Das habe ich nicht verstanden.", reprompt="Was soll ich tun?")
            try:
                return _speech(ask_jarvis(cmd), reprompt="Noch etwas?")
            except Exception:
                log.exception("JARVIS failed")
                return _speech("Jarvis ist gerade nicht erreichbar.")
    return _speech("Das kann ich nicht.")


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            err = validate(body)
            out = {"error": err} if err else handle_alexa(body)
            code = 403 if err else 200
        except Exception:
            out, code = {"error": "bad request"}, 400
        data = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entry (Alexa verifies signatures itself for Lambda triggers)."""
    err = validate(event)
    return _speech("Nicht erlaubt.", end=True) if err else handle_alexa(event)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), _Handler).serve_forever()
