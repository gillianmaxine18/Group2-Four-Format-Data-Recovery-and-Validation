"""Parquet reader.  Owner: Member 2.

Columns are stored as strings in the supplied file, so everything is returned
as untouched Python objects; conversion to numbers happens only after validation.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .common import InputFileError, with_source_record


def read_parquet_source(path: Path, settings: dict) -> pd.DataFrame:
    """Read a Parquet file with the configured engine and keep original values."""
    engine = settings.get("engine", "pyarrow")
    try:
        df = pd.read_parquet(path, engine=engine)
    except ImportError as exc:
        raise InputFileError(f"{Path(path).name}: parquet engine {engine!r} is not installed") from exc
    except (OSError, ValueError) as exc:
        raise InputFileError(f"{Path(path).name}: cannot read parquet ({exc})") from exc
    df.columns = [str(c).strip() for c in df.columns]
    return with_source_record(df.astype(object))
