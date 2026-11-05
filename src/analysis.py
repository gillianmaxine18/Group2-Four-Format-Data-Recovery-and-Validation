
"""analysis.py -- takes the clean, validated table and produces the two pandas results: 
Asia for a chosen year, and one country’s history.
"""
from __future__ import annotations

import pandas as pd

from .common import ProcessingError


def asia_selected_year(df: pd.DataFrame, year: int, continent: str = "Asia") -> pd.DataFrame:
    """Select one continent and year with .loc; add pop in millions and life-expectancy rank."""
    mask = (df["continent"] == continent) & (df["year"] == year)
    out = df.loc[mask].copy()
    out["pop_millions"] = out["pop"] / 1_000_000
    out["lifeExp_rank"] = out["lifeExp"].rank(method="min", ascending=False).astype("int64")
    return out.sort_values(["lifeExp_rank", "country"]).reset_index(drop=True)


def country_history(df: pd.DataFrame, country: str) -> pd.DataFrame:
    """All rows of one country by year, with pop in millions and life-expectancy change."""
    out = df.loc[df["country"] == country].sort_values("year").copy()
    if out.empty:
        raise ProcessingError(f"no rows found for country {country!r}")
    out["pop_millions"] = out["pop"] / 1_000_000
    out["lifeExp_change"] = out["lifeExp"] - out["lifeExp"].iloc[0]
    return out.reset_index(drop=True)
