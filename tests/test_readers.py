"""Member 1 tests: normal recovery, missing file, unsupported format, analysis results."""
import unittest
from pathlib import Path

from helpers import CONFIG, DATA_DIR, HAS_PYARROW, SCHEMA, settings_for
from src.analysis import asia_selected_year, country_history
from src.common import InputFileError, UnsupportedFormatError
from src.pipeline import recover_source
from src.readers import flatten_record, read_source
from src.reconcile import compare_tables


def recover(fmt: str):
    """Recover one configured input file."""
    return recover_source(settings_for(fmt), SCHEMA, DATA_DIR, [])


class NormalRecovery(unittest.TestCase):
    def check_counts(self, fmt: str) -> None:
        rec = recover(fmt)
        exp = CONFIG["expected"]["per_file"]
        self.assertEqual(rec.raw_count, exp["raw_rows"])
        self.assertEqual(rec.validation.rejected_count, exp["rejected_rows"])
        self.assertEqual(len(rec.duplicates), exp["exact_duplicates_removed"])
        self.assertEqual(len(rec.clean), exp["canonical_rows"])

    def test_01_normal_recovery_csv(self):
        self.check_counts("csv")

    def test_01_normal_recovery_xlsx(self):
        self.check_counts("xlsx")

    def test_01_normal_recovery_json(self):
        self.check_counts("json")

    @unittest.skipUnless(HAS_PYARROW, "pyarrow is not installed")
    def test_01_normal_recovery_parquet(self):
        self.check_counts("parquet")

    def test_01_csv_positions_start_at_one_and_skip_comments(self):
        raw = read_source(DATA_DIR / "country_records.csv", settings_for("csv"))
        self.assertEqual(int(raw["source_record"].iloc[0]), 1)
        self.assertEqual(len(raw), 1712)
        self.assertIn("CountryName", raw.columns)

    def test_01_csv_reads_cp1252_text(self):
        raw = read_source(DATA_DIR / "country_records.csv", settings_for("csv"))
        self.assertTrue(raw["export_note"].str.contains("Parañaque").all())

    def test_01_formats_agree(self):
        a, b, c = recover("csv").clean, recover("xlsx").clean, recover("json").clean
        self.assertEqual(compare_tables(a, b, SCHEMA), [])
        self.assertEqual(compare_tables(a, c, SCHEMA), [])

    def test_json_flatten(self):
        self.assertEqual(flatten_record({"a": {"b": 1, "c": {"d": 2}}, "e": 3}), {"a.b": 1, "a.c.d": 2, "e": 3})


class FileLevelErrors(unittest.TestCase):
    def test_02_missing_file(self):
        with self.assertRaises(InputFileError):
            read_source(DATA_DIR / "does_not_exist.csv", settings_for("csv"))

    def test_03_existing_unsupported_format(self):
        settings = {"file": "unsupported.txt", "format": "txt"}
        with self.assertRaises(UnsupportedFormatError):
            read_source(DATA_DIR / "unsupported.txt", settings)


class Analysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = recover("csv").clean

    def test_asia_2007_rows_population_and_rank(self):
        asia = asia_selected_year(self.df, 2007)
        controls = CONFIG["expected"]["controls"]
        self.assertEqual(len(asia), controls["asia_2007_rows"])
        self.assertEqual(int(asia["pop"].sum()), controls["asia_2007_population"])
        self.assertEqual(int(asia["lifeExp_rank"].min()), 1)
        self.assertTrue(asia["lifeExp_rank"].is_monotonic_increasing)
        self.assertAlmostEqual(asia["pop_millions"].iloc[0] * 1e6, asia["pop"].iloc[0])

    def test_reporting_year_1997_changes_selection(self):
        asia = asia_selected_year(self.df, 1997)
        self.assertTrue((asia["year"] == 1997).all())
        self.assertEqual(len(asia), 33)

    def test_rank_uses_min_method_for_ties(self):
        import pandas as pd
        from helpers import make_frame
        df = make_frame([("A", "Asia", 2007, 70.0, 1, 1.0), ("B", "Asia", 2007, 70.0, 2, 1.0), ("C", "Asia", 2007, 60.0, 3, 1.0)])
        out = asia_selected_year(df, 2007)
        self.assertEqual(out["lifeExp_rank"].tolist(), [1, 1, 3])
        self.assertEqual(out["country"].tolist(), ["A", "B", "C"])

    def test_philippines_history(self):
        hist = country_history(self.df, "Philippines")
        self.assertEqual(len(hist), 12)
        self.assertTrue(hist["year"].is_monotonic_increasing)
        self.assertEqual(float(hist["lifeExp_change"].iloc[0]), 0.0)
        self.assertEqual(int(hist.loc[hist["year"] == 2007, "pop"].iloc[0]), 91077287)


if __name__ == "__main__":
    unittest.main()
