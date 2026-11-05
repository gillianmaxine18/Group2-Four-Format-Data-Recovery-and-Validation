"""Tests: missing column, unparseable numbers, fractional, non-finite/out-of-range."""
import unittest
from unittest import mock

import pandas as pd

from helpers import DATA_DIR, GOOD, HAS_PYARROW, ORDER, SCHEMA, plain_csv_settings, raw_frame
from src.common import SchemaError
from src.parquet_reader import read_parquet_source
from src.pipeline import recover_source
from src.validation import (
    ValidationResult,
    map_columns,
    parse_float,
    parse_integer,
    validate_dataframe,
    validate_record,
)


def record(**changes) -> dict:
    """A valid raw record with some fields replaced."""
    base = dict(zip(ORDER, GOOD))
    base.update(changes)
    return base


def reason(**changes) -> str:
    clean, why = validate_record(record(**changes), SCHEMA)
    assert clean is None, f"expected rejection for {changes}"
    return why


class MissingColumn(unittest.TestCase):
    def test_04_missing_column_is_file_level_error(self):
        frame = raw_frame([GOOD]).drop(columns=["pop"])
        mapping = {c: c for c in ORDER}
        with self.assertRaises(SchemaError):
            map_columns(frame, mapping, ORDER, "fake.csv")

    def test_04_missing_column_csv_fixture_stops_run(self):
        with self.assertRaises(SchemaError):
            recover_source(plain_csv_settings("missing_column.csv"), SCHEMA, DATA_DIR, [])

    def test_mapping_renames_and_keeps_position(self):
        raw = pd.DataFrame({"A": ["x"], "B": ["Asia"], "C": ["2007"], "D": ["1"], "E": ["2"], "F": ["3"], "extra": ["z"]})
        raw["source_record"] = [1]
        mapped = map_columns(raw, dict(zip("ABCDEF", ORDER)), ORDER, "f")
        self.assertEqual(list(mapped.columns), ORDER + ["source_record"])
        self.assertEqual(mapped["country"].iloc[0], "x")


class ParsingAndValidation(unittest.TestCase):
    def test_valid_record_is_cleaned_and_trimmed(self):
        clean, why = validate_record(record(country="  Testland  ", year="2007", pop="1000000"), SCHEMA)
        self.assertIsNone(why)
        self.assertEqual(clean["country"], "Testland")
        self.assertEqual(clean["year"], 2007)
        self.assertIsInstance(clean["pop"], int)

    def test_05_unparseable_number(self):
        self.assertIn("not a number", reason(gdpPercap="not-a-number"))
        self.assertIn("not a number", reason(year="not-a-year"))
        self.assertIn("not a number", reason(lifeExp="1_000"))
        self.assertIn("not a number", reason(pop="12abc"))

    def test_06_fractional_year_and_population(self):
        self.assertIn("fractional", reason(year=1952.5))
        self.assertIn("fractional", reason(pop="100.5"))
        self.assertEqual(parse_integer("1952.0"), 1952)
        self.assertEqual(parse_integer(1952.0), 1952)

    def test_07_non_finite_values(self):
        for bad in ("nan", "inf", "-inf", "Infinity", float("inf"), float("-inf"), "1e999"):
            self.assertIn("non-finite", reason(lifeExp=bad), msg=str(bad))
        self.assertIn("non-finite", reason(pop="NaN"))

    def test_07_out_of_range_values(self):
        self.assertIn("greater than 120", reason(lifeExp="150"))
        self.assertIn("not greater than 0", reason(lifeExp=0))
        self.assertIn("not greater than 0", reason(pop=-1))
        self.assertIn("not greater than 0", reason(gdpPercap="0"))
        self.assertIn("not in allowed years", reason(year=1953))
        self.assertIn("not in allowed set", reason(continent="Atlantis"))
        clean, _ = validate_record(record(lifeExp=120), SCHEMA)
        self.assertIsNotNone(clean)  # boundary: at most 120 is allowed

    def test_missing_and_empty_values(self):
        self.assertIn("country", reason(country=""))
        self.assertIn("country", reason(country="   "))
        self.assertIn("country", reason(country=None))
        self.assertIn("pop", reason(pop=float("nan")))
        self.assertIn("continent", reason(continent=""))

    def test_booleans_are_not_numbers(self):
        with self.assertRaises(ValueError):
            parse_float(True)

    def test_validation_result_collects_and_keeps_original_values(self):
        frame = raw_frame([GOOD, ("", "Asia", 2007, 1.0, 1, 1.0), ("X", "Asia", "bad", 1.0, 1, 1.0), GOOD])
        result = validate_dataframe(frame, SCHEMA, "fake.csv")
        self.assertIsInstance(result, ValidationResult)
        self.assertEqual((result.accepted_count, result.rejected_count), (2, 2))
        self.assertEqual([q["source_record"] for q in result.quarantined], [2, 3])
        self.assertEqual(result.quarantined[1]["year"], "bad")
        self.assertEqual(result.quarantined[0]["country"], "")
        typed = result.to_frame(SCHEMA)
        self.assertEqual(str(typed["year"].dtype), "int64")
        self.assertEqual(str(typed["pop"].dtype), "int64")
        self.assertEqual(result.reason_counts()["country"], 1)


class ParquetReader(unittest.TestCase):
    def test_parquet_reader_logic_with_fake_dataframe(self):
        fake = pd.DataFrame({"COUNTRY": ["A", None], "YEAR": ["2007", "x"]})
        with mock.patch("pandas.read_parquet", return_value=fake):
            out = read_parquet_source(DATA_DIR / "country_records.parquet", {"engine": "pyarrow"})
        self.assertEqual(out["source_record"].tolist(), [1, 2])
        self.assertEqual(out["YEAR"].tolist(), ["2007", "x"])

    @unittest.skipUnless(HAS_PYARROW, "pyarrow is not installed")
    def test_parquet_real_file(self):
        from helpers import settings_for
        out = read_parquet_source(DATA_DIR / "country_records.parquet", settings_for("parquet"))
        self.assertEqual(len(out), 1712)
        self.assertIn("LIFE_EXP", out.columns)


if __name__ == "__main__":
    unittest.main()
