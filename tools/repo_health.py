"""Repo health check used by the scheduled maintenance routine.

Parses every Python file with ``ast`` (no imports executed, so heavy deps like
torch are not needed) and reports syntax errors plus lightweight hygiene
signals as JSON.

Usage:
    python tools/repo_health.py [ROOT] [--exclude DIR ...]

Exit code: 0 if no syntax errors were found, 1 otherwise.
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

logger = logging.getLogger("repo_health")

DEFAULT_EXCLUDES: tuple[str, ...] = (".git", "venv", ".venv", "__pycache__", "node_modules")


@dataclass
class SyntaxIssue:
    path: str
    line: Optional[int]
    message: str


@dataclass
class HealthReport:
    files_checked: int = 0
    syntax_errors: List[SyntaxIssue] = field(default_factory=list)
    bare_excepts: List[str] = field(default_factory=list)
    todo_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.syntax_errors

    def to_dict(self) -> dict:
        data = asdict(self)
        data["ok"] = self.ok
        return data


def iter_python_files(root: Path, excludes: Iterable[str]) -> Iterable[Path]:
    excluded = set(excludes)
    for path in sorted(root.rglob("*.py")):
        if excluded.intersection(path.relative_to(root).parts):
            continue
        yield path


def check_file(path: Path, root: Path, report: HealthReport) -> None:
    rel = str(path.relative_to(root))
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        report.syntax_errors.append(SyntaxIssue(rel, None, f"unreadable: {exc}"))
        return
    report.files_checked += 1
    report.todo_count += source.count("TODO")
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        report.syntax_errors.append(SyntaxIssue(rel, exc.lineno, exc.msg))
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            report.bare_excepts.append(f"{rel}:{node.lineno}")


def run(root: Path, excludes: Sequence[str] = DEFAULT_EXCLUDES) -> HealthReport:
    report = HealthReport()
    for path in iter_python_files(root, excludes):
        check_file(path, root, report)
    logger.info("checked %d files, %d syntax errors", report.files_checked, len(report.syntax_errors))
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--exclude", nargs="*", default=list(DEFAULT_EXCLUDES))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
    report = run(Path(args.root).resolve(), args.exclude)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
