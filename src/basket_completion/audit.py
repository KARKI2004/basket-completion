"""Read-only, reproducible audit of the original Online Retail workbook.

The positive-purchase view is descriptive and does not enact a cleaning policy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/raw/Online Retail.xlsx"
REPORTS = ROOT / "reports"
CANDIDATE_SERVICE_CODES = {"POST", "DOT", "M", "C2", "AMAZONFEE", "S", "B"}
COLUMNS = ("InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def row_flags(frame: pd.DataFrame) -> pd.DataFrame:
    """Independent row flags; their counts overlap."""
    return pd.DataFrame({
        "cancellation_prefix": frame.InvoiceNo.astype(str).str.startswith("C"),
        "nonpositive_quantity": frame.Quantity.le(0),
        "nonpositive_price": frame.UnitPrice.le(0),
        "missing_description": frame.Description.isna(),
    }, index=frame.index)


def distinct_presence(frame: pd.DataFrame) -> pd.DataFrame:
    """One stock per invoice, regardless of repeated lines or quantity."""
    return frame[["invoice", "stock"]].drop_duplicates()


def possible_pairs(sizes: pd.Series) -> pd.Series:
    """Number of unordered product pairs contributed by each distinct-product basket."""
    return sizes * (sizes - 1) // 2


def monthly_invoice_counts(frame: pd.DataFrame) -> dict[str, int]:
    """Count each invoice once in the month of its earliest line timestamp."""
    first = frame.groupby("invoice").InvoiceDate.min()
    counts = first.dt.to_period("M").value_counts().sort_index()
    return {str(month): int(count) for month, count in counts.items()}


def invoice_anomalies(frame: pd.DataFrame) -> dict[str, int | float]:
    group = frame.groupby("invoice")
    time_n = group.InvoiceDate.nunique()
    customer_n = group.CustomerID.nunique(dropna=True)
    time_range = group.InvoiceDate.agg(["min", "max"])
    multi_time = time_n.gt(1)
    spans = (time_range.loc[multi_time, "max"] - time_range.loc[multi_time, "min"]).dt.total_seconds().div(60)
    return {
        "multiple_timestamps": int(multi_time.sum()),
        "multiple_known_customer_ids": int(customer_n.gt(1).sum()),
        "mixed_missing_and_known_customer_ids": int(group.CustomerID.apply(lambda x: x.isna().any() and x.notna().any()).sum()),
        "multi_timestamp_rows": int(frame.invoice.isin(time_n.index[multi_time]).sum()),
        "multi_timestamp_cross_calendar_date": int((time_range.loc[multi_time, "min"].dt.date != time_range.loc[multi_time, "max"].dt.date).sum()),
        "multi_timestamp_max_span_minutes": float(spans.max()) if len(spans) else 0.0,
    }


def questionable_codes(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate code-level review list; no invoice or customer records."""
    code = frame.stock
    code_upper = code.str.upper()
    irregular = ~code.str.fullmatch(r"\d+[A-Za-z]?")
    variants = frame.groupby("stock").Description.nunique(dropna=True)
    case_variants = frame.groupby(code_upper).stock.nunique().gt(1)
    mixed_descriptions = code.isin(variants.index[variants.gt(1)])
    mixed_case = code_upper.isin(case_variants.index[case_variants])
    service = code_upper.isin(CANDIDATE_SERVICE_CODES)
    subset = frame.loc[irregular | mixed_descriptions | mixed_case | service, ["invoice", "stock", "Description"]]
    rows = []
    for stock, part in subset.groupby("stock", sort=True):
        names = part.Description.value_counts().head(3)
        reasons = []
        if stock.upper() in CANDIDATE_SERVICE_CODES:
            reasons.append("candidate_non_merchandise")
        if not bool(pd.Series([stock]).str.fullmatch(r"\d+[A-Za-z]?").iloc[0]):
            reasons.append("unusual_identifier")
        if variants.loc[stock] > 1:
            reasons.append("multiple_descriptions")
        if case_variants.loc[stock.upper()]:
            reasons.append("case_variant")
        rows.append({
            "stock_code": stock,
            "review_reasons": ";".join(reasons),
            "positive_rows": len(part),
            "distinct_invoices": part.invoice.nunique(),
            "distinct_descriptions": int(variants.loc[stock]),
            "top_source_descriptions": " | ".join(f"{name} ({count})" for name, count in names.items()),
        })
    return pd.DataFrame(rows).sort_values(["positive_rows", "stock_code"], ascending=[False, True])


def calculate(source: Path = SOURCE) -> tuple[dict, pd.DataFrame]:
    before = sha256(source)
    workbook = load_workbook(source, read_only=True, data_only=True)
    sheets = [{"name": sheet.title, "rows_including_header": sheet.max_row, "columns": sheet.max_column} for sheet in workbook.worksheets]
    workbook.close()
    if len(sheets) != 1:
        raise ValueError("Expected exactly one source sheet")
    frame = pd.read_excel(source, sheet_name=sheets[0]["name"], engine="openpyxl")
    after = sha256(source)
    if before != after:
        raise RuntimeError("Original workbook changed during audit")
    if tuple(frame.columns) != COLUMNS:
        raise ValueError(f"Unexpected source columns: {list(frame.columns)}")
    frame["invoice"] = frame.InvoiceNo.astype(str)
    frame["stock"] = frame.StockCode.astype(str)
    flags = row_flags(frame)
    exclude = flags[["cancellation_prefix", "nonpositive_quantity", "nonpositive_price"]].any(axis=1)
    positive = frame.loc[~exclude].copy()
    presence = distinct_presence(positive)
    sizes = presence.groupby("invoice").size()
    pairs = possible_pairs(sizes)
    frequency = presence.groupby("stock").size().sort_values(ascending=False)
    service = positive.stock.str.upper().isin(CANDIDATE_SERVICE_CODES)
    descriptions = positive.groupby("stock").Description.nunique(dropna=True)
    case_variants = positive.groupby(positive.stock.str.upper()).stock.nunique().gt(1)
    invoice_numeric = frame.invoice.str.fullmatch(r"\d+")
    invoice_cancel = frame.invoice.str.fullmatch(r"C\d+")
    missing_customer_invoices = positive.groupby("invoice").CustomerID.apply(lambda x: x.isna().any())
    raw_customer_anomalies = invoice_anomalies(frame)
    positive_anomalies = invoice_anomalies(positive)
    questionable = questionable_codes(positive)

    def group_stats(view: pd.DataFrame) -> dict:
        return {
            "rows": len(view), "distinct_invoices": view.invoice.nunique(),
            "distinct_stock_codes": view.stock.nunique(),
            "distinct_known_customers": view.CustomerID.nunique(),
            "missing_values": {column: int(view[column].isna().sum()) for column in COLUMNS},
            "exact_duplicate_rows": int(view.duplicated(subset=list(COLUMNS)).sum()),
            "date_min": str(view.InvoiceDate.min()), "date_max": str(view.InvoiceDate.max()),
            "monthly_invoice_counts_earliest_timestamp": monthly_invoice_counts(view),
        }

    large = {}
    for threshold in (100, 200):
        selected = sizes.ge(threshold)
        large[str(threshold)] = {
            "invoices": int(selected.sum()),
            "distinct_product_presences": int(sizes.loc[selected].sum()),
            "presence_share": float(sizes.loc[selected].sum() / len(presence)),
            "possible_pairs": int(pairs.loc[selected].sum()),
            "possible_pair_share": float(pairs.loc[selected].sum() / pairs.sum()),
        }
    data = {
        "source": {"path": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
                   "bytes": source.stat().st_size, "sha256_before": before, "sha256_after": after,
                   "sheets": sheets, "columns": list(COLUMNS),
                   "pandas_dtypes": {c: str(frame[c].dtype) for c in COLUMNS},
                   "loaded_value_types": {c: {t.__name__: int(n) for t, n in frame[c].map(type).value_counts().items()} for c in ("InvoiceNo", "StockCode")}},
        "raw": group_stats(frame),
        "raw_flags": {**{key: int(flags[key].sum()) for key in flags},
                      "union_primary_three": int(exclude.sum()),
                      "union_all_four": int(flags.any(axis=1).sum()),
                      "cancellation_invoice_ids": int(frame.loc[flags.cancellation_prefix, "invoice"].nunique()),
                      "nonpositive_quantity_invoice_ids": int(frame.loc[flags.nonpositive_quantity, "invoice"].nunique()),
                      "nonpositive_price_invoice_ids": int(frame.loc[flags.nonpositive_price, "invoice"].nunique())},
        "raw_invoice_anomalies": raw_customer_anomalies,
        "raw_invoice_identifier_forms": {
            "numeric_rows": int(invoice_numeric.sum()),
            "numeric_invoice_ids": int(frame.loc[invoice_numeric, "invoice"].nunique()),
            "C_digits_rows": int(invoice_cancel.sum()),
            "C_digits_invoice_ids": int(frame.loc[invoice_cancel, "invoice"].nunique()),
            "other_rows": int((~invoice_numeric & ~invoice_cancel).sum()),
            "other_invoice_ids": int(frame.loc[~invoice_numeric & ~invoice_cancel, "invoice"].nunique()),
            "other_examples": sorted(frame.loc[~invoice_numeric & ~invoice_cancel, "invoice"].unique().tolist())[:5],
        },
        "provisional_positive_purchase": {
            "definition": "InvoiceNo does not begin C; Quantity > 0; UnitPrice > 0. No code, customer, or basket-size exclusions.",
            **group_stats(positive),
            "distinct_invoice_product_presences": len(presence),
            "repeated_lines_collapsed_for_presence": len(positive) - len(presence),
            "single_product_invoices": int(sizes.eq(1).sum()),
            "multi_product_invoices": int(sizes.ge(2).sum()),
            "basket_size_distinct_products": {"min": int(sizes.min()), "median": float(sizes.median()),
                                               "p90": float(sizes.quantile(.9)), "p99": float(sizes.quantile(.99)),
                                               "max": int(sizes.max())},
            "total_possible_unordered_product_pairs": int(pairs.sum()),
            "large_baskets_at_least": large,
            "top_product_frequency_distinct_baskets": [{"stock_code": str(code), "baskets": int(n),
                                                        "positive_rows": int(positive.stock.eq(code).sum())}
                                                       for code, n in frequency.head(10).items()],
            "missing_customer_rows": int(positive.CustomerID.isna().sum()),
            "invoices_with_missing_customer_id": int(missing_customer_invoices.sum()),
            "candidate_non_merchandise_rows": int(service.sum()),
            "candidate_non_merchandise_invoices": int(positive.loc[service, "invoice"].nunique()),
            "candidate_non_merchandise_by_code": [
                {"code": str(code), "rows": int(len(part)), "invoices": int(part.invoice.nunique()),
                 "description": str(part.Description.mode().iloc[0])}
                for code, part in positive.loc[service].assign(code=positive.loc[service, "stock"].str.upper()).groupby("code")],
            "stock_codes_with_multiple_descriptions": int(descriptions.gt(1).sum()),
            "uppercase_code_groups_with_case_variants": int(case_variants.sum()),
            "unusual_stock_identifier_rows": int((~positive.stock.str.fullmatch(r"\d+[A-Za-z]?")).sum()),
            "unusual_stock_identifier_codes": int(positive.loc[~positive.stock.str.fullmatch(r"\d+[A-Za-z]?"), "stock"].nunique()),
            "invoice_anomalies": positive_anomalies,
        },
        "notes": [
            "Counts of flags overlap; union_primary_three is the number of rows removed by the provisional filter.",
            "Invoice counts use distinct InvoiceNo, not rows or CustomerID.",
            "Basket size and product frequency use distinct invoice-product presence.",
            "Monthly invoice counts assign each invoice to its earliest observed timestamp for descriptive audit only; split policy remains pending.",
            "Possible pairs are n*(n-1)/2 per distinct-product invoice, not observed association counts.",
            "Questionable-code CSV is a code-level review list, not an exclusion list.",
        ],
    }
    if sum(data["raw"]["monthly_invoice_counts_earliest_timestamp"].values()) != data["raw"]["distinct_invoices"]:
        raise AssertionError("Raw monthly invoice counts do not reconcile")
    if sum(data["provisional_positive_purchase"]["monthly_invoice_counts_earliest_timestamp"].values()) != len(sizes):
        raise AssertionError("Provisional monthly invoice counts do not reconcile")
    return data, questionable


def markdown(data: dict) -> str:
    raw, p, source = data["raw"], data["provisional_positive_purchase"], data["source"]
    flags = data["raw_flags"]
    sheet_labels = ", ".join(
        f"{sheet['name']} ({sheet['rows_including_header']:,} rows including header × {sheet['columns']} columns)"
        for sheet in source["sheets"]
    )
    lines = ["# Online Retail original-data audit", "",
             "**Descriptive audit only. The positive-purchase view and all cleaning suggestions are provisional.**",
             "", "## Source and schema", "",
             f"- Original file: `{source['path']}` ({source['bytes']:,} bytes); SHA-256 `{source['sha256_before']}`. Hash before and after read matched.",
             f"- Sheets: {sheet_labels}.",
             "- Columns: `InvoiceNo` invoice ID; `StockCode` product/service code; `Description` label; `Quantity` line quantity; `InvoiceDate` event time; `UnitPrice` line unit price; `CustomerID` optional customer ID; `Country` country. Invoice and stock IDs contain mixed numeric/text Excel values.",
             "", "| Column | pandas dtype | Missing raw rows |", "| --- | --- | ---: |"]
    for c in source["columns"]:
        lines.append(f"| {c} | `{source['pandas_dtypes'][c]}` | {raw['missing_values'][c]:,} |")
    lines += ["", "## Raw workbook totals", "",
              f"- **{raw['rows']:,} rows**, **{raw['distinct_invoices']:,} distinct invoice IDs**, **{raw['distinct_stock_codes']:,} stock codes**, and **{raw['distinct_known_customers']:,} identified customers**. These are different units.",
              f"- Date range: {raw['date_min']} to {raw['date_max']}; exact duplicate source rows: {raw['exact_duplicate_rows']:,}.",
              f"- Cancellation-prefixed invoice IDs: {flags['cancellation_invoice_ids']:,}; their rows: {flags['cancellation_prefix']:,}. Nonpositive-quantity rows: {flags['nonpositive_quantity']:,} across {flags['nonpositive_quantity_invoice_ids']:,} invoices. Nonpositive-price rows: {flags['nonpositive_price']:,} across {flags['nonpositive_price_invoice_ids']:,} invoices.",
              "", "### Overlapping raw-row flags", "", "| Flag | Rows |", "| --- | ---: |"]
    for key in ("cancellation_prefix", "nonpositive_quantity", "nonpositive_price", "missing_description", "union_primary_three", "union_all_four"):
        lines.append(f"| {key.replace('_', ' ')} | {flags[key]:,} |")
    lines += ["", "Flags overlap: a cancellation row can also have nonpositive quantity; a missing-description row may also have zero price. The union, not the sum of flags, is the provisional removed-row count. All missing-description rows are already in the primary union here.",
              "", "### Monthly distinct invoice IDs", "", "Counted once in the month of each invoice's earliest line timestamp. This is an audit convention, not the approved chronological split rule.",
              "", "| Month | Raw invoices | Provisional positive invoices |", "| --- | ---: | ---: |"]
    for month in sorted(set(raw["monthly_invoice_counts_earliest_timestamp"]) | set(p["monthly_invoice_counts_earliest_timestamp"])):
        lines.append(f"| {month} | {raw['monthly_invoice_counts_earliest_timestamp'].get(month, 0):,} | {p['monthly_invoice_counts_earliest_timestamp'].get(month, 0):,} |")
    lines += ["", "## Provisional positive-purchase view", "", p["definition"], "",
              f"- **{p['rows']:,} rows**, **{p['distinct_invoices']:,} invoices**, **{p['distinct_stock_codes']:,} stock codes**. No service-code, missing-customer, or basket-size exclusions have been applied.",
              f"- **{p['distinct_invoice_product_presences']:,}** distinct invoice–stock presences; {p['repeated_lines_collapsed_for_presence']:,} repeated lines do not add product presence. **{p['single_product_invoices']:,}** single-product and **{p['multi_product_invoices']:,}** multi-product invoices.",
              f"- Basket size (distinct products): median {p['basket_size_distinct_products']['median']:.0f}; p90 {p['basket_size_distinct_products']['p90']:.0f}; p99 {p['basket_size_distinct_products']['p99']:.2f}; maximum {p['basket_size_distinct_products']['max']:,}.",
              f"- Missing CustomerID: {p['missing_customer_rows']:,} rows across {p['invoices_with_missing_customer_id']:,} invoices. Baskets use InvoiceNo, so missing CustomerID does not merge or automatically invalidate them.",
              "", "### Large baskets and pair opportunity", "", "Possible unordered pairs = basket size × (basket size − 1) / 2; these are potential co-presences, not mined pair counts.",
              f"Total possible pairs: **{p['total_possible_unordered_product_pairs']:,}**.", "", "| Minimum distinct products | Invoices | Product presences | Presence share | Possible pairs | Pair share |", "| ---: | ---: | ---: | ---: | ---: | ---: |"]
    for threshold, v in p["large_baskets_at_least"].items():
        lines.append(f"| {threshold} | {v['invoices']:,} | {v['distinct_product_presences']:,} | {v['presence_share']:.1%} | {v['possible_pairs']:,} | {v['possible_pair_share']:.1%} |")
    lines += ["", "### Product frequency", "", "Distinct baskets containing a stock code, not quantity or line count.", "", "| Stock code | Baskets | Positive rows |", "| --- | ---: | ---: |"]
    for item in p["top_product_frequency_distinct_baskets"]:
        lines.append(f"| `{item['stock_code']}` | {item['baskets']:,} | {item['positive_rows']:,} |")
    lines += ["", "## Codes, descriptions, and invoice anomalies", "",
              f"- Candidate non-merchandise: {p['candidate_non_merchandise_rows']:,} rows in {p['candidate_non_merchandise_invoices']:,} invoices. These remain in the provisional view and need code-by-code review. Invoice counts per code may overlap.",
              "", "| Code | Source description | Rows | Invoices |", "| --- | --- | ---: | ---: |"]
    for item in p["candidate_non_merchandise_by_code"]:
        lines.append(f"| `{item['code']}` | {item['description']} | {item['rows']:,} | {item['invoices']:,} |")
    id_forms = data["raw_invoice_identifier_forms"]
    lines += ["", f"- {p['stock_codes_with_multiple_descriptions']:,} stock codes have multiple exact descriptions; {p['uppercase_code_groups_with_case_variants']:,} uppercase-normalized code groups have case variants (for example `15056BL` and `15056bl`). {p['unusual_stock_identifier_codes']:,} irregular-form codes appear on {p['unusual_stock_identifier_rows']:,} positive rows. The compact [questionable-code review CSV](questionable_product_codes.csv) gives counts and leading source descriptions; it is not a removal list. Real letter-coded merchandise exists.",
              f"- Invoice ID forms: {id_forms['numeric_invoice_ids']:,} numeric IDs, {id_forms['C_digits_invoice_ids']:,} `C`-prefixed numeric IDs, and {id_forms['other_invoice_ids']:,} other IDs ({', '.join(id_forms['other_examples'])}). The unusual `A` invoices are bad-debt adjustments; one positive-price row enters the provisional view until code exclusions are decided."]
    for label, anomalies in (("Raw", data["raw_invoice_anomalies"]), ("Provisional", p["invoice_anomalies"])):
        span = anomalies['multi_timestamp_max_span_minutes']
        unit = "minute" if span == 1 else "minutes"
        lines.append(f"- {label} invoices: {anomalies['multiple_timestamps']:,} with multiple timestamps (maximum span {span:g} {unit}; {anomalies['multi_timestamp_cross_calendar_date']:,} cross dates), {anomalies['multiple_known_customer_ids']:,} with multiple known customer IDs, and {anomalies['mixed_missing_and_known_customer_ids']:,} mixing missing and known customer IDs.")
    lines += ["", "## Feasibility and pending decisions", "",
              f"The {p['multi_product_invoices']:,} provisional multi-product invoices support an offline held-out-item comparison against popularity. No model quality or sales impact has been measured. These are gift-retail transactions, not restaurant-supply data.",
              "", "Preparation uses positive purchase-event filtering, explicit service/adjustment code exclusions, distinct invoice–stock presence, retention of missing-customer invoices, and training-only product display names.",
              "", "Limitations: source descriptions can change; large baskets dominate possible pairs; a few invoices have timestamp anomalies; repeated customers may create dependent observations. The audit does not set split dates, tune a model, or create cleaned data.", ""]
    return "\n".join(lines)


def main() -> None:
    data, questionable = calculate()
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "data_audit.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPORTS / "data_audit.md").write_text(markdown(data), encoding="utf-8")
    questionable.to_csv(REPORTS / "questionable_product_codes.csv", index=False)
    print("Wrote reports/data_audit.json, reports/data_audit.md, reports/questionable_product_codes.csv")


if __name__ == "__main__":
    main()
