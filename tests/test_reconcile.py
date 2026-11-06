"""Duplicates, conflicts, missing key, reordered records, NumPy totals."""
import unittest

import numpy as np

from helpers import DATA_DIR, ORDER, SCHEMA, make_frame, plain_csv_settings, raw_frame, settings_for
from src.common import ConflictError, SchemaError
from src.matrix import (
    asia_total,
    build_population_matrix,
    index_by_loop,
    index_to_baseline,
    matrix_to_frame,
)
from src.pipeline import recover_source
from src.reconcile import (
    check_conflicts,
    compare_tables,
    remove_exact_duplicates,
    require_key_columns,
    sort_canonical,
)
from src.validation import map_columns, validate_dataframe

A = ("Aland", "Asia", 2007, 70.0, 100, 1.0)
B = ("Bland", "Europe", 1952, 60.0, 200, 2.0)


class Duplicates(unittest.TestCase):
    def test_08_exact_duplicates_removed_and_logged(self):
        df = make_frame([A, B, A, A])
        clean, log = remove_exact_duplicates(df, "f.csv", ORDER)
        self.assertEqual(len(clean), 2)
        self.assertEqual([r["source_record"] for r in log], [3, 4])
        self.assertTrue(all(r["duplicate_of_record"] == 1 for r in log))
        self.assertEqual(log[0]["country"], "Aland")

    def test_08_real_file_has_two_duplicates(self):
        rec = recover_source(settings_for("csv"), SCHEMA, DATA_DIR, [])
        self.assertEqual(len(rec.duplicates), 2)


class Conflicts(unittest.TestCase):
    def test_09_conflicting_key_stops(self):
        df = make_frame([A, ("Aland", "Asia", 2007, 71.0, 100, 1.0)])
        deduped, _ = remove_exact_duplicates(df, "f.csv", ORDER)
        with self.assertRaises(ConflictError):
            check_conflicts(deduped, SCHEMA["key"], "f.csv")

    def test_09_conflicting_key_csv_fixture_stops(self):
        with self.assertRaises(ConflictError):
            recover_source(plain_csv_settings("conflicting_key.csv"), SCHEMA, DATA_DIR, [])

    def test_no_conflict_for_identical_copies(self):
        deduped, _ = remove_exact_duplicates(make_frame([A, A]), "f.csv", ORDER)
        check_conflicts(deduped, SCHEMA["key"], "f.csv")  # must not raise


class MissingKey(unittest.TestCase):
    def test_10_missing_key_column_is_file_error(self):
        df = make_frame([A]).drop(columns=["year"])
        with self.assertRaises(SchemaError):
            require_key_columns(df, SCHEMA["key"], "f.csv")

    def test_10_missing_key_value_is_quarantined(self):
        raw = raw_frame([A, ("", "Asia", 2007, 70.0, 100, 1.0), ("Cland", "Asia", None, 70.0, 100, 1.0)])
        mapped = map_columns(raw, {c: c for c in ORDER}, ORDER, "f")
        result = validate_dataframe(mapped, SCHEMA, "f")
        self.assertEqual(result.rejected_count, 2)
        self.assertEqual(result.accepted_count, 1)


class ReorderedRecords(unittest.TestCase):
    def test_11_reordered_records_still_agree(self):
        left = sort_canonical(make_frame([A, B, ("Cland", "Africa", 1957, 50.0, 300, 3.0)]), SCHEMA["key"])
        shuffled = make_frame([("Cland", "Africa", 1957, 50.0, 300, 3.0), A, B])
        self.assertEqual(compare_tables(left, shuffled, SCHEMA), [])

    def test_sort_by_country_then_year(self):
        df = make_frame([("B", "Asia", 2002, 1.0, 1, 1.0), ("A", "Asia", 2007, 1.0, 1, 1.0), ("A", "Asia", 1952, 1.0, 1, 1.0)])
        out = sort_canonical(df, SCHEMA["key"])
        self.assertEqual(list(zip(out["country"], out["year"])), [("A", 1952), ("A", 2007), ("B", 2002)])

    def test_differences_are_detected(self):
        base = make_frame([A, B])
        self.assertTrue(any("keys differ" in p for p in compare_tables(base, make_frame([A]), SCHEMA)))
        changed_int = make_frame([A, ("Bland", "Europe", 1952, 60.0, 201, 2.0)])
        self.assertTrue(compare_tables(base, changed_int, SCHEMA))
        changed_text = make_frame([A, ("Bland", "Asia", 1952, 60.0, 200, 2.0)])
        self.assertTrue(compare_tables(base, changed_text, SCHEMA))

    def test_float_tolerance_is_absolute_1e_8(self):
        base = make_frame([A])
        within = make_frame([("Aland", "Asia", 2007, 70.0 + 5e-9, 100, 1.0)])
        outside = make_frame([("Aland", "Asia", 2007, 70.0 + 5e-8, 100, 1.0)])
        self.assertEqual(compare_tables(base, within, SCHEMA, 1e-8), [])
        self.assertTrue(compare_tables(base, outside, SCHEMA, 1e-8))


class NumpyMatrix(unittest.TestCase):
    def setUp(self):
        rows = []
        for country, start in (("P", 100), ("I", 200), ("T", 50)):
            for i, year in enumerate((1982, 1987, 1992, 1997, 2002, 2007)):
                rows.append((country, "Asia", year, 60.0, start + 10 * i, 1.0))
        self.df = make_frame(rows)
        self.years = [1982, 1987, 1992, 1997, 2002, 2007]

    def test_12_matrix_shapes_and_broadcast(self):
        m = build_population_matrix(self.df, ["P", "I", "T"], self.years)
        info = index_to_baseline(m, 0)
        self.assertEqual(info["shape_matrix"], (3, 6))
        self.assertEqual(info["shape_baseline"], (3, 1))
        self.assertEqual(info["shape_index"], (3, 6))
        self.assertTrue(np.allclose(info["index"][:, 0], 100.0))
        self.assertTrue(np.allclose(info["index"], index_by_loop(m, 0), rtol=0, atol=1e-8))
        self.assertAlmostEqual(info["index"][0, 1], 110.0)  # 110 / 100 * 100

    def test_zero_baseline_is_rejected(self):
        from src.common import ProcessingError
        with self.assertRaises(ProcessingError):
            index_to_baseline(np.array([[0, 5]]), 0)
            
    def test_asia_total_matches_pandas(self):
        rows, total = asia_total(self.df, 2007)
        self.assertEqual(rows, 3)
        self.assertEqual(total, int(self.df.loc[self.df["year"] == 2007, "pop"].sum()))
        self.assertEqual(asia_total(self.df, 1999), (0, 0))

    def test_boolean_selection_ignores_other_continents(self):
        df = make_frame([("A", "Asia", 2007, 1.0, 10, 1.0), ("B", "Europe", 2007, 1.0, 99, 1.0)])
        self.assertEqual(asia_total(df, 2007), (1, 10))

    def test_matrix_requires_exactly_one_row_per_cell(self):
        from src.common import ProcessingError
        with self.assertRaises(ProcessingError):
            build_population_matrix(self.df, ["P", "Nowhere"], self.years)

    def test_matrix_frame_has_named_year_columns(self):
        m = build_population_matrix(self.df, ["P", "I", "T"], self.years)
        frame = matrix_to_frame(["P", "I", "T"], self.years, index_to_baseline(m, 0)["index"])
        self.assertEqual(list(frame.columns), ["country", "1982", "1987", "1992", "1997", "2002", "2007"])

    def test_real_data_asia_2007_total(self):
        from src.analysis import asia_selected_year
        clean = recover_source(settings_for("csv"), SCHEMA, DATA_DIR, []).clean
        rows, total = asia_total(clean, 2007)
        self.assertEqual((rows, total), (33, 3811953827))
        self.assertEqual(total, int(asia_selected_year(clean, 2007)["pop"].sum()))


if __name__ == "__main__":
    unittest.main()

