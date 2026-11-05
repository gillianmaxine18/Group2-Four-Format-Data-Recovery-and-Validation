"""NumPy population matrix, broadcasting and independent checks."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .common import ProcessingError


def build_population_matrix(df: pd.DataFrame, countries: list[str], years: list[int]) -> np.ndarray:
    """Build a (countries x years) int64 matrix using Boolean selection on NumPy arrays."""
    country_arr = df["country"].to_numpy(dtype=object)
    year_arr = df["year"].to_numpy(dtype="int64")
    pop_arr = df["pop"].to_numpy(dtype="int64")
    matrix = np.zeros((len(countries), len(years)), dtype="int64")
    for i, country in enumerate(countries):
        for j, year in enumerate(years):
            mask = (country_arr == country) & (year_arr == year)
            if int(mask.sum()) != 1:
                raise ProcessingError(f"expected exactly one row for {country} {year}")
            matrix[i, j] = pop_arr[mask][0]
    return matrix


def index_to_baseline(matrix: np.ndarray, baseline_col: int) -> dict[str, Any]:
    """Broadcast each row's baseline column to give an index (baseline = 100)."""
    baseline = matrix[:, [baseline_col]]  # shape (rows, 1)
    index = matrix / baseline * 100.0  # (rows, cols) / (rows, 1) broadcasts
    return {
        "baseline": baseline,
        "index": index,
        "shape_matrix": matrix.shape,
        "shape_baseline": baseline.shape,
        "shape_index": index.shape,
    }


def index_by_loop(matrix: np.ndarray, baseline_col: int) -> np.ndarray:
    """Independent loop version of the baseline index, used to verify broadcasting."""
    rows, cols = matrix.shape
    out = np.zeros((rows, cols), dtype="float64")
    for i in range(rows):
        base = float(matrix[i, baseline_col])
        for j in range(cols):
            out[i, j] = float(matrix[i, j]) / base * 100.0
    return out


def asia_total(df: pd.DataFrame, year: int, continent: str = "Asia") -> tuple[int, int]:
    """Boolean-mask selection and sum of population; returns (rows, total persons)."""
    continent_arr = df["continent"].to_numpy(dtype=object)
    year_arr = df["year"].to_numpy(dtype="int64")
    pop_arr = df["pop"].to_numpy(dtype="int64")
    mask = (continent_arr == continent) & (year_arr == year)
    return int(mask.sum()), int(pop_arr[mask].sum())


def matrix_to_frame(countries: list[str], years: list[int], values: np.ndarray) -> pd.DataFrame:
    """Label a matrix with country names and one named column per year."""
    frame = pd.DataFrame(values, columns=[str(y) for y in years])
    frame.insert(0, "country", countries)
    return frame

