"""Exports, reload/compare, schema re-application and safe staging.  Owner: Member 4."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from .audit import CHECK_COLUMNS, write_checks
from .common import SchemaError
from .reconcile import compare_tables

FAILED_REPORT = "failed_validation_report.csv"


# ---------------------------------------------------------------- writing
def write_export(df: pd.DataFrame, path: Path, fmt: str, sheet: str = "observations") -> None:
    """Write the canonical table in one format without any row index."""
    if fmt == "csv":
        df.to_csv(path, index=False)
    elif fmt == "xlsx":
        df.to_excel(path, sheet_name=sheet, index=False, engine="openpyxl")
    elif fmt == "json":  # orientation: records
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(df.to_dict(orient="records"), handle, ensure_ascii=False, indent=1)
    elif fmt == "parquet":
        df.to_parquet(path, engine="pyarrow", index=False)
    else:
        raise ValueError(f"unknown export format {fmt!r}")


def read_export(path: Path, fmt: str, sheet: str = "observations") -> pd.DataFrame:
    """Reload an exported file with the types its format naturally gives back."""
    if fmt == "csv":
        return pd.read_csv(path, keep_default_na=False)
    if fmt == "xlsx":
        return pd.read_excel(path, sheet_name=sheet, keep_default_na=False, engine="openpyxl")
    if fmt == "json":
        with open(path, encoding="utf-8") as handle:
            return pd.DataFrame(json.load(handle))
    if fmt == "parquet":
        return pd.read_parquet(path, engine="pyarrow")
    raise ValueError(f"unknown export format {fmt!r}")


# ------------------------------------------------------- schema re-applied
def apply_schema(df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    """Cast a reloaded table to the declared dtypes, refusing lossy conversions."""
    order = list(schema["canonical_order"])
    if set(df.columns) != set(order):
        raise SchemaError(f"reloaded columns {sorted(df.columns)} differ from the schema")
    out = df[order].copy()
    for col in order:
        kind = schema["dtypes"][col]
        try:
            if kind == "string":
                if out[col].isna().any():
                    raise SchemaError(f"{col}: missing text after reload")
                out[col] = out[col].astype(str).str.strip().astype("string")
                continue
            numbers = pd.to_numeric(out[col], errors="raise")
            values = numbers.to_numpy(dtype="float64")
            if not np.isfinite(values).all():
                raise SchemaError(f"{col}: non-finite value after reload")
            if kind == "int64":
                if not (values == np.floor(values)).all():
                    raise SchemaError(f"{col}: fractional value after reload")
                out[col] = numbers.astype("int64")
            else:
                out[col] = numbers.astype("float64")
        except (ValueError, TypeError) as exc:
            raise SchemaError(f"{col}: cannot convert reloaded values ({exc})") from exc
    return out


def roundtrip_check(
    original: pd.DataFrame, path: Path, fmt: str, schema: dict, atol: float, sheet: str = "observations"
) -> tuple[list[str], list[str]]:
    """Reload an export, reapply the schema and compare; return (differences, conversions)."""
    raw = read_export(path, fmt, sheet)
    conversions = [
        f"{col}: {raw[col].dtype} -> {schema['dtypes'][col]}"
        for col in schema["canonical_order"]
        if col in raw.columns and str(raw[col].dtype) != schema["dtypes"][col]
    ]
    try:
        reloaded = apply_schema(raw, schema)
    except SchemaError as exc:
        return [f"schema re-application failed: {exc}"], conversions
    return compare_tables(original, reloaded, schema, atol), conversions


# ---------------------------------------------------------------- staging
def make_staging(output_dir: Path) -> Path:
    """Create a private staging folder next to the output folder."""
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=".staging_", dir=output_dir.parent))


def publish_staging(stage: Path, output_dir: Path) -> list[str]:
    """Move every staged file into the output folder; return the published names."""
    output_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for item in sorted(stage.iterdir()):
        os.replace(item, output_dir / item.name)
        names.append(item.name)
    (output_dir / FAILED_REPORT).unlink(missing_ok=True)
    shutil.rmtree(stage, ignore_errors=True)
    return names


def discard_staging(stage: Path) -> None:
    """Delete a staging folder without touching published outputs."""
    shutil.rmtree(stage, ignore_errors=True)


def write_failed_report(output_dir: Path, checks: list[dict], error: str) -> Path:
    """Save the failed validation report (checks so far plus the stopping error)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = list(checks) + [
        {"check": "run_error", "expected": "no error", "actual": error, "tolerance": "exact", "pass": False}
    ]
    path = output_dir / FAILED_REPORT
    write_checks(rows, path)
    return path


__all__ = [
    "CHECK_COLUMNS",
    "FAILED_REPORT",
    "apply_schema",
    "discard_staging",
    "make_staging",
    "publish_staging",
    "read_export",
    "roundtrip_check",
    "write_export",
    "write_failed_report",
]
