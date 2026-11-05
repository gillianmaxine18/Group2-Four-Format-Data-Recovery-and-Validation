"""Column mapping, record validation and the ValidationResult class."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .common import SchemaError

_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_NONFINITE = {"nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}


# mapping
def unmapped_columns(raw: pd.DataFrame, mapping: Mapping[str, str]) -> list[str]:
    """Return source columns that are neither mapped nor the position column."""
    return sorted(set(raw.columns) - set(mapping) - {"source_record"})


def map_columns(
    raw: pd.DataFrame,
    mapping: Mapping[str, str],
    canonical_order: list[str],
    source_file: str = "",
) -> pd.DataFrame:
    """Rename source columns to canonical names; a missing required column is file-level."""
    missing = set(mapping) - set(raw.columns)
    if missing:
        raise SchemaError(f"{source_file}: missing required column(s) {sorted(missing)}")
    if set(mapping.values()) != set(canonical_order):
        raise SchemaError(f"{source_file}: mapping does not cover exactly the canonical columns")
    out = raw[list(mapping)].rename(columns=dict(mapping))[list(canonical_order)].copy()
    out["source_record"] = raw["source_record"].to_numpy()
    return out

# parsing
def is_missing(value: Any) -> bool:
    """True for None, NaN/NA and empty or whitespace-only text."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def original_text(value: Any) -> str:
    """Original field value as text for the quarantine file ('' when missing)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
    return str(value)


def parse_float(value: Any) -> float:
    """Parse a finite float; raise ValueError with a reason otherwise."""
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("not a number (boolean)")
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if text.lower() in _NONFINITE:
            raise ValueError(f"non-finite value {text!r}")
        if not _NUMBER_RE.match(text):
            raise ValueError(f"not a number {text!r}")
        number = float(text)
    else:
        raise ValueError(f"not a number {value!r}")
    if not math.isfinite(number):
        raise ValueError("non-finite value")
    return number


def parse_integer(value: Any) -> int:
    """Parse a whole number (1952 or '1952.0' pass, 1952.5 fails) without silent truncation."""
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, str) and _INT_RE.match(value.strip()):
        return int(value.strip())
    number = parse_float(value)
    if not number.is_integer():
        raise ValueError(f"fractional value {value!r} where a whole number is required")
    return int(number)


def check_rule(number: float, rule: Mapping[str, float]) -> str | None:
    """Return a reason if number breaks the min_exclusive / max_inclusive rule."""
    if "min_exclusive" in rule and not number > rule["min_exclusive"]:
        return f"{number} is not greater than {rule['min_exclusive']}"
    if "max_inclusive" in rule and not number <= rule["max_inclusive"]:
        return f"{number} is greater than {rule['max_inclusive']}"
    return None


# validation
def validate_record(raw: Mapping[str, Any], schema: dict) -> tuple[dict | None, str | None]:
    """Validate one record; return (clean_record, None) or (None, reasons)."""
    allowed_continents = set(schema["allowed_continents"])
    allowed_years = set(schema["allowed_years"])
    reasons: list[str] = []
    clean: dict[str, Any] = {}
    for col in schema["canonical_order"]:
        value = raw.get(col)
        kind = schema["dtypes"][col]
        if is_missing(value):
            reasons.append(f"{col}: missing or empty")
            continue
        if kind == "string":
            text = str(value).strip()
            if col == "continent" and text not in allowed_continents:
                reasons.append(f"{col}: {text!r} not in allowed set")
            clean[col] = text
            continue
        try:
            number = parse_integer(value) if kind == "int64" else parse_float(value)
        except ValueError as exc:
            reasons.append(f"{col}: {exc}")
            continue
        if col == "year" and number not in allowed_years:
            reasons.append(f"{col}: {number} not in allowed years")
        problem = check_rule(number, schema.get("rules", {}).get(col, {}))
        if problem:
            reasons.append(f"{col}: {problem}")
        clean[col] = number
    if reasons:
        return None, "; ".join(reasons)
    return clean, None


class ValidationResult:
    """Collects accepted records and quarantined records for one source file."""

    def __init__(self, source_file: str, raw_count: int) -> None:
        self.source_file = source_file
        self.raw_count = raw_count
        self.accepted: list[dict] = []
        self.quarantined: list[dict] = []

    @property
    def accepted_count(self) -> int:
        """Number of records that passed validation."""
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        """Number of records sent to quarantine."""
        return len(self.quarantined)

    def add_accepted(self, source_record: int, clean: dict) -> None:
        """Store a valid record with its original position."""
        self.accepted.append({**clean, "source_record": int(source_record)})

    def add_rejected(self, source_record: int, reason: str, original: dict) -> None:
        """Store an invalid record with its reason and original field values."""
        self.quarantined.append(
            {
                "source_file": self.source_file,
                "source_record": int(source_record),
                "reason": reason,
                **original,
            }
        )

    def reason_counts(self) -> Counter:
        """Count quarantined records by the field named at the start of the reason."""
        return Counter(q["reason"].split(":")[0] for q in self.quarantined)

    def to_frame(self, schema: dict) -> pd.DataFrame:
        """Accepted records as a typed DataFrame (conversion happens only here)."""
        columns = list(schema["canonical_order"]) + ["source_record"]
        df = pd.DataFrame(self.accepted, columns=columns)
        for col in schema["canonical_order"]:
            df[col] = df[col].astype(schema["dtypes"][col])
        df["source_record"] = df["source_record"].astype("int64")
        return df


def validate_dataframe(mapped: pd.DataFrame, schema: dict, source_file: str) -> ValidationResult:
    """Validate every mapped row, keeping valid ones and quarantining the rest."""
    result = ValidationResult(source_file, len(mapped))
    for row in mapped.to_dict("records"):
        clean, reason = validate_record(row, schema)
        if reason is None:
            result.add_accepted(row["source_record"], clean)
        else:
            original = {col: original_text(row.get(col)) for col in schema["canonical_order"]}
            result.add_rejected(row["source_record"], reason, original)
    return result
