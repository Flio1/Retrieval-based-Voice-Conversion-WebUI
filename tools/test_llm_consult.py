import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_consult  # noqa: E402


def fake_post(url, headers, body):
    if "googleapis" in url:
        assert headers == {"x-goog-api-key": "g-key"}
        return {"candidates": [{"content": {"parts": [{"text": "gemini says hi"}]}}]}
    assert headers == {"Authorization": "Bearer o-key"}
    return {"choices": [{"message": {"content": "gpt says hi"}}]}


def failing_post(url, headers, body):
    raise urllib.error.URLError("blocked")


ENV = {"GEMINI_API_KEY": "g-key", "OPENAI_API_KEY": "o-key"}


class LlmConsultTest(unittest.TestCase):
    def test_gemini_answers(self) -> None:
        res = llm_consult.consult("q", ["gemini"], env=ENV, post=fake_post)
        self.assertEqual(res["gemini"], {"ok": True, "text": "gemini says hi"})

    def test_openai_blocked_without_allow_paid(self) -> None:
        res = llm_consult.consult("q", ["openai"], env=ENV, post=fake_post)
        self.assertFalse(res["openai"]["ok"])
        self.assertIn("--allow-paid", res["openai"]["error"])

    def test_openai_with_allow_paid(self) -> None:
        res = llm_consult.consult("q", ["openai"], allow_paid=True, env=ENV, post=fake_post)
        self.assertEqual(res["openai"]["text"], "gpt says hi")

    def test_missing_key(self) -> None:
        res = llm_consult.consult("q", ["gemini"], env={}, post=fake_post)
        self.assertEqual(res["gemini"]["error"], "GEMINI_API_KEY not set")

    def test_network_error_is_reported(self) -> None:
        res = llm_consult.consult("q", ["gemini"], env=ENV, post=failing_post)
        self.assertFalse(res["gemini"]["ok"])
        self.assertIn("URLError", res["gemini"]["error"])


if __name__ == "__main__":
    unittest.main()
