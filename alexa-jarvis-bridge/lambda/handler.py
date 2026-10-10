"""Alexa -> JARVIS voice bridge: core request handler.

Framework-free (Python standard library only) so it runs unchanged on AWS Lambda
or behind a self-hosted HTTP endpoint. The single job of this module is:

    Alexa JSON request  ->  forward spoken text to JARVIS  ->  Alexa JSON response

Configuration is read from environment variables (see .env.example):
    JARVIS_ENDPOINT   (required)  URL of the JARVIS HTTP endpoint
    JARVIS_API_KEY    (optional)  sent as "Authorization: Bearer <key>"
    JARVIS_TIMEOUT    (optional)  seconds before giving up (default 7)
    ALEXA_SKILL_ID    (optional)  if set, only requests from this skill are accepted
"""

import json
import os
import urllib.error
import urllib.request

# Spoken strings (German, matching the de-DE interaction model).
MSG_WELCOME = "Hi, ich bin die Brücke zu JARVIS. Was soll ich ihn fragen?"
MSG_REPROMPT = "Was soll ich JARVIS sagen?"
MSG_HELP = (
    "Sag einfach, was JARVIS tun soll. Zum Beispiel: "
    "frag nach dem Wetter, oder: sag ihm, er soll das Licht anschalten."
)
MSG_BYE = "Bis später."
MSG_EMPTY = "Ich habe nichts verstanden. Was soll ich JARVIS fragen?"
MSG_UNREACHABLE = "Ich konnte JARVIS gerade nicht erreichen. Versuch es gleich nochmal."
MSG_FORBIDDEN = "Dieser Skill ist nicht für diese Anfrage freigegeben."


class _Forbidden(Exception):
    """Raised when the incoming request is not from the allow-listed skill."""


def handle_alexa_request(event):
    """Entry point. Takes a parsed Alexa request dict, returns a response dict."""
    try:
        _verify_skill_id(event)
    except _Forbidden:
        return _response(MSG_FORBIDDEN, end=True)

    request = (event or {}).get("request", {})
    rtype = request.get("type")

    if rtype == "LaunchRequest":
        return _response(MSG_WELCOME, reprompt=MSG_REPROMPT)

    if rtype == "SessionEndedRequest":
        # No spoken response is allowed for SessionEndedRequest.
        return {"version": "1.0", "response": {}}

    if rtype == "IntentRequest":
        return _handle_intent(event, request)

    # Unknown request type: stay graceful.
    return _response(MSG_WELCOME, reprompt=MSG_REPROMPT)


def _handle_intent(event, request):
    intent = request.get("intent", {}) or {}
    name = intent.get("name")

    if name in ("AMAZON.StopIntent", "AMAZON.CancelIntent"):
        return _response(MSG_BYE, end=True)

    if name == "AMAZON.HelpIntent":
        return _response(MSG_HELP, reprompt=MSG_REPROMPT)

    # AskJarvisIntent and AMAZON.FallbackIntent both forward whatever was said.
    text = _extract_text(intent)
    if not text:
        return _response(MSG_EMPTY, reprompt=MSG_REPROMPT)

    try:
        reply, end = _ask_jarvis(text, _meta(event, name))
    except Exception:  # network error, bad JSON, timeout, misconfig...
        return _response(MSG_UNREACHABLE, reprompt=MSG_REPROMPT)

    if not reply:
        reply = "JARVIS hat keine Antwort geschickt."
    return _response(reply, end=end, reprompt=None if end else MSG_REPROMPT)


def _extract_text(intent):
    """Pull the free-text SearchQuery slot value out of the intent."""
    slots = intent.get("slots") or {}
    query = slots.get("query") or {}
    value = (query.get("value") or "").strip()
    return value


def _meta(event, intent_name):
    session = (event or {}).get("session", {}) or {}
    request = (event or {}).get("request", {}) or {}
    return {
        "locale": request.get("locale", "de-DE"),
        "session_id": session.get("sessionId"),
        "intent": intent_name,
    }


def _ask_jarvis(text, meta):
    """POST the utterance to JARVIS and return (reply_text, end_session_bool)."""
    endpoint = os.environ.get("JARVIS_ENDPOINT")
    if not endpoint:
        raise RuntimeError("JARVIS_ENDPOINT is not configured")

    payload = json.dumps(
        {
            "text": text,
            "source": "alexa",
            "locale": meta.get("locale"),
            "session_id": meta.get("session_id"),
            "intent": meta.get("intent"),
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    api_key = os.environ.get("JARVIS_API_KEY")
    if api_key:
        req.add_header("Authorization", "Bearer " + api_key)

    timeout = float(os.environ.get("JARVIS_TIMEOUT", "7"))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")

    body = json.loads(raw) if raw else {}
    reply = body.get("reply") or body.get("speech") or body.get("text")
    end = bool(body.get("end_session", False))
    return reply, end


def _verify_skill_id(event):
    expected = os.environ.get("ALEXA_SKILL_ID")
    if not expected:
        return
    got = (
        (event or {})
        .get("context", {})
        .get("System", {})
        .get("application", {})
        .get("applicationId")
    )
    if not got:
        got = (
            (event or {})
            .get("session", {})
            .get("application", {})
            .get("applicationId")
        )
    if got != expected:
        raise _Forbidden()


def _response(speech, end=False, reprompt=None):
    out = {
        "version": "1.0",
        "response": {
            "outputSpeech": {"type": "PlainText", "text": speech},
            "shouldEndSession": bool(end),
        },
    }
    if reprompt:
        out["response"]["reprompt"] = {
            "outputSpeech": {"type": "PlainText", "text": reprompt}
        }
    return out
