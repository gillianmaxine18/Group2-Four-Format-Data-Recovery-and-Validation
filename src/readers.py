"""CSV, Excel and JSON readers plus the format dispatcher.

Readers keep the ORIGINAL field values (as text or as the
raw JSON values) and the original record position.  They do not rename or
validate anything; that happens later in validation.py.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .common import (
    InputFileError,
    SchemaError,
    UnsupportedFormatError,
    with_source_record,
)
from .parquet_reader import read_parquet_source


def read_csv_source(path: Path, settings: dict) -> pd.DataFrame:
    """Read a delimited text file, skipping comment lines, all values as text."""
    encoding = settings.get("encoding", "utf-8")
    separator = settings.get("separator", ",")
    prefix = settings.get("comment_prefix")
    try:
        text = Path(path).read_text(encoding=encoding)
    except UnicodeDecodeError as exc:
        raise InputFileError(f"{Path(path).name}: cannot decode as {encoding}") from exc
    lines = text.split("\n")
    if prefix:
        lines = [line for line in lines if not line.startswith(prefix)]
    if not any(line.strip() for line in lines):
        raise SchemaError(f"{Path(path).name}: no header row found")
    try:
        df = pd.read_csv(
            io.StringIO("\n".join(lines)),
            sep=separator,
            dtype=str,
            keep_default_na=False,
        )
    except (ValueError, pd.errors.ParserError) as exc:
        raise InputFileError(f"{Path(path).name}: cannot parse CSV ({exc})") from exc
    df.columns = [str(c).strip() for c in df.columns]
    return with_source_record(df)


def read_excel_source(path: Path, settings: dict) -> pd.DataFrame:
    """Read the required observations sheet of a workbook, values as text."""
    sheet = settings["sheet_name"]
    try:
        df = pd.read_excel(
            path,
            sheet_name=sheet,
            dtype=str,
            keep_default_na=False,
            engine=settings.get("engine", "openpyxl"),
        )
    except (ValueError, KeyError) as exc:
        raise SchemaError(f"{Path(path).name}: sheet {sheet!r} not readable ({exc})") from exc
    except (zipfile.BadZipFile, OSError) as exc:
        raise InputFileError(f"{Path(path).name}: not a valid workbook ({exc})") from exc
    df.columns = [str(c).strip() for c in df.columns]
    return with_source_record(df)


def flatten_record(record: dict, parent: str = "", sep: str = ".") -> dict:
    """Flatten nested dictionaries into one level: {'a': {'b': 1}} -> {'a.b': 1}."""
    flat: dict[str, Any] = {}
    for key, value in record.items():
        name = f"{parent}{sep}{key}" if parent else str(key)
        if isinstance(value, dict):
            flat.update(flatten_record(value, name, sep))
        else:
            flat[name] = value
    return flat


def read_json_source(path: Path, settings: dict) -> pd.DataFrame:
    """Read the nested `record_path` list of a JSON file and flatten each record."""
    try:
        data = json.loads(Path(path).read_text(encoding=settings.get("encoding", "utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InputFileError(f"{Path(path).name}: not valid JSON ({exc})") from exc
    node: Any = data
    for part in str(settings.get("record_path", "")).split("."):
        if not part:
            continue
        if not isinstance(node, dict) or part not in node:
            raise SchemaError(f"{Path(path).name}: record path {settings['record_path']!r} not found")
        node = node[part]
    if not isinstance(node, list) or not all(isinstance(r, dict) for r in node):
        raise SchemaError(f"{Path(path).name}: record path must point to a list of objects")
    df = pd.DataFrame([flatten_record(r) for r in node], dtype=object)
    return with_source_record(df)


READERS: dict[str, Callable[[Path, dict], pd.DataFrame]] = {
    "csv": read_csv_source,
    "xlsx": read_excel_source,
    "json": read_json_source,
    "parquet": read_parquet_source,
}


def read_source(path: Path, settings: dict) -> pd.DataFrame:
    """Read one input file with the reader named by settings['format']."""
    path = Path(path)
    if not path.is_file():
        raise InputFileError(f"input file not found: {path.name}")
    fmt = str(settings.get("format") or path.suffix.lstrip(".")).lower()
    reader = READERS.get(fmt)
    if reader is None:
        raise UnsupportedFormatError(f"{path.name}: unsupported format {fmt!r}")
    return reader(path, settings)
