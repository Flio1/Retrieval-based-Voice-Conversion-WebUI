"""Let a Claude chat (planner/reviewer) and Claude Code (executor) work together.

Loop: the chat side gets the goal and writes one instruction for Claude Code.
Claude Code executes it (with file/shell tools) and its result goes back to the
chat side, which reviews it and writes the next instruction - until the chat
side answers with the DONE marker or --max-rounds is reached.

Chat backends:
    cli (default) - `claude -p --tools ""`: a plain chat without tools, billed
                    like normal Claude Code usage (your subscription login).
    api           - Anthropic Messages API via the `anthropic` SDK. Billed per
                    token, so it needs --allow-paid and ANTHROPIC_API_KEY.

Safety: Claude Code runs with --permission-mode default unless you pass another
mode; in print mode, tool calls that need approval are denied instead of run.
Nothing here opens a port or accepts remote input.

Usage:
    python tools/claude_bridge.py "Ziel" [--cwd DIR] [--max-rounds 5]
        [--permission-mode default|acceptEdits|plan] [--chat-backend cli|api]
        [--allow-paid] [--transcript out.json]

Exit code: 0 if the chat side declared the goal done, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

logger = logging.getLogger("claude_bridge")

DONE = "FERTIG"
API_MODEL = "claude-opus-5"
SAFE_PERMISSION_MODES = ("default", "acceptEdits", "plan")

CHAT_SYSTEM = (
    "Du bist der Planer und Reviewer. Ein zweiter Agent (Claude Code) hat Zugriff auf "
    "Dateien und Shell und führt deine Anweisungen aus. Antworte jedes Mal mit GENAU EINER "
    "konkreten, überprüfbaren Anweisung für Claude Code. Prüfe dessen Ergebnis kritisch. "
    f"Wenn das Ziel erreicht ist, antworte nur mit '{DONE}' und einer kurzen Zusammenfassung. "
    "Gib nie Anweisungen, die Geld kosten, Zugangsdaten preisgeben oder Fernzugriff öffnen."
)

# (argv, cwd) -> stdout; injectable for tests.
Runner = Callable[[List[str], Optional[str]], str]


def run_subprocess(argv: List[str], cwd: Optional[str]) -> str:
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(f"{argv[0]} exited {proc.returncode}: {proc.stderr.strip()[:500]}")
    return proc.stdout


class ClaudeCli:
    """One resumable `claude -p` conversation."""

    def __init__(self, extra_args: Sequence[str], cwd: Optional[str] = None,
                 runner: Runner = run_subprocess) -> None:
        self.extra_args = list(extra_args)
        self.cwd = cwd
        self.runner = runner
        self.session_id: Optional[str] = None

    def send(self, prompt: str) -> str:
        argv = ["claude", "-p", prompt, "--output-format", "json", *self.extra_args]
        if self.session_id:
            argv += ["--resume", self.session_id]
        data = json.loads(self.runner(argv, self.cwd))
        self.session_id = data.get("session_id", self.session_id)
        if data.get("is_error"):
            raise RuntimeError(f"claude reported an error: {data.get('result')}")
        return str(data.get("result", ""))


class ApiChat:
    """Chat side over the Messages API (paid)."""

    def __init__(self, model: str = API_MODEL) -> None:
        import anthropic  # optional dependency, only needed for this backend

        self.client = anthropic.Anthropic()
        self.model = model
        self.messages: list = []

    def send(self, prompt: str) -> str:
        self.messages.append({"role": "user", "content": prompt})
        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=CHAT_SYSTEM,
            thinking={"type": "adaptive"},
            messages=self.messages,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("chat side refused the request")
        self.messages.append({"role": "assistant", "content": response.content})
        return "".join(b.text for b in response.content if b.type == "text")


@dataclass
class Turn:
    round: int
    instruction: str
    result: str


@dataclass
class BridgeResult:
    done: bool
    summary: str
    turns: List[Turn] = field(default_factory=list)


def is_done(text: str) -> bool:
    return text.strip().upper().startswith(DONE)


def run_bridge(goal: str, chat, coder, max_rounds: int = 5, workdir: str = ".") -> BridgeResult:
    result = BridgeResult(done=False, summary="")
    message = (
        f"Ziel: {goal}\n\nClaude Code arbeitet im Verzeichnis: {workdir}\n"
        "Gib die erste Anweisung für Claude Code."
    )
    for rnd in range(1, max_rounds + 1):
        instruction = chat.send(message)
        if is_done(instruction):
            result.done, result.summary = True, instruction.strip()
            return result
        logger.info("round %d: instruction sent to Claude Code", rnd)
        try:
            outcome = coder.send(instruction)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            outcome = f"FEHLER bei der Ausführung: {exc}"
        result.turns.append(Turn(rnd, instruction, outcome))
        message = (
            f"Ergebnis von Claude Code (Runde {rnd}):\n{outcome}\n\n"
            f"Prüfe das Ergebnis. Nächste Anweisung, oder '{DONE}' + Zusammenfassung."
        )
    result.summary = f"Abgebrochen nach {max_rounds} Runden ohne '{DONE}'."
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("goal")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--max-rounds", type=int, default=5)
    parser.add_argument("--permission-mode", choices=SAFE_PERMISSION_MODES, default="default")
    parser.add_argument("--chat-backend", choices=["cli", "api"], default="cli")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--transcript")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
    workdir = str(Path(args.cwd).resolve())

    if args.chat_backend == "api":
        if not args.allow_paid:
            parser.error("--chat-backend api is billed per token; pass --allow-paid")
        chat = ApiChat()
    else:
        chat = ClaudeCli(["--tools", "", "--system-prompt", CHAT_SYSTEM], cwd=workdir)
    coder = ClaudeCli(["--permission-mode", args.permission_mode], cwd=workdir)

    result = run_bridge(args.goal, chat, coder, args.max_rounds, workdir)
    if args.transcript:
        Path(args.transcript).write_text(
            json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(result.summary)
    return 0 if result.done else 1


if __name__ == "__main__":
    sys.exit(main())
