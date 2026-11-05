"""Pipeline: recover each file, reconcile, analyse, export and verify.  Owner: Member 4."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from .analysis import asia_selected_year, country_history
from .audit import add_audit, make_check, write_audit, write_checks, write_table
from .common import (
    AgreementError,
    CheckFailedError,
    ProcessingError,
    Recovery,
)
from .export import (
    discard_staging,
    make_staging,
    publish_staging,
    roundtrip_check,
    write_export,
    write_failed_report,
)
from .matrix import (
    asia_total,
    build_population_matrix,
    index_by_loop,
    index_to_baseline,
    matrix_to_frame,
)
from .readers import read_source
from .reconcile import check_conflicts, compare_all, remove_exact_duplicates, sort_canonical
from .validation import map_columns, unmapped_columns, validate_dataframe

QUARANTINE_COLUMNS = ["source_file", "source_record", "reason"]
DUPLICATE_COLUMNS = ["source_file", "source_record", "duplicate_of_record"]


def recover_source(settings: dict, schema: dict, data_dir: Path, audit: list[dict]) -> Recovery:
    """Run parse, map, validate, de-duplicate, conflict-check and sort for one file."""
    name = settings["file"]
    order = list(schema["canonical_order"])
    raw = read_source(Path(data_dir) / name, settings)
    n_raw = len(raw)
    add_audit(audit, name, "parse", f"read {settings.get('format')} layout, keep original values and order", 0, n_raw)
    mapping = settings["source_to_canonical"]
    mapped = map_columns(raw, mapping, order, name)
    ignored = unmapped_columns(raw, mapping)
    add_audit(audit, name, "map_columns", f"rename to canonical names; ignored columns {ignored}", n_raw, n_raw)
    result = validate_dataframe(mapped, schema, name)
    add_audit(audit, name, "validate", "type/domain rules from schema; invalid rows to quarantine", n_raw, result.accepted_count)
    valid = result.to_frame(schema)
    deduped, duplicates = remove_exact_duplicates(valid, name, order)
    add_audit(audit, name, "deduplicate", "remove exact duplicate valid records, log each copy", len(valid), len(deduped))
    check_conflicts(deduped, schema["key"], name)
    add_audit(audit, name, "conflict_check", "same (country, year) must not disagree on other fields", len(deduped), len(deduped))
    clean = sort_canonical(deduped, schema["key"])
    add_audit(audit, name, "sort", "sort by country then year", len(clean), len(clean))
    return Recovery(name, n_raw, clean, result, duplicates)


# ----------------------------------------------------------------- checks
def reconciliation_checks(rec: Recovery, settings: dict, expected: dict) -> list[dict]:
    """Row reconciliation for one input: raw = rejected + duplicates + canonical."""
    n = rec.source_file
    rejected, dups, canon = rec.validation.rejected_count, len(rec.duplicates), len(rec.clean)
    return [
        make_check(f"{n}: raw rows", settings["raw_records"], rec.raw_count),
        make_check(f"{n}: rejected rows", expected["rejected_rows"], rejected),
        make_check(f"{n}: exact duplicate copies removed", expected["exact_duplicates_removed"], dups),
        make_check(f"{n}: canonical rows", expected["canonical_rows"], canon),
        make_check(f"{n}: raw = rejected + duplicates + canonical", rec.raw_count, rejected + dups + canon),
    ]


def domain_checks(df: pd.DataFrame, schema: dict, controls: dict) -> list[dict]:
    """Key and domain checks on the shared canonical table (sets are used for membership)."""
    key = schema["key"]
    return [
        make_check("canonical: repeated keys", 0, int(df.duplicated(subset=key).sum())),
        make_check("canonical: distinct countries", controls["countries"], df["country"].nunique()),
        make_check("canonical: years outside allowed set", 0, len(set(df["year"]) - set(schema["allowed_years"]))),
        make_check("canonical: continents outside allowed set", 0, len(set(df["continent"]) - set(schema["allowed_continents"]))),
        make_check("canonical: missing values", 0, int(df.isna().sum().sum())),
        make_check("canonical: empty text values", 0, int((df["country"].str.len() == 0).sum())),
        make_check("canonical: column order", ",".join(schema["canonical_order"]), ",".join(df.columns)),
        make_check(
            "canonical: dtypes match schema",
            str({c: schema["dtypes"][c] for c in schema["canonical_order"]}),
            str({c: str(df[c].dtype) for c in schema["canonical_order"]}),
        ),
    ]


def run_stages(config: dict, base_dir: Path, stage: Path, audit: list[dict], checks: list[dict]) -> None:
    """Do all the work, writing results only into the staging folder."""
    schema = config["schema"]
    atol = config["tolerance"]["abs"]
    year = int(config["reporting_year"])
    data_dir = base_dir / config["data_dir"]
    expected = config["expected"]
    controls = expected["controls"]
    order = list(schema["canonical_order"])
    n_inputs = len(config["inputs"])

    # 1-4: recover every input independently
    recoveries: dict[str, Recovery] = {}
    for settings in config["inputs"]:
        rec = recover_source(settings, schema, data_dir, audit)
        recoveries[settings["file"]] = rec
        checks.extend(reconciliation_checks(rec, settings, expected["per_file"]))
    quarantined = [row for rec in recoveries.values() for row in rec.validation.quarantined]
    duplicates = [row for rec in recoveries.values() for row in rec.duplicates]
    checks.append(make_check("all inputs: quarantined records", expected["per_file"]["rejected_rows"] * n_inputs, len(quarantined)))
    checks.append(make_check("all inputs: duplicate copies removed", expected["per_file"]["exact_duplicates_removed"] * n_inputs, len(duplicates)))

    # 5: agreement across formats, compared by key
    tables = {name: rec.clean[order] for name, rec in recoveries.items()}
    differences = compare_all(tables, schema, atol)
    reference = next(iter(tables))
    for name, problems in differences.items():
        checks.append(make_check(f"agreement: {name} vs {reference}", 0, len(problems), atol))
    add_audit(audit, "all", "compare_formats", f"keys/text/integers exact, floats abs tol {atol}", n_inputs, n_inputs)
    if any(differences.values()):
        raise AgreementError("formats disagree: " + "; ".join(f"{k}: {v}" for k, v in differences.items() if v))
    canonical = tables[reference].reset_index(drop=True)
    add_audit(audit, "canonical", "build_canonical", "shared table created after agreement passed", len(canonical), len(canonical))
    checks.extend(domain_checks(canonical, schema, controls))

    # analysis with pandas and NumPy
    asia = asia_selected_year(canonical, year, config["analysis"]["continent"])
    history = country_history(canonical, config["analysis"]["history_country"])
    np_rows, np_total = asia_total(canonical, year, config["analysis"]["continent"])
    checks.append(make_check(f"asia {year}: rows pandas vs NumPy mask", len(asia), np_rows))
    checks.append(make_check(f"asia {year}: population pandas vs NumPy", int(asia["pop"].sum()), np_total))
    checks.append(make_check(f"asia {year}: best life-expectancy rank is 1", 1, int(asia["lifeExp_rank"].min())))
    checks.append(make_check(f"asia {year}: sorted by rank then country", True, bool(asia.equals(asia.sort_values(["lifeExp_rank", "country"]).reset_index(drop=True)))))
    if year == controls["year"]:
        checks.append(make_check(f"asia {year}: rows (control)", controls["asia_2007_rows"], len(asia)))
        checks.append(make_check(f"asia {year}: population (control)", controls["asia_2007_population"], np_total))
    country = config["analysis"]["history_country"]
    checks.append(make_check(f"{country}: history rows", controls["philippines_rows"], len(history)))
    last = history.loc[history["year"] == controls["year"], "pop"]
    checks.append(make_check(f"{country} {controls['year']}: population (control)", controls["philippines_2007_population"], int(last.iloc[0]) if len(last) else -1))
    checks.append(make_check(f"{country}: first life-expectancy change is 0", 0.0, float(history["lifeExp_change"].iloc[0]), atol))

    m_cfg = config["matrix"]
    countries, years = m_cfg["countries"], m_cfg["years"]
    base_col = years.index(m_cfg["baseline_year"])
    matrix = build_population_matrix(canonical, countries, years)
    info = index_to_baseline(matrix, base_col)
    loop = index_by_loop(matrix, base_col)
    checks.append(make_check("numpy: matrix shape", str((len(countries), len(years))), str(info["shape_matrix"])))
    checks.append(make_check("numpy: baseline shape before broadcast", str((len(countries), 1)), str(info["shape_baseline"])))
    checks.append(make_check("numpy: index shape after broadcast", str((len(countries), len(years))), str(info["shape_index"])))
    checks.append(make_check("numpy: broadcast vs loop max abs difference", 0.0, float(abs(info["index"] - loop).max()), atol))
    checks.append(make_check("numpy: baseline column equals 100", 0.0, float(abs(info["index"][:, base_col] - 100.0).max()), atol))

    # write analytical outputs (staging only)
    write_table(quarantined, QUARANTINE_COLUMNS + order, stage / "quarantine.csv")
    write_table(duplicates, DUPLICATE_COLUMNS + order, stage / "duplicate_log.csv")
    asia.to_csv(stage / "asia_selected_year.csv", index=False)
    history.to_csv(stage / "country_history.csv", index=False)
    matrix_to_frame(countries, years, info["index"]).to_csv(stage / "population_index.csv", index=False)
    add_audit(audit, "outputs", "write_analysis", f"asia {year}, history, population index", len(canonical), len(asia))

    # exports and round trips
    sheet = config.get("export_sheet", "observations")
    for fmt, filename in config["exports"].items():
        path = stage / filename
        write_export(canonical, path, fmt, sheet)
        add_audit(audit, filename, "export", f"{fmt}; six canonical fields, no row index", len(canonical), len(canonical))
        problems, conversions = roundtrip_check(canonical, path, fmt, schema, atol, sheet)
        checks.append(make_check(f"round trip {fmt}: differences after reload", 0, len(problems), atol))
        note = "; ".join(conversions) if conversions else "none needed"
        add_audit(audit, filename, "reload_compare", f"reapply schema, compare by key; conversions: {note}", len(canonical), len(canonical) if not problems else 0)

    write_checks(checks, stage / "validation.csv")
    write_audit(audit, stage / "audit_log.csv")
    failed = [c["check"] for c in checks if not c["pass"]]
    if failed:
        raise CheckFailedError(f"{len(failed)} check(s) failed: {failed[:5]}")


def run_pipeline(config: dict, base_dir: Path) -> int:
    """Run everything; publish outputs only on success. Returns a process exit status."""
    base_dir = Path(base_dir)
    output_dir = base_dir / config["output_dir"]
    stage = make_staging(output_dir)
    audit: list[dict] = []
    checks: list[dict] = []
    try:
        run_stages(config, base_dir, stage, audit, checks)
    except ProcessingError as exc:
        discard_staging(stage)
        report = write_failed_report(output_dir, checks, f"{type(exc).__name__}: {exc}")
        print(f"FAILED: {type(exc).__name__}: {exc}\nreport: {report}", file=sys.stderr)
        return 1
    except Exception as exc:  # unexpected bug: still fail safely
        discard_staging(stage)
        report = write_failed_report(output_dir, checks, f"unexpected {type(exc).__name__}: {exc}")
        print(f"FAILED (unexpected): {exc}\nreport: {report}", file=sys.stderr)
        return 1
    names = publish_staging(stage, output_dir)
    print(f"OK: {len(checks)} checks passed; published {len(names)} files to {output_dir}")
    return 0
