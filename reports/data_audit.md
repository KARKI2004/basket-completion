# Online Retail original-data audit

**Descriptive audit only. The positive-purchase view and all cleaning suggestions are provisional.**

## Source and schema

- Original file: `data/raw/Online Retail.xlsx` (23,715,344 bytes); SHA-256 `43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d`. Hash before and after read matched.
- Sheets: Online Retail (541,910 rows including header × 8 columns).
- Columns: `InvoiceNo` invoice ID; `StockCode` product/service code; `Description` label; `Quantity` line quantity; `InvoiceDate` event time; `UnitPrice` line unit price; `CustomerID` optional customer ID; `Country` country. Invoice and stock IDs contain mixed numeric/text Excel values.

| Column | pandas dtype | Missing raw rows |
| --- | --- | ---: |
| InvoiceNo | `object` | 0 |
| StockCode | `object` | 0 |
| Description | `object` | 1,454 |
| Quantity | `int64` | 0 |
| InvoiceDate | `datetime64[us]` | 0 |
| UnitPrice | `float64` | 0 |
| CustomerID | `float64` | 135,080 |
| Country | `str` | 0 |

## Raw workbook totals

- **541,909 rows**, **25,900 distinct invoice IDs**, **4,070 stock codes**, and **4,372 identified customers**. These are different units.
- Date range: 2010-12-01 08:26:00 to 2011-12-09 12:50:00; exact duplicate source rows: 5,268.
- Cancellation-prefixed invoice IDs: 3,836; their rows: 9,288. Nonpositive-quantity rows: 10,624 across 5,172 invoices. Nonpositive-price rows: 2,517 across 2,157 invoices.

### Overlapping raw-row flags

| Flag | Rows |
| --- | ---: |
| cancellation prefix | 9,288 |
| nonpositive quantity | 10,624 |
| nonpositive price | 2,517 |
| missing description | 1,454 |
| union primary three | 11,805 |
| union all four | 11,805 |

Flags overlap: a cancellation row can also have nonpositive quantity; a missing-description row may also have zero price. The union, not the sum of flags, is the provisional removed-row count. All missing-description rows are already in the primary union here.

### Monthly distinct invoice IDs

Counted once in the month of each invoice's earliest line timestamp. This is an audit convention, not the approved chronological split rule.

| Month | Raw invoices | Provisional positive invoices |
| --- | ---: | ---: |
| 2010-12 | 2,025 | 1,559 |
| 2011-01 | 1,476 | 1,086 |
| 2011-02 | 1,393 | 1,100 |
| 2011-03 | 1,983 | 1,454 |
| 2011-04 | 1,744 | 1,246 |
| 2011-05 | 2,162 | 1,681 |
| 2011-06 | 2,012 | 1,533 |
| 2011-07 | 1,927 | 1,475 |
| 2011-08 | 1,737 | 1,361 |
| 2011-09 | 2,327 | 1,837 |
| 2011-10 | 2,637 | 2,040 |
| 2011-11 | 3,462 | 2,769 |
| 2011-12 | 1,015 | 819 |

## Provisional positive-purchase view

InvoiceNo does not begin C; Quantity > 0; UnitPrice > 0. No code, customer, or basket-size exclusions.

- **530,104 rows**, **19,960 invoices**, **3,922 stock codes**. No service-code, missing-customer, or basket-size exclusions have been applied.
- **519,602** distinct invoice–stock presences; 10,502 repeated lines do not add product presence. **1,641** single-product and **18,319** multi-product invoices.
- Basket size (distinct products): median 15; p90 52; p99 217.41; maximum 1,110.
- Missing CustomerID: 132,220 rows across 1,428 invoices. Baskets use InvoiceNo, so missing CustomerID does not merge or automatically invalidate them.

### Large baskets and pair opportunity

Possible unordered pairs = basket size × (basket size − 1) / 2; these are potential co-presences, not mined pair counts.
Total possible pairs: **28,531,398**.

| Minimum distinct products | Invoices | Product presences | Presence share | Possible pairs | Pair share |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 637 | 141,146 | 27.2% | 21,780,936 | 76.3% |
| 200 | 236 | 84,056 | 16.2% | 17,571,806 | 61.6% |

### Product frequency

Distinct baskets containing a stock code, not quantity or line count.

| Stock code | Baskets | Positive rows |
| --- | ---: | ---: |
| `85123A` | 2,198 | 2,265 |
| `85099B` | 2,089 | 2,112 |
| `22423` | 1,988 | 2,017 |
| `47566` | 1,685 | 1,706 |
| `20725` | 1,565 | 1,595 |
| `84879` | 1,455 | 1,489 |
| `22197` | 1,392 | 1,426 |
| `22720` | 1,385 | 1,399 |
| `21212` | 1,320 | 1,370 |
| `22383` | 1,284 | 1,326 |

## Codes, descriptions, and invoice anomalies

- Candidate non-merchandise: 2,300 rows in 2,265 invoices. These remain in the provisional view and need code-by-code review. Invoice counts per code may overlap.

| Code | Source description | Rows | Invoices |
| --- | --- | ---: | ---: |
| `AMAZONFEE` | AMAZON FEE | 2 | 2 |
| `B` | Adjust bad debt | 1 | 1 |
| `C2` | CARRIAGE | 141 | 141 |
| `DOT` | DOTCOM POSTAGE | 706 | 706 |
| `M` | Manual | 322 | 290 |
| `POST` | POSTAGE | 1,126 | 1,126 |
| `S` | SAMPLES | 2 | 2 |

- 220 stock codes have multiple exact descriptions; 110 uppercase-normalized code groups have case variants (for example `15056BL` and `15056bl`). 24 irregular-form codes appear on 2,762 positive rows. The compact [questionable-code review CSV](questionable_product_codes.csv) gives counts and leading source descriptions; it is not a removal list. Real letter-coded merchandise exists.
- Invoice ID forms: 22,061 numeric IDs, 3,836 `C`-prefixed numeric IDs, and 3 other IDs (A563185, A563186, A563187). The unusual `A` invoices are bad-debt adjustments; one positive-price row enters the provisional view until code exclusions are decided.
- Raw invoices: 43 with multiple timestamps (maximum span 1 minute; 0 cross dates), 0 with multiple known customer IDs, and 0 mixing missing and known customer IDs.
- Provisional invoices: 42 with multiple timestamps (maximum span 1 minute; 0 cross dates), 0 with multiple known customer IDs, and 0 mixing missing and known customer IDs.

## Feasibility and pending decisions

The 18,319 provisional multi-product invoices support an offline held-out-item comparison against popularity. No model quality or sales impact has been measured. These are gift-retail transactions, not restaurant-supply data.

Propose positive purchase-event filtering, explicit service/adjustment code exclusions, distinct invoice–stock presence, retention of missing-customer invoices, and training-only product display names. Alternatives: a labeled sensitivity view with candidate codes retained; exclusion of every multi-timestamp invoice versus an explicit earliest-time rule with boundary-crossers removed; and uncapped baskets versus predeclared size bounds with coverage and pair-impact reporting. All remain pending in `docs/DECISIONS.md` and require Gate B review.

Limitations: source descriptions can change; large baskets dominate possible pairs; a few invoices have timestamp anomalies; repeated customers may create dependent observations. The audit does not set split dates, tune a model, or create cleaned data.
