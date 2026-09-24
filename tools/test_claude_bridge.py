import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import claude_bridge  # noqa: E402


class ScriptedChat:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def send(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


class FakeCoder:
    def __init__(self, fail=False):
        self.fail = fail
        self.instructions = []

    def send(self, instruction):
        self.instructions.append(instruction)
        if self.fail:
            raise RuntimeError("boom")
        return f"done: {instruction}"


class BridgeLoopTest(unittest.TestCase):
    def test_runs_until_done(self) -> None:
        chat = ScriptedChat(["Erstelle a.txt", "FERTIG – a.txt existiert"])
        coder = FakeCoder()
        res = claude_bridge.run_bridge("Ziel", chat, coder, max_rounds=5)
        self.assertTrue(res.done)
        self.assertEqual(coder.instructions, ["Erstelle a.txt"])
        self.assertIn("done: Erstelle a.txt", chat.prompts[1])
        self.assertIn("Verzeichnis: .", chat.prompts[0])

    def test_stops_at_max_rounds(self) -> None:
        chat = ScriptedChat(["x", "y"])
        res = claude_bridge.run_bridge("Ziel", chat, FakeCoder(), max_rounds=2)
        self.assertFalse(res.done)
        self.assertEqual(len(res.turns), 2)

    def test_coder_error_is_fed_back(self) -> None:
        chat = ScriptedChat(["x", "fertig"])
        res = claude_bridge.run_bridge("Ziel", chat, FakeCoder(fail=True))
        self.assertTrue(res.done)
        self.assertIn("FEHLER", res.turns[0].result)


class ClaudeCliTest(unittest.TestCase):
    def test_builds_argv_and_resumes_session(self) -> None:
        calls = []

        def runner(argv, cwd):
            calls.append((argv, cwd))
            return json.dumps({"result": "ok", "session_id": "s1", "is_error": False})

        cli = claude_bridge.ClaudeCli(["--tools", ""], cwd="/w", runner=runner)
        self.assertEqual(cli.send("hi"), "ok")
        cli.send("again")
        self.assertEqual(calls[0][0][:5], ["claude", "-p", "hi", "--output-format", "json"])
        self.assertNotIn("--resume", calls[0][0])
        self.assertEqual(calls[1][0][-2:], ["--resume", "s1"])
        self.assertEqual(calls[0][1], "/w")

    def test_error_result_raises(self) -> None:
        cli = claude_bridge.ClaudeCli(
            [], runner=lambda a, c: json.dumps({"result": "bad", "is_error": True})
        )
        with self.assertRaises(RuntimeError):
            cli.send("x")


class MainGuardTest(unittest.TestCase):
    def test_api_backend_requires_allow_paid(self) -> None:
        with self.assertRaises(SystemExit):
            claude_bridge.main(["goal", "--chat-backend", "api"])

    def test_bypass_permissions_not_allowed(self) -> None:
        with self.assertRaises(SystemExit):
            claude_bridge.main(["goal", "--permission-mode", "bypassPermissions"])


if __name__ == "__main__":
    unittest.main()
