"""Audit records and validation checks.  Owner: Member 4."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

AUDIT_COLUMNS = ["step", "source_file", "operation", "rule", "rows_before", "rows_after"]
CHECK_COLUMNS = ["check", "expected", "actual", "tolerance", "pass"]


def add_audit(
    audit: list[dict],
    source_file: str,
    operation: str,
    rule: str,
    rows_before: int,
    rows_after: int,
) -> None:
    """Append one audit record; the step number is the running position in the list."""
    audit.append(
        {
            "step": len(audit) + 1,
            "source_file": source_file,
            "operation": operation,
            "rule": rule,
            "rows_before": int(rows_before),
            "rows_after": int(rows_after),
        }
    )


def make_check(check: str, expected: Any, actual: Any, tolerance: float | str = "exact") -> dict:
    """Build one validation row; numeric values may differ by `tolerance`, others must match."""
    if isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool):
        passed = abs(float(expected) - float(actual)) <= tolerance
    else:
        passed = expected == actual
    return {
        "check": check,
        "expected": expected,
        "actual": actual,
        "tolerance": tolerance,
        "pass": bool(passed),
    }


def write_table(rows: list[dict], columns: list[str], path: Path) -> None:
    """Write a list of dictionaries to CSV with a fixed column order (header even if empty)."""
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def write_audit(audit: list[dict], path: Path) -> None:
    """Write audit_log.csv."""
    write_table(audit, AUDIT_COLUMNS, path)


def write_checks(checks: list[dict], path: Path) -> None:
    """Write validation.csv (or the failed validation report)."""
    write_table(checks, CHECK_COLUMNS, path)
