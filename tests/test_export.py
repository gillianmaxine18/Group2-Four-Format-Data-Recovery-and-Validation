"""Member 4 tests: corrupted export, round trips, staging / no overwrite, CLI exit status."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from helpers import DATA_DIR, HAS_PYARROW, SCHEMA, plain_csv_settings, runnable_config, settings_for
from main import main as cli_main
from src.audit import add_audit, make_check
from src.common import SchemaError
from src.export import apply_schema, read_export, roundtrip_check, write_export
from src.pipeline import recover_source, run_pipeline

FORMATS = ["csv", "xlsx", "json"] + (["parquet"] if HAS_PYARROW else [])


def canonical():
    return recover_source(settings_for("csv"), SCHEMA, DATA_DIR, []).clean.drop(columns=["source_record"])


class RoundTrips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = canonical()

    def test_13_round_trip_all_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            for fmt in FORMATS:
                path = Path(tmp) / f"c.{fmt}"
                write_export(self.df, path, fmt)
                problems, _ = roundtrip_check(self.df, path, fmt, SCHEMA, 1e-8)
                self.assertEqual(problems, [], msg=fmt)

    def test_exports_have_no_index_and_six_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            for fmt in FORMATS:
                path = Path(tmp) / f"c.{fmt}"
                write_export(self.df, path, fmt)
                raw = read_export(path, fmt)
                self.assertEqual(list(raw.columns), SCHEMA["canonical_order"], msg=fmt)
                self.assertEqual(len(raw), 1704, msg=fmt)

    def test_excel_sheet_and_json_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_export(self.df, Path(tmp) / "c.xlsx", "xlsx")
            self.assertEqual(pd.ExcelFile(Path(tmp) / "c.xlsx").sheet_names, ["observations"])
            write_export(self.df, Path(tmp) / "c.json", "json")
            data = json.loads((Path(tmp) / "c.json").read_text(encoding="utf-8"))
            self.assertIsInstance(data, list)
            self.assertEqual(set(data[0]), set(SCHEMA["canonical_order"]))

    def test_types_after_reload_are_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            for fmt in FORMATS:
                path = Path(tmp) / f"c.{fmt}"
                write_export(self.df, path, fmt)
                fixed = apply_schema(read_export(path, fmt), SCHEMA)
                self.assertEqual({c: str(fixed[c].dtype) for c in fixed}, SCHEMA["dtypes"], msg=fmt)

    def test_14_corrupted_export_values_fail_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # CSV: change one population
            path = tmp / "c.csv"
            write_export(self.df, path, "csv")
            raw = pd.read_csv(path, keep_default_na=False)
            raw.loc[10, "pop"] += 1
            raw.to_csv(path, index=False)
            problems, _ = roundtrip_check(self.df, path, "csv", SCHEMA, 1e-8)
            self.assertTrue(any("pop" in p for p in problems))
            # JSON: change one float by more than the tolerance
            path = tmp / "c.json"
            write_export(self.df, path, "json")
            data = json.loads(path.read_text(encoding="utf-8"))
            data[5]["lifeExp"] += 0.001
            path.write_text(json.dumps(data), encoding="utf-8")
            problems, _ = roundtrip_check(self.df, path, "json", SCHEMA, 1e-8)
            self.assertTrue(any("lifeExp" in p for p in problems))
            # Excel: change a text value
            path = tmp / "c.xlsx"
            write_export(self.df, path, "xlsx")
            raw = pd.read_excel(path, sheet_name="observations", keep_default_na=False)
            raw.loc[3, "continent"] = "Asia" if raw.loc[3, "continent"] != "Asia" else "Europe"
            raw.to_excel(path, sheet_name="observations", index=False)
            problems, _ = roundtrip_check(self.df, path, "xlsx", SCHEMA, 1e-8)
            self.assertTrue(any("continent" in p for p in problems))

    def test_14_deleted_rows_and_bad_types_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.csv"
            write_export(self.df.iloc[:-1], path, "csv")
            problems, _ = roundtrip_check(self.df, path, "csv", SCHEMA, 1e-8)
            self.assertTrue(any("keys differ" in p for p in problems))
            write_export(self.df, path, "csv")
            raw = pd.read_csv(path, keep_default_na=False)
            raw["year"] = raw["year"].astype(float) + 0.5
            with self.assertRaises(SchemaError):
                apply_schema(raw, SCHEMA)


class AuditAndChecks(unittest.TestCase):
    def test_audit_steps_are_numbered(self):
        audit = []
        add_audit(audit, "f", "parse", "rule", 0, 5)
        add_audit(audit, "f", "validate", "rule", 5, 4)
        self.assertEqual([a["step"] for a in audit], [1, 2])
        self.assertEqual(list(audit[0]), ["step", "source_file", "operation", "rule", "rows_before", "rows_after"])

    def test_make_check_tolerance(self):
        self.assertTrue(make_check("x", 1.0, 1.0 + 5e-9, 1e-8)["pass"])
        self.assertFalse(make_check("x", 1.0, 1.0 + 5e-7, 1e-8)["pass"])
        self.assertFalse(make_check("x", 1, 2)["pass"])


class PipelineAndCli(unittest.TestCase):
    def test_full_run_publishes_all_outputs_and_reconciles(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            cfg = runnable_config(out)
            self.assertEqual(run_pipeline(cfg, Path(tmp)), 0)
            names = {p.name for p in out.iterdir()}
            for expected in ("quarantine.csv", "duplicate_log.csv", "validation.csv", "audit_log.csv",
                             "asia_selected_year.csv", "country_history.csv", "population_index.csv",
                             "canonical.csv", "canonical.xlsx", "canonical.json"):
                self.assertIn(expected, names)
            n = len(cfg["inputs"])
            self.assertEqual(len(pd.read_csv(out / "quarantine.csv")), 6 * n)
            self.assertEqual(len(pd.read_csv(out / "duplicate_log.csv")), 2 * n)
            self.assertEqual(len(pd.read_csv(out / "canonical.csv")), 1704)
            self.assertEqual(len(pd.read_csv(out / "asia_selected_year.csv")), 33)
            self.assertEqual(len(pd.read_csv(out / "country_history.csv")), 12)
            self.assertEqual(list(pd.read_csv(out / "population_index.csv").columns),
                             ["country", "1982", "1987", "1992", "1997", "2002", "2007"])
            validation = pd.read_csv(out / "validation.csv")
            self.assertTrue(validation["pass"].all())
            audit = pd.read_csv(out / "audit_log.csv")
            self.assertEqual(list(audit.columns), ["step", "source_file", "operation", "rule", "rows_before", "rows_after"])
            self.assertFalse(any(p.name.startswith(".staging_") for p in Path(tmp).iterdir()))

    def test_reporting_year_1997_regenerates_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            cfg = runnable_config(out, reporting_year=1997)
            self.assertEqual(run_pipeline(cfg, Path(tmp)), 0)
            asia = pd.read_csv(out / "asia_selected_year.csv")
            self.assertTrue((asia["year"] == 1997).all())
            self.assertEqual(len(asia), 33)

    def test_15_conflicting_key_fails_nonzero_and_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            cfg = runnable_config(out)
            cfg["inputs"] = [plain_csv_settings("conflicting_key.csv")]
            self.assertEqual(run_pipeline(cfg, Path(tmp)), 1)
            self.assertEqual([p.name for p in out.iterdir()], ["failed_validation_report.csv"])
            report = pd.read_csv(out / "failed_validation_report.csv")
            self.assertIn("ConflictError", str(report["actual"].iloc[-1]))
            self.assertFalse(any(p.name.startswith(".staging_") for p in Path(tmp).iterdir()))

    def test_16_failed_run_does_not_overwrite_earlier_successful_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            sentinel = out / "asia_selected_year.csv"
            sentinel.write_text("previous successful run\n", encoding="utf-8")
            cfg = runnable_config(out)
            cfg["inputs"] = [plain_csv_settings("missing_column.csv")]
            self.assertEqual(run_pipeline(cfg, Path(tmp)), 1)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "previous successful run\n")
            self.assertFalse((out / "validation.csv").exists())

    def test_disagreeing_formats_fail_and_publish_nothing(self):
        import src.pipeline as pipeline
        original = pipeline.recover_source

        def tampered(settings, schema, data_dir, audit):
            rec = original(settings, schema, data_dir, audit)
            if settings["format"] == "xlsx":
                clean = rec.clean.copy()
                clean.loc[0, "pop"] += 5
                rec = rec._replace(clean=clean)
            return rec

        pipeline.recover_source = tampered
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "out"
                self.assertEqual(run_pipeline(runnable_config(out), Path(tmp)), 1)
                self.assertEqual([p.name for p in out.iterdir()], ["failed_validation_report.csv"])
        finally:
            pipeline.recover_source = original

    def test_missing_file_and_unsupported_input_fail(self):
        for bad in ({"file": "nope.csv", "format": "csv"}, {"file": "unsupported.txt", "format": "txt"}):
            with tempfile.TemporaryDirectory() as tmp:
                cfg = runnable_config(Path(tmp) / "out")
                cfg["inputs"] = [bad]
                self.assertEqual(run_pipeline(cfg, Path(tmp)), 1)

    def test_cli_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = runnable_config(Path(tmp) / "out")
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(cfg), encoding="utf-8")
            self.assertEqual(cli_main(["--config", str(path)]), 0)
            self.assertEqual(cli_main(["--config", str(path), "--reporting-year", "1997"]), 0)
            self.assertEqual(cli_main(["--config", str(Path(tmp) / "missing.json")]), 1)


if __name__ == "__main__":
    unittest.main()
