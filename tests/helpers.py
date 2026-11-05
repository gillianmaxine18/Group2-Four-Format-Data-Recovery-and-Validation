"""Shared test helpers.  Generated fixtures live in temp folders, never in data/."""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import load_config  # noqa: E402

CONFIG = load_config(ROOT / "config.json")
SCHEMA = CONFIG["schema"]
DATA_DIR = ROOT / "data"
ORDER = SCHEMA["canonical_order"]
HAS_PYARROW = importlib.util.find_spec("pyarrow") is not None


def settings_for(fmt: str) -> dict:
    """Return the configured input settings for one format."""
    return next(i for i in CONFIG["inputs"] if i["format"] == fmt)


def plain_csv_settings(filename: str) -> dict:
    """Settings for the failure-test CSVs: UTF-8, commas, canonical names, no comments."""
    return {
        "file": filename,
        "format": "csv",
        "raw_records": 0,
        "encoding": "utf-8",
        "separator": ",",
        "source_to_canonical": {c: c for c in ORDER},
    }


def runnable_config(out_dir: Path, **overrides) -> dict:
    """Config copy that writes to a temp folder; Parquet is dropped if pyarrow is missing."""
    cfg = copy.deepcopy(CONFIG)
    cfg["data_dir"] = str(DATA_DIR)
    cfg["output_dir"] = str(out_dir)
    if not HAS_PYARROW:
        cfg["inputs"] = [i for i in cfg["inputs"] if i["format"] != "parquet"]
        cfg["exports"].pop("parquet", None)
    cfg.update(overrides)
    return cfg


def make_frame(rows: list[tuple]) -> pd.DataFrame:
    """Typed canonical frame (+ source_record) from tuples of the six fields."""
    df = pd.DataFrame(rows, columns=ORDER)
    for col in ORDER:
        df[col] = df[col].astype(SCHEMA["dtypes"][col])
    df["source_record"] = range(1, len(df) + 1)
    return df


def raw_frame(rows: list[tuple]) -> pd.DataFrame:
    """Untyped (object) frame in canonical column names, like a reader + mapper would give."""
    df = pd.DataFrame(rows, columns=ORDER, dtype=object)
    df["source_record"] = range(1, len(df) + 1)
    return df


GOOD = ("Testland", "Asia", 2007, 70.5, 1_000_000, 5000.25)
