# Final test results — frozen Gate C configuration

One hidden product per eligible complete test invoice. The model and all training-derived artifacts remained fixed after validation. The source is gift-retail data; this offline recovery task does not measure sales impact.

- Popularity: **64/3,205 (2.00%)**.
- Association-only: **589/3,205 (18.38%)**.
- Association with labeled popularity fill: **589/3,205 (18.38%)**, **+16.38 percentage points** versus popularity.
- Paired 95% customer-cluster bootstrap interval for the combined-minus-popularity difference: **[+14.98, +17.85] percentage points**; 1,000 fixed-seed resamples. Missing IDs may conceal repeated customers.
- Training catalog contains **2,852/3,205 (89.0%)** hidden targets; **353** unseen targets remain misses in the main denominator.
- Known-target subset: popularity **64/2,852 (2.24%)**; association-only **589/2,852 (20.65%)**; combined **589/2,852 (20.65%)**.
- Association coverage: **3,148/3,205 (98.2%)**; full five association candidates: **3,147/3,205**.
- Any popularity fill: **58/3,205 (1.8%)**; full popularity fallback: **57/3,205 (1.8%)**; fewer than five final suggestions: **0/3,205**.

## Training-defined target groups

| Group | Test invoices | Popularity hits | Association-only hits | Combined hits |
| --- | ---: | ---: | ---: | ---: |
| head | 1,132 | 64 | 274 | 274 |
| middle | 1,083 | 0 | 238 | 238 |
| tail | 637 | 0 | 77 | 77 |
| unseen | 353 | 0 | 0 | 0 |

## Prespecified larger-basket sensitivity

Only the basket-size ceiling changes from <100 to <200. This adds eligible training baskets, so the sensitivity training catalog, popularity frequencies, and pair evidence are rebuilt from its own training split. The chronological boundaries, cleaning, holdout, candidate restrictions, scoring rule, and popularity-fill rule stay fixed. The selected configuration was not re-searched. Compare the common <100 test cohort to isolate the effect of the expanded training setup; report additional 100–199 baskets separately.

| Test cohort | Baskets | Primary popularity hits | Primary combined hits | Sensitivity popularity hits | Sensitivity combined hits |
| --- | ---: | ---: | ---: | ---: | ---: |
| Common <100 | 3,205 | 64 | 589 | 64 | 553 |
| Additional 100–199 | 64 | — | — | 1 | 4 |

Test results did not alter the frozen method. The sensitivity is a robustness check, not a post-test alternative for selection.
