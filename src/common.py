"""Shared contract: exceptions, the Recovery record and config loading.

Owner: Member 4 (committed first so every member can import from it).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd


class ProcessingError(Exception):
    """Base class for every error that must stop a run."""


class InputFileError(ProcessingError):
    """An input file is missing, unreadable or malformed."""


class UnsupportedFormatError(InputFileError):
    """An input file exists but its format is not supported."""


class SchemaError(ProcessingError):
    """A required column (or sheet/key) is missing from an input."""


class ConflictError(ProcessingError):
    """Two valid rows share a (country, year) key but disagree on a value."""


class AgreementError(ProcessingError):
    """The recovered tables from the different formats do not agree."""


class CheckFailedError(ProcessingError):
    """One or more validation checks failed at the end of a run."""


class Recovery(NamedTuple):
    """Everything recovered from one input file."""

    source_file: str
    raw_count: int
    clean: pd.DataFrame
    validation: "ValidationResult"  # noqa: F821  (defined in validation.py)
    duplicates: list


def load_config(path: str | Path) -> dict:
    """Load the JSON configuration file into a dictionary."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise InputFileError(f"config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputFileError(f"config file is not valid JSON: {exc}") from exc


def with_source_record(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with a one-based `source_record` column added."""
    out = df.reset_index(drop=True).copy()
    out["source_record"] = np.arange(1, len(out) + 1, dtype="int64")
    return out
