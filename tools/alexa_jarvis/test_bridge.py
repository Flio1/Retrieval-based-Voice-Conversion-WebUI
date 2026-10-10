import os
from datetime import datetime, timezone
from tools.alexa_jarvis import bridge


def ev(cmd=None, uid="u1", kind="IntentRequest"):
    r = {"type": kind, "timestamp": datetime.now(timezone.utc).isoformat()}
    if cmd is not None:
        r["intent"] = {"name": "JarvisCommandIntent", "slots": {"command": {"value": cmd}}}
    return {"session": {"user": {"userId": uid}, "application": {"applicationId": "app"}}, "request": r}


def test_forward(monkeypatch):
    monkeypatch.setattr(bridge, "ask_jarvis", lambda c: "ok " + c)
    out = bridge.handle_alexa(ev("licht an"))
    assert out["response"]["outputSpeech"]["text"] == "ok licht an"


def test_blocked_and_launch():
    assert "nicht erlaubt" in bridge.ask_jarvis("shutdown pc")
    assert "bereit" in bridge.handle_alexa(ev(kind="LaunchRequest"))["response"]["outputSpeech"]["text"]


def test_validate(monkeypatch):
    monkeypatch.setenv("ALEXA_SKILL_ID", "app")
    monkeypatch.setenv("ALEXA_ALLOWED_USERS", "u1")
    assert bridge.validate(ev("x")) is None
    assert bridge.validate(ev("x", uid="evil")) == "user not allowed"
    monkeypatch.setenv("ALEXA_SKILL_ID", "other")
    assert bridge.validate(ev("x")) == "wrong skill id"
