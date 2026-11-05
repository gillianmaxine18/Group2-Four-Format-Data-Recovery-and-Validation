"""Run every automated check and record what ran, and the outcome, in test_results.txt.

Usage:  python run_tests.py
Owner: Member 4.  Fixtures are created in temporary folders, never inside data/.
"""
from __future__ import annotations

import platform
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))


class RecordingResult(unittest.TextTestResult):
    """Remember the outcome of each test so it can be listed in test_results.txt."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows: list[tuple[str, str]] = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.rows.append((test.id(), "PASS"))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.rows.append((test.id(), "FAIL"))

    def addError(self, test, err):
        super().addError(test, err)
        self.rows.append((test.id(), "ERROR"))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.rows.append((test.id(), f"SKIPPED ({reason})"))


def main() -> int:
    """Discover tests, run them and write the report."""
    import numpy
    import pandas

    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(resultclass=RecordingResult, verbosity=1, stream=sys.stderr)
    result = runner.run(suite)
    lines = [
        "DSA4153 Week 10 - automated check results",
        f"run at: {datetime.now().isoformat(timespec='seconds')}",
        f"python {platform.python_version()}, pandas {pandas.__version__}, numpy {numpy.__version__}",
        "runner: python run_tests.py  (unittest)",
        "",
    ]
    lines += [f"{outcome:<10} {name}" for name, outcome in sorted(result.rows)]
    skipped = len(result.skipped)
    passed = result.testsRun - len(result.failures) - len(result.errors) - skipped
    lines += [
        "",
        f"ran {result.testsRun} checks: {passed} passed, {len(result.failures)} failed, "
        f"{len(result.errors)} errors, {skipped} skipped",
        "RESULT: " + ("OK" if result.wasSuccessful() else "FAILED"),
    ]
    (ROOT / "test_results.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
