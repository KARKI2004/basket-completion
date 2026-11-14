# Decisions

## Accepted setup choices

- Use a `src/` Python package with `pyproject.toml` and a local `.venv`.
- Use Python 3.11 for this local setup, pandas and openpyxl as core dependencies, pytest and ruff as development extras, and built-in `sqlite3`.
- Ignore original and generated datasets and local databases. Keep selected aggregate reports and figures eligible for Git.

The cleaning and evaluation policy was approved at Checkpoint B. Gate C method selection is accepted and frozen. The first final test run has been inspected; Checkpoint D conclusions are reviewed in [test_results.md](../reports/test_results.md).

## Approved Checkpoint B policy

The owner approved the four material recommendations on 2026-10-31. [EVALUATION_SPEC.md](EVALUATION_SPEC.md) is the governing detail. The bullets below summarize accepted rules; alternatives remain documented in that specification but are not active policy.

- Primary purchase-event filter: exclude cancellation-prefixed invoices, nonpositive quantity, and nonpositive unit price. Report each flag and their overlap.
- Exclude explicitly identified non-merchandise codes (`POST`, `DOT`, `M`/`m`, `C2`, `AMAZONFEE`, `S`, `B`) from the product catalog. Retain letter-coded merchandise.
- Form baskets from distinct invoice–stock presence, preserving invoices with missing CustomerID. Use training-derived names for display.
- Do not automatically uppercase stock codes. Apply only two explicit mappings (`47566b` → `47566B`; `15056n` → `15056N`); keep all other case variants separate.
- Remove the `B` bad-debt adjustment code, including the positive-price `A`-prefixed adjustment line.
- Use the earliest source-line timestamp for a retained invoice and exclude that entire invoice if any of its source-line times straddle an approved boundary. Keep invoices intact.
- Primary eligibility is 2–99 distinct products, with a 2–199 sensitivity policy using the primary-selected configuration and uncapped coverage context.
- The chronological boundaries, deterministic hidden-item rule, common candidate universe, unseen-target denominators, training-defined popularity groups, eight-setting validation budget, and paired uncertainty approach in [EVALUATION_SPEC.md](EVALUATION_SPEC.md) are approved. This line records the Gate B policy as accepted before model selection; Gate C was subsequently accepted below.

## Gate C method — accepted and frozen before final test

The owner accepted `count3_confidence_maximum` on 2026-10-31 for final test evaluation: minimum 3 distinct training-basket co-occurrences, directional confidence `P(candidate | visible product) = count(candidate, visible) / count(visible)`, maximum qualifying confidence across visible products, existing deterministic ties, and labeled popularity fill. Both counts in confidence use eligible **training baskets** with distinct invoice-product presence; a visible product contributes once per basket. The primary basket rule remains 2–99 products; the 2–199-product sensitivity is a robustness check only. The exact pre-test files, artifacts, seed, setting, and validation result are hashed in [frozen_config.json](frozen_config.json). No validation or test baskets are used to refit training artifacts.

**Search history:** [validation_metrics.json](../reports/validation_metrics.json) contains exactly the approved eight combinations: minimum count `{3, 10}` × score `{confidence, lift}` × aggregation `{maximum, sum}`. The validation comparison was rerun after a deterministic SQL evidence-order fix; its machine-readable metrics stayed byte-identical. The larger-basket sensitivity used only the primary-selected setting and was not a second search. There was **no search-budget deviation** and no additional settings were tried. The chosen combined validation result was 717/3,432, versus 77/3,432 for popularity. Gate C was closed before the first final test evaluation. No post-test retuning is permitted.

## Checkpoint D review — existing test results

The first frozen test evaluation was run after the Gate C freeze and has been inspected. Its generated report, [final_test_results.md](../reports/final_test_results.md), and JSON metrics are preserved. The authoritative post-evaluation interpretation is [test_results.md](../reports/test_results.md). The prior session record supports the acceptance → freeze → first test scoring order; current hashes verify the frozen source, prepared data and model files are unchanged. Most files are uncommitted, so Git alone cannot prove the chronological order independently. The post-inspection work added figures and documentation, with no change to the method, prepared baskets, training artifacts, candidates or holdouts. The accepted <200 sensitivity remains a robustness check, not a post-test model choice.

Gate D review is complete with no new cleaning or method decision. The next permitted phase is the separately requested UI; do not refit or tune the frozen study in that phase.
