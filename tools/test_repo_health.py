import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import repo_health  # noqa: E402


class RepoHealthTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, content: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_clean_tree_is_ok(self) -> None:
        self.write("a.py", "x = 1  # TODO later\n")
        report = repo_health.run(self.root)
        self.assertTrue(report.ok)
        self.assertEqual(report.files_checked, 1)
        self.assertEqual(report.todo_count, 1)

    def test_syntax_error_detected(self) -> None:
        self.write("bad.py", "def f(:\n")
        report = repo_health.run(self.root)
        self.assertFalse(report.ok)
        self.assertEqual(report.syntax_errors[0].path, "bad.py")

    def test_bare_except_and_excludes(self) -> None:
        self.write("b.py", "try:\n    pass\nexcept:\n    pass\n")
        self.write("venv/skip.py", "def f(:\n")
        report = repo_health.run(self.root)
        self.assertTrue(report.ok)
        self.assertEqual(report.bare_excepts, ["b.py:3"])

    def test_main_exit_code(self) -> None:
        self.write("bad.py", "def f(:\n")
        self.assertEqual(repo_health.main([str(self.root)]), 1)


if __name__ == "__main__":
    unittest.main()
