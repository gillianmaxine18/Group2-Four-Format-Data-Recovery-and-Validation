# Group 2: DSA4153 Week 10 - Four-Format Data Recovery and Validation

Recovers the same clean Gapminder table (1,704 rows) from CSV, Excel, JSON and Parquet, proves the four agree,
runs pandas/NumPy analysis, exports four formats, and verifies every export by reloading it.

## Setup and run

```
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_tests.py                  # writes test_results.txt
python main.py --config config.json  # writes outputs/
python main.py --config config.json --reporting-year 1997   # or edit "reporting_year" in config.json
jupyter nbconvert --to html --execute report.ipynb          # report.html
```

Exit status is 0 on success and 1 on any failure. A failed run writes only `outputs/failed_validation_report.csv`
and never overwrites earlier successful outputs (all files are built in a hidden `.staging_*` folder first).
`data/` must stay unchanged (byte-for-byte; see `.gitattributes`).

## Layout

| Path | Purpose |
|---|---|
| `main.py` | CLI entry point |
| `config.json` | inputs, column mappings, schema/rules, reporting year, matrix selection, exports, expected controls |
| `src/common.py` | exceptions, `Recovery`, config loading |
| `src/readers.py`, `src/parquet_reader.py` | CSV / Excel / JSON / Parquet readers (original values + position kept) |
| `src/validation.py` | column mapping, `validate_record`, `ValidationResult` class |
| `src/reconcile.py` | duplicates, conflicts, sorting, comparison by key (tolerance 1e-8) |
| `src/matrix.py`, `src/analysis.py` | NumPy matrix and pandas analysis |
| `src/export.py`, `src/audit.py`, `src/pipeline.py` | exports, reload checks, staging, audit log, orchestration |
| `tests/`, `run_tests.py` | automated checks (unittest); fixtures are made in temp folders |
| `report.ipynb` | report that imports the code |

## Group 2 - Task ownership and Git identities

| Member | Git identity | Branch | Files |
|---|---|---|---|
| 1 Gillian Maxine Estilloso | `@gillianmaxine18` | `maxine(task1)-readers-analysis` | `src/readers.py`, `src/analysis.py`, `config.json` |
| 2 Kaycelyn Tigas | `@kaycelyntigas` | `kaycelyn-validation` | `src/validation.py`, `src/parquet_reader.py` |
| 3 Giana Elisha Tuplano | `@gianaelishatuplano-jpg` | `elisha-reconcile-numpy` | `src/reconcile.py`, `src/matrix.py` |
| 4 Hans Adrian Laudato | `hansadrianlaudato-oss` | `Hans-export-cli` | `main.py`, `src/common.py`, `src/export.py`, `src/audit.py`, `src/pipeline.py`, `run_tests.py` |

## How the 12 required failure categories are covered

| # | Category | Test |
|---|---|---|
| 1 | normal four-format recovery | `test_member1...NormalRecovery`, `test_member4...test_full_run_...` |
| 2 | missing file | `test_member1...test_02_missing_file` |
| 3 | existing unsupported format | `test_member1...test_03_existing_unsupported_format` |
| 4 | missing column | `test_member2...MissingColumn` |
| 5 | missing key | `test_member3...MissingKey` |
| 6 | unparseable number | `test_member2...test_05_unparseable_number` |
| 7 | fractional year/population | `test_member2...test_06_fractional_year_and_population` |
| 8 | non-finite / out-of-range | `test_member2...test_07_*` |
| 9 | exact duplicates | `test_member3...Duplicates` |
| 10 | conflicting keys | `test_member3...Conflicts`, `test_member4...test_15_conflicting_key_...` |
| 11 | reordered records | `test_member3...ReorderedRecords` |
| 12 | corrupted export values | `test_member4...test_14_corrupted_export_values_fail_comparison` |

(The numbers in the test names are historical labels, use this table for the category mapping.)

## Notes on reloaded types

CSV/Excel/JSON give back plain `object` text columns, and CSV/Excel may give back different integer widths, so after reload
`apply_schema` converts text columns to pandas `string` and numbers to `int64`/`float64` (refusing fractional or non-finite
values) before comparing with the pre-export table. Each conversion is written in `audit_log.csv`.

## Fresh-clone verification, AI disclosure

Record the verifying member and date in `submission_manifest.txt`. AI assistance used: TODO (state exactly what, per the course AI policy).
