# Validation-only basket completion results

**Checkpoint C evidence.** All counts and scores below use validation invoices only. The final test period was not evaluated. The training-only pair table uses primary baskets with 2–99 distinct products; no pairs from larger excluded baskets were generated.

- Training baskets: 11,000; catalog products: 3,500; distinct unordered training pairs: 1,300,982.
- Validation invoices and common all-eligible denominator: **3,432**. One deterministic hidden product per invoice, shared by every method.
- Training-catalog target coverage: **3,106/3,432 (90.5%)**; unseen targets: **326**, retained as misses in the main denominator.
- Popularity hit rate@5: **77/3,432 (2.24%)**; known-target subset 77/3,106 (2.48%).

## Fixed validation search

Eight approved settings: minimum pair count {3, 10} × directional {confidence, lift} × multi-item {maximum, sum}. Pair support is count/N_train; confidence is count/frequency(visible product); lift is confidence divided by candidate frequency/N_train. Score each candidate from visible training products; exclude visible products; tie-break by training popularity then stock code. Association-only lists are measured separately from popularity-filled lists.

| Setting | Assoc-only hit@5 | Combined hit@5 | Δ vs popularity | Assoc coverage | Any fallback | Full fallback |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `count3_confidence_maximum` | 20.89% | 20.89% | +18.65 pp | 98.3% | 1.8% | 1.7% |
| `count3_confidence_sum` | 11.98% | 11.98% | +9.73 pp | 98.3% | 1.8% | 1.7% |
| `count3_lift_maximum` | 8.95% | 8.95% | +6.70 pp | 98.3% | 1.8% | 1.7% |
| `count3_lift_sum` | 10.69% | 10.69% | +8.45 pp | 98.3% | 1.8% | 1.7% |
| `count10_confidence_maximum` | 20.43% | 20.43% | +18.18 pp | 97.5% | 3.4% | 2.5% |
| `count10_confidence_sum` | 12.30% | 12.30% | +10.05 pp | 97.5% | 3.4% | 2.5% |
| `count10_lift_maximum` | 11.71% | 11.71% | +9.47 pp | 97.5% | 3.4% | 2.5% |
| `count10_lift_sum` | 13.49% | 13.49% | +11.25 pp | 97.5% | 3.4% | 2.5% |

Association coverage means at least one eligible evidence-backed candidate before fallback. Any fallback means at least one final suggestion is popularity-filled; full fallback means no eligible association candidate. See the JSON for exact numerators, full-five association coverage, and fewer-than-five cases.

## Training-defined target popularity

Catalog group sizes: head 350 products, middle 1,050, tail 2,100. Unseen targets are separate.

| Target group | Validation invoices | Popularity hit@5 | Best combined hit@5 |
| --- | ---: | ---: | ---: |
| head | 1,321 | 5.83% | 28.54% |
| middle | 1,137 | 0.00% | 22.34% |
| tail | 648 | 0.00% | 13.27% |
| unseen | 326 | 0.00% | 0.00% |

## Recommendation and limits

The approved tie-break selects `count3_confidence_maximum` among association settings: 717/3,432 combined hits (20.89%), +18.65 percentage points versus popularity. Its association-only list hits 717/3,432; coverage is 3,375/3,432; 61 invoices use at least one fallback and 57 use full fallback.
Paired 95% customer-cluster bootstrap interval for the combined-minus-popularity hit-rate difference: [+17.19, +20.20] percentage points (1,000 fixed-seed resamples). This interval reuses the validation data that selected the setting, so it is descriptive, not untouched confirmation. Missing customer IDs may conceal repeated customers.
**Proposed configuration, not yet frozen: count3_confidence_maximum.** This recommendation is based only on validation; Gate C acceptance is required before final test evaluation. A positive offline hit-rate difference would not establish sales impact or superiority to a deployed recommendation system.

### Approved large-basket sensitivity on validation

The <200 policy uses its own training aggregates and the primary-selected setting without a second search. The common group contains the same <100 validation invoices and hidden targets; the additional group contains only 100–199-product validation baskets.

| Validation group | Baskets | <100-train baseline hits | <100-train combined hits | <200-train baseline hits | <200-train combined hits |
| --- | ---: | ---: | ---: | ---: | ---: |
| Common <100 | 3,432 | 77 | 717 | 76 | 682 |
| Additional 100–199 | 86 | — | — | 2 | 8 |

Adding larger training baskets did not improve the selected setting on the common validation examples. The additional cohort is small and should not be compared as if it were the same evaluation set.

### First matching validation examples (no invoice or customer IDs)

Examples are the first in invoice sort order within each category, with at most two visible products shown. They illustrate individual outcomes and are **not representative performance evidence**; the denominators above carry that evidence. These source gift-retail products are not restaurant catalog examples. Each association suggestion in the machine-readable report carries its supporting visible product and pair statistics; fallback suggestions are labeled separately.

- **association success baseline miss:** visible excerpt PACK OF 12 LONDON TISSUES, LUNCH BOX I LOVE LONDON (basket has 5 visible products); hidden LONDON BUS COFFEE MUG; final suggestions: SET OF 60 PANTRY DESIGN CAKE CASES (association), SET 2 TEA TOWELS I LOVE LONDON (association), SET OF 60 VINTAGE LEAF CAKE CASES (association), SPACEBOY LUNCH BOX (association), LONDON BUS COFFEE MUG (association). Supporting pair: TOTE BAG I LOVE LONDON → target, 20 training baskets.
- **fallback used:** visible excerpt HANGING BAUBLE T-LIGHT HOLDER LARGE (basket has 1 visible products); hidden HANGING BAUBLE T-LIGHT HOLDER SMALL; final suggestions: REX CASH+CARRY JUMBO SHOPPER (association), WHITE HANGING HEART T-LIGHT HOLDER (popularity), REGENCY CAKESTAND 3 TIER (popularity), JUMBO BAG RED RETROSPOT (popularity), PARTY BUNTING (popularity).
- **baseline success combined miss:** visible excerpt EDWARDIAN PARASOL NATURAL, DOORMAT RED RETROSPOT (basket has 42 visible products); hidden PARTY BUNTING; final suggestions: JUMBO BAG RED RETROSPOT (association), FRENCH BLUE METAL DOOR SIGN 2 (association), TRAVEL CARD WALLET VINTAGE TICKET (association), LUNCH BAG SPACEBOY DESIGN (association), LUNCH BAG RED RETROSPOT (association).
- **both miss:** visible excerpt PINK POLKADOT BOWL (basket has 1 visible products); hidden PARTY CONES CANDY ASSORTED; final suggestions: BLUE POLKADOT BOWL (association), PINK POLKADOT CUP (association), RED RETROSPOT BOWL (association), BLUE POLKADOT CUP (association), PINK POLKADOT PLATE (association).

No final test-period recommendation results were calculated. The sensitivity used the primary-selected setting and did not affect the eight-setting selection.
