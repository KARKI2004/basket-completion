# Cleaning and evaluation specification — approved at Gate B

**Status: approved by the owner at Checkpoint B (2026-10-31).** This is the fixed policy for preparation and subsequent validation; later gates still control association selection and test evaluation. The accepted setup choices are recorded in [DECISIONS.md](DECISIONS.md). Counts below are read-only policy estimates from the local workbook with SHA-256 `43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d`; they are **not** recommendation results. Source audit: [data_audit.md](../reports/data_audit.md).

## 1. Purchase and product rules

- Model positive purchase **events**, rather than net retained purchases. Keep a line only when `InvoiceNo` does not start `C`, `Quantity > 0`, and `UnitPrice > 0`. Exclude cancellations, returns, and nonpositive-price lines from the primary view. The raw flags overlap; use their union, not the sum, to explain removed rows. The audit's first-stage view has 530,104 rows and 19,960 invoice IDs.
- Then remove only the following listed stock codes, matching case-insensitively, from **product** lines. The reasons and effects are from the provisional positive-purchase audit; per-code invoice counts overlap:

  | Code | Reason from source description | Positive rows | Invoice IDs containing code |
  | --- | --- | ---: | ---: |
  | `POST` | POSTAGE | 1,126 | 1,126 |
  | `DOT` | DOTCOM POSTAGE | 706 | 706 |
  | `C2` | CARRIAGE | 141 | 141 |
  | `M` / `m` | Manual entry, not an identified product | 322 | 290 |
  | `AMAZONFEE` | AMAZON FEE | 2 | 2 |
  | `S` | SAMPLES | 2 | 2 |
  | `B` | Adjust bad debt | 1 | 1 |

  The **2,300 unique rows** occur in **2,265 distinct invoice IDs**; removing them leaves **527,804 rows** and **19,784 invoices with at least one product**, 176 fewer than the first-stage view. Multi-product invoices fall from 18,319 to 18,273; some others become single-product. This also removes the positive-price `A563185` bad-debt line. Do **not** exclude every nonnumeric stock code: some are real merchandise. `M` is the most debatable code because “Manual” could conceal a sale; retaining it in a labeled alternative would preserve 322 lines but would treat an unidentified item as merchandise.
- Keep invoice IDs as the basket key. Missing `CustomerID` is allowed, and missing IDs are never grouped into one customer. The audit found no invoice with two known customer IDs. Keep `Country` as source metadata, not a product identity key. An invoice needs at least two eligible **distinct** products to support one hidden target and a visible basket. After the proposed service-code removal, 1,511 invoices contain one product and 18,273 contain at least two.
- Collapse all eligible lines for the same `(InvoiceNo, canonical stock code)` to one product presence. This also neutralizes exact duplicate rows and repeated invoice-product lines; do not use quantity for the first model. Preserve the original workbook unchanged and report line and invoice attrition at each stage.

### Product identity and descriptions

Do not uppercase every stock code. The audit found 110 case-variant groups; code case and description alone are insufficient for a blanket merge. Apply only the following predeclared, auditable mappings, then deduplicate presence. Both pairs differ only by letter case, have the same description in the **training period**, and have no training invoice containing both forms:

| Source form → canonical code | Source evidence | Caveat |
| --- | --- | --- |
| `47566b` → `47566B` | 90 vs 329 training-period positive rows; both “TEA TIME PARTY BUNTING” | Different price ranges may reflect sales channels; identity is inferred from code and name. |
| `15056n` → `15056N` | 67 vs 343 training-period positive rows; both “EDWARDIAN PARASOL NATURAL” | Same caveat. |

All other case variants stay separate unless documented evidence supports another mapping. For example, `85123a` and `85123A` have a shared dominant name, but some uppercase rows say “CREAM HANGING HEART T-LIGHT HOLDER”; do not infer distinct products solely from that description difference or merge them without review. Fix the two proposed mappings **before** any validation search; never choose mappings based on recommendation performance. Their identity evidence is from the proposed training period only; catalog frequencies and display names also come from training only. A strict alternative is no mappings, avoiding this judgment but fragmenting two likely identical products.

For each canonical training product, trim and collapse whitespace in nonempty descriptions. Within each training invoice/product, choose the lexicographically first normalized description if multiple occur; then select the name used by the most distinct training invoices, breaking ties lexicographically. If none exists, display its code. Do not derive names or resolve conflicts from validation/test. A name change does not automatically imply a new product.

### Invoice timestamps

Use the earliest source-line `InvoiceDate` of a retained invoice as its single timestamp; keep all its eligible products together. Check the minimum and maximum times across **all source lines of that invoice**, including lines later excluded as non-merchandise. If they fall on opposite sides of a split boundary, exclude the entire invoice from all splits and report it. The raw audit found 43 multi-timestamp invoices (42 in the first-stage positive view); each spans one minute, none crosses a calendar date, and the proposed boundaries below have **zero** crossing invoices in the read-only count. A stricter alternative is to remove every multi-timestamp retained invoice; that loses otherwise usable baskets without resolving a known boundary crossing. Do not split invoice lines by timestamp.

## 2. Large-basket policy and coverage

The audit found 637 provisional invoices with at least 100 distinct products, contributing 76.3% of all possible unordered product pairs. An invoice with 1,110 products alone permits over 615,000 pairs. Do not silently sample pairs, since that changes pair evidence in a hard-to-explain way.

**The primary eligibility range is `2 ≤ distinct products < 100`**, applied to training, validation, and test invoices after product exclusions and the two mappings. This keeps almost all multi-product invoices while preventing very large orders from dominating pair statistics. Run **one prespecified sensitivity policy `2 ≤ distinct products < 200`** with its own training aggregates and the **same configuration selected on primary validation**; do not run a second configuration search. Compare results on the common `<100` validation/test invoices to isolate the training effect, and report the additional 100–199-product cohort separately. The uncapped row is coverage context, not a third planned model search. The sensitivity still omits ≥200-product baskets, so it cannot settle the effect of the most extreme orders.

Read-only estimated coverage after proposed code removal and two mappings, relative to all 18,273 multi-product invoices / 515,823 product presences / 3,906 distinct products / 28,373,891 possible pairs:

| Policy | Invoices | Invoice coverage | Product presences | Presence coverage | Distinct products | Product coverage | Possible pairs | Pair coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Primary, 2–99 | 17,637 | 96.5% | 375,220 | 72.7% | 3,763 | 96.3% | 6,713,631 | 23.7% |
| Sensitivity, 2–199 | 18,037 | 98.7% | 431,993 | 83.7% | 3,821 | 97.8% | 10,883,601 | 38.4% |
| Uncapped, ≥2 | 18,273 | 100.0% | 515,823 | 100.0% | 3,906 | 100.0% | 28,373,891 | 100.0% |

The cap excludes some products that occur only in large baskets. Report actual coverage again after implementation, along with excluded invoice and presence counts by split. These estimates must not be treated as approved cleaned-data totals.

## 3. Chronological train / validation / test plan

Use naive source timestamps consistently. Boundaries were chosen from monthly invoice coverage and to reserve two later periods, **without looking at recommendation performance**:

| Split | Timestamp interval | Expected primary baskets (2–99) | Expected sensitivity baskets (2–199) | Uncapped multi-product context |
| --- | --- | ---: | ---: | ---: |
| Train | `2010-12-01 00:00:00 ≤ t < 2011-09-01 00:00:00` | 11,000 | 11,250 | 11,376 |
| Validation | `2011-09-01 00:00:00 ≤ t < 2011-11-01 00:00:00` | 3,432 | 3,518 | 3,572 |
| Test | `2011-11-01 00:00:00 ≤ t < 2011-12-10 00:00:00` | 3,205 | 3,269 | 3,325 |
| Total | Complete observed period | **17,637** | **18,037** | **18,273** |

Train spans nine months; validation spans September–October 2011; test spans November and the first nine days of December. The test is partly holiday-season data and the final December is incomplete, so distribution shift may influence results. Do not tune the method or rules on test results. If a source discrepancy changes the estimated counts, reconcile and explain it before modeling; do not alter dates based on performance.

## 4. Training artifacts and one-item evaluation

- Derive the candidate catalog, product display names, basket-popularity counts, product-frequency groups, and pair counts **only from primary-eligible training invoices**. Each invoice contributes at most one presence per canonical product. Never use validation or test to refit these artifacts in this study.
- On every eligible validation/test invoice, sort canonical product codes lexicographically. Compute SHA-256 of UTF-8 text `basket-completion-v1|<InvoiceNo>`; interpret the first eight digest bytes as an unsigned big-endian integer and take modulo basket size. Hide the product at that zero-based position. Use the identical hidden target and remaining visible products for every method; fix the seed before validation. The choice is deterministic and independent of method scores.
- The common candidate universe for popularity and association methods is **training catalog minus every visible basket product**. Never recommend an existing visible product. A visible product absent from the training catalog remains in the input and is ignored only as an association seed. Rank up to five eligible candidates with deterministic stock-code tie breaks. If fewer than five exist, return fewer and report that case.
- Keep a later invoice whose hidden target is absent from the training catalog in the **main all-eligible denominator**. It is necessarily a miss for both methods. Also report a known-target subset (target in training catalog) with its own numerator and denominator. Do not silently drop unseen targets or change the candidate universe for one method.
- Define training popularity groups by ranking training catalog products by descending training-basket frequency, then code ascending. For catalog size `K`, head is ranks `1..ceil(0.10K)`, middle is the following ranks through `ceil(0.40K)`, and tail is the rest. Assign validation/test targets using **training** ranks only; unseen is its own group. Report group product counts, evaluation invoice counts, and hit rate@5 by group. This rank rule avoids ambiguous frequency ties.

## 5. Metrics, limited validation search, and uncertainty

- **Hit rate@5:** eligible invoices with the hidden product among up to five suggestions divided by all eligible invoices, one target each. Report popularity baseline, association-only list, and association-plus-popularity-fallback separately. For the known-target subset, use that subset's count as denominator.
- **Association coverage:** eligible invoices with at least one association candidate after evidence and candidate restrictions, divided by all eligible invoices. Report the number with a full five association candidates too.
- **Fallback use:** fraction of eligible invoices whose final list actually contains at least one popularity-filled suggestion; separately report full fallback (zero association candidates before filling). After ranking association candidates, append highest-ranked eligible popularity products not already selected until the list reaches five or the candidate universe is exhausted. Label each filled suggestion. A list with fewer than five available catalog candidates is reported separately.
- **Catalog coverage:** fraction of eligible hidden targets present in the training catalog; report known and unseen counts. This is target coverage, not fraction of catalog items ever recommended.
- Report all denominators, exclusion counts, fewer-than-five cases, and the training-defined target popularity groups on validation and test. Consider a table by basket size and known customer status as descriptive diagnostics, without tuning on test.

Fix the popularity baseline once: descending count of training baskets containing each product, with code ascending for ties. For associations, compute training pair counts, confidence `count(a,b)/count(a)`, and lift `confidence/(count(b)/N_train)`. Search only **eight** prespecified validation configurations: minimum pair count `{3, 10}` × pair score `{confidence, lift}` × multi-visible-item aggregation `{maximum, sum}`. Score candidates from visible items only; order them by aggregated score descending, training-basket popularity descending, then code ascending. Select by all-eligible validation hit rate@5 of the combined system; break ties by higher association coverage, then prefer confidence, minimum count 10, and maximum aggregation in that order. Fill remaining slots from fixed popularity. Freeze one configuration before opening test results. This approved grid has no result yet.

For the final paired hit-rate difference, use 1,000 fixed-seed bootstrap resamples of evaluation **customer clusters**: all invoices sharing a known CustomerID form one cluster; each missing-ID invoice is its own cluster. Resample clusters with replacement, recompute the paired difference, and report a 95% percentile interval. Keep training artifacts fixed. Missing IDs may hide repeat customers, so the interval still may understate dependence; report the point estimate and this limitation. Do not use interval outcomes to retune after test inspection.

## Checkpoint B approval record

The owner approved all four recommendations from the critical review: purchase and product exclusions, the two explicit case mappings, basket-size and chronological policies, and the evaluation contract. The two case mappings and the all-source-line split-boundary check are explicit above. No policy choice is based on recommendation results.

Checkpoint B is closed. Phase 4 may implement preparation and the popularity baseline. Association selection, real test evaluation, and UI remain for later phases and gates.
