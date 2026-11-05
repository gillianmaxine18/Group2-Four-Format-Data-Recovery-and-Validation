"""Duplicates, conflicts, sorting and four-format comparison."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import ConflictError, SchemaError


def require_key_columns(df: pd.DataFrame, key_columns: list[str], source_file: str = "") -> None:
    """Raise SchemaError if any key column is absent from the table."""
    missing = set(key_columns) - set(df.columns)
    if missing:
        raise SchemaError(f"{source_file}: missing key column(s) {sorted(missing)}")


def remove_exact_duplicates(
    df: pd.DataFrame, source_file: str, columns: list[str]
) -> tuple[pd.DataFrame, list[dict]]:
    """Drop repeated identical records (keep the first) and log every removed copy."""
    seen: dict[tuple, int] = {}
    keep: list[bool] = []
    log: list[dict] = []
    for row in df.to_dict("records"):
        signature = tuple(row[c] for c in columns)
        if signature in seen:
            keep.append(False)
            log.append(
                {
                    "source_file": source_file,
                    "source_record": int(row["source_record"]),
                    "duplicate_of_record": seen[signature],
                    **{c: row[c] for c in columns},
                }
            )
        else:
            seen[signature] = int(row["source_record"])
            keep.append(True)
    return df.loc[keep].reset_index(drop=True), log


def check_conflicts(df: pd.DataFrame, key_columns: list[str], source_file: str = "") -> None:
    """Stop with ConflictError if a key is repeated with different values."""
    require_key_columns(df, key_columns, source_file)
    repeated = df.loc[df.duplicated(subset=key_columns, keep=False)]
    if not repeated.empty:
        first = repeated.iloc[0]
        key = tuple(first[c].item() if hasattr(first[c], "item") else first[c] for c in key_columns)
        raise ConflictError(
            f"{source_file}: conflicting values for key {key}; "
            f"{repeated[key_columns].drop_duplicates().shape[0]} conflicting key(s)"
        )


def sort_canonical(df: pd.DataFrame, key_columns: list[str]) -> pd.DataFrame:
    """Sort by the key columns (country, then year) and reset the index."""
    return df.sort_values(key_columns, kind="mergesort").reset_index(drop=True)


def compare_tables(
    left: pd.DataFrame,
    right: pd.DataFrame,
    schema: dict,
    atol: float = 1e-8,
) -> list[str]:
    """Compare two tables BY KEY; return difference messages (empty list = identical)."""
    order = list(schema["canonical_order"])
    key = list(schema["key"])
    if set(order) - set(left.columns) or set(order) - set(right.columns):
        return ["columns differ from the canonical schema"]
    left, right = left[order], right[order]
    left_keys = set(map(tuple, left[key].itertuples(index=False, name=None)))
    right_keys = set(map(tuple, right[key].itertuples(index=False, name=None)))
    problems: list[str] = []
    if left.duplicated(subset=key).any() or right.duplicated(subset=key).any():
        return ["a table contains repeated keys"]
    if left_keys != right_keys:
        problems.append(
            f"keys differ: {len(left_keys - right_keys)} only in left, "
            f"{len(right_keys - left_keys)} only in right"
        )
        return problems
    a = left.set_index(key).sort_index()
    b = right.set_index(key).sort_index()
    for col in a.columns:
        a_na, b_na = a[col].isna().to_numpy(), b[col].isna().to_numpy()
        if (a_na != b_na).any():
            problems.append(f"{col}: {int((a_na != b_na).sum())} missingness difference(s)")
            continue
        ok = ~a_na
        kind = schema["dtypes"][col]
        if kind == "float64":
            x = a[col].to_numpy(dtype="float64")[ok]
            y = b[col].to_numpy(dtype="float64")[ok]
            bad = ~np.isclose(x, y, rtol=0.0, atol=atol)
        else:
            x = a[col].to_numpy(dtype=object)[ok]
            y = b[col].to_numpy(dtype=object)[ok]
            bad = x != y
        if bad.any():
            problems.append(f"{col}: {int(bad.sum())} value(s) differ")
    return problems


def compare_all(
    tables: dict[str, pd.DataFrame], schema: dict, atol: float = 1e-8
) -> dict[str, list[str]]:
    """Compare every table with the first one; return {name: differences}."""
    names = list(tables)
    reference = tables[names[0]]
    return {name: compare_tables(reference, tables[name], schema, atol) for name in names[1:]}

