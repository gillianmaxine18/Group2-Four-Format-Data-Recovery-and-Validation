# **Code Review Evidence**

DSA4153 Week 10 Group Programming Challenge, Group 2 Repository: https\://github.com/gillianmaxine18/Group2-Four-Format-Data-Recovery-and-Validation

**Who reviewed whom**

| Review | Reviewer (writes the comments) | Author (writes the response) |
| ----- | ----- | ----- |
| 1 | Kaycelyn | Gillian |
| 2 | Giana | Kaycelyn |
| 3 | Hans | Giana |
| 4 | Gillian | Hans |

---

## **Review 1: Kaycelyn reviews Gillian**

* Reviewer: Kaycelyn Tigas  
* Author: Gillian Maxine Estilloso (branch `member1-readers-analysis`)  
* Reviewed commit: `e8499d1dc0350e45603c975203d85bdcae1b869f`  
* Code reviewed: `read_csv_source`, `read_excel_source`, `read_json_source`, `flatten_record`, `read_source` in `src/readers.py`; `asia_selected_year`, `country_history` in `src/analysis.py`  
* Test reviewed: `tests/test_readers.py` (commit `7194ed2cb80bd0829a6e8cc4403d5e1ea93f21a3`)

**Feedback (Kaycelyn writes)**

1. The code in the `read_csv_source` at `asia_selected_year` is working and meets all the requirements of the readers and analysis  
2. However, I noticed that when your pull request was merged into the main branch, the [readers.py](http://readers.py) and [analysis.py](http://analysis.py) were accidentally deleted. Kindly check the merge history and restore those filed to the main branch. 

**Author's response (Gillian writes)**

1. Thank you for confirming that \`read\_source\` and \`asia\_selected\_year\` meet the requirements. On your second point: you were right. After my branch was merged into \`main\`, \`src/readers.py\`, \`src/analysis.py\`, \`tests/test\_readers.py\` and \`config.json\` were no longer on \`main\`. I checked the merge history and found the cause. A mistaken revert of the merge (\`2a80b47\`, merged in PR \#4 as \`05c6fd3\`) had removed those files, and my attempt to undo it with a "Revert the revert" commit (\`2b86ac5\`) did not bring them back, because Git already recorded the branch as merged, so merging it again changed nothing.  
2. Fixed in \`b44ae1cb8d3f77937c2093d5bd287dfd2543666b\` ("Restore task1 readers and analysis files"): I copied the four files from my branch into a new commit on \`main\`. I confirmed they are back in the repository and that the tests run against them. I kept the restore as its own commit instead of rewriting history, so the revert and the restore both remain visible in the log.

---

## **Review 2: Giana reviews Kaycelyn**

* Reviewer: Giana Elisha Tuplano  
* Author: Kaycelyn Tigas (branch `kaycelyn-validation`)  
* Reviewed commit: `a7eef6664d87772cd49c9456190dd122188ad86f`  
* Code reviewed: `validate_record`, `map_columns`, `ValidationResult` in `src/validation.py`; `read_parquet_source` in `src/parquet_reader.py`  
* Test reviewed: `tests/test_validation.py` (commit `960831b051170877f57303f81f2fc80e3c496336`)

**Feedback (Giana writes)**

1. `validate_record` (line 131 of `kaycelyn-validation.py` at a7eef66): `elseparse_float(value)` is missing a space after `else`, so the file raises a SyntaxError and can’t be imported. Please fix it and confirm the tests run.  
2. I noticed you named the file `kaycelyn-validation.py`. Please follow our naming format and rename it to `src/validation.py`, because hyphens can’t be imported in Python and the tests use `src.validation`.

**Author's response (Kaycelyn writes)**

1. I accidentally deleted the space while formatting. I've added it back so it correctly reads `else parse_float(value)`. I also ran the test suite locally, and I can confirm that the file imports properly and the tests are passing now. (Commit: a7eef6664d87772cd49c9456190dd122188ad86f)   
2. Thank you. I accidentally used the branch name format. I renamed it already to validation.py (Commit: 1401cb0c11c9f5971808d16cc83bdd5b7786a1bb)

---

## **Review 3: Hans reviews Giana**

* Reviewer: Hans Adrian Laudato  
* Author: Giana Elisha Tuplano (branch `elisha-reconcile-numpy`)  
* Reviewed commit: `aaddfe5f95e21a71380be893e6ccc355f4156cb9`  
* Code reviewed: `remove_exact_duplicates`, `check_conflicts`, `compare_tables` in `src/reconcile.py`; `build_population_matrix`, `index_to_baseline` in `src/matrix.py`  
* Test reviewed: `tests/test_reconcile.py` (commit `9cf5f7a2b37856bbf93d053f55f7ee1304dca9ce`)

**Feedback (Hans writes)**

1\. In ⁠remove\_exact\_duplicates⁠ (⁠src/reconcile.py⁠), rows containing ⁠NaN⁠ values in the subset columns may not be evaluated or dropped correctly because standard Pandas equality comparisons treat ⁠NaN⁠ as unequal. Consider adding explicit handling or dropping nulls prior to duplicate checks if required.

2\. In ⁠index\_to\_baseline⁠ (⁠src/matrix.py⁠), dividing by the baseline year value can raise a ⁠ZeroDivisionError⁠ or propagate ⁠inf⁠/⁠NaN⁠ if a baseline year has a zero or missing population count. Adding an explicit zero check or warning would improve robustness.

**Author's response (Giana writes)**

1. Kept as is. `remove_exact_duplicates` compares tuples of values in a dictionary, not pandas `duplicated()`, and rows with NaN are already rejected by `validate_record` and sent to quarantine before this step, so no NaN reaches it. Dropping nulls here would hide invalid rows instead of quarantining them.  
2. Fixed in `a51accd`: `index_to_baseline` now raises `ProcessingError` when a baseline value is zero or negative, with a new test in `tests/test_reconcile.py`. A small note: NumPy gives `inf`/`NaN` on arrays rather than `ZeroDivisionError`, but the pipeline can’t produce a zero baseline, and the guard protects direct calls to the function.

---

## **Review 4: Gillian reviews Hans**

* Reviewer: Gillian Maxine Estilloso  
* Author: Hans Adrian Laudato (branch `Hans-export-cli`)  
* Reviewed commit: `26489c12c22c9de058b3188ea683b2efa348078e`  
* Code reviewed: `write_export`, `roundtrip_check` in `src/export.py`; `run_pipeline` in `src/pipeline.py`  
* Test reviewed: `tests/test_export.py` (commit `c3235ede1b947acc28404946b7392ec4101bc791`)

**Feedback (Gillian writes)**

1.  In \`write\_export\` (\`src/export.py\`), writing directly to \`path\` raises a \`FileNotFoundError\` if the parent directory does not already exist, since \`write\_export\` does not call \`path.parent.mkdir(parents=True, exist\_ok=True)\` itself.   
2.  In \`run\_pipeline\` (\`src/pipeline.py\`), the \`except ProcessingError\` and \`except Exception\` blocks pass \`checks\` to \`write\_failed\_report\`, but the \`audit\` log accumulated in \`run\_stages\` is discarded with the staging folder instead of showing which pipeline stage failed. 

**Author's response (Hans writes)**

1. Thank you for pointing this out. I tested write_export() by attempting to export a CSV file into a nested directory that did not exist. The test produced an OSError because the parent directory was missing. After inspecting the implementation, I confirmed that write_export() does not independently create its parent directory. Although make_staging() creates the staging directory for normal pipeline execution, direct calls to write_export() with a nonexistent parent directory can still fail. I agree that the function should create its parent directory before writing. Confirmed issue; fix required. (Relevant commit: 704d243 — src/export.)
2. Thank you for identifying the missing audit information. I inspected run_pipeline() and confirmed that both exception handlers discard the staging directory and call write_failed_report() using only checks and the exception message. The accumulated audit entries from run_stages() are not saved when processing fails. I verified that the failure report contains the checks and stopping error but does not contain the stage-level audit information. I agree that preserving the audit log separately would improve debugging while still preventing partial outputs from being published. Confirmed issue; fix required. (Relevant commit: 26489c1 — src/pipeline.py.)


---

## **Summary table (the last person to edit fills in the response commits)**

| Review | Reviewer | Author | Reviewed commit | Code reviewed | Response commit |
| ----- | ----- | ----- | ----- | ----- | ----- |
| 1 | Kaycelyn | Gillian | `e8499d1` | readers.py, analysis.py | `b44ae1c`   |
| 2 | Giana | Kaycelyn | `a7eef66` | validation.py, parquet\_reader.py | `1401cb0`  |
| 3 | Hans | Giana | `aaddfe5` | reconcile.py, matrix.py | `a51accd`  |
| 4 | Gillian | Hans | `704d243, 26489c1`  | export.py, pipeline.py | ``  |

