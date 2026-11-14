"""Build approved binary baskets and training-only popularity artifacts in SQLite."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

from .audit import COLUMNS, ROOT, SOURCE, sha256

DB_PATH = ROOT / "data/processed/basket_completion.sqlite"
SUMMARY_PATH = ROOT / "reports/preparation_summary.json"
SQL_DIR = ROOT / "sql"


def _source_frame(source: Path) -> pd.DataFrame:
    raw = pd.read_excel(source, engine="openpyxl")
    if tuple(raw.columns) != COLUMNS:
        raise ValueError(f"Unexpected source columns: {list(raw.columns)}")
    if raw[["InvoiceNo", "StockCode", "InvoiceDate"]].isna().any().any():
        raise ValueError("Required source identifiers or timestamps are missing")
    known_customers = raw.CustomerID.dropna()
    if not known_customers.mod(1).eq(0).all():
        raise ValueError("CustomerID contains a nonintegral value")
    return pd.DataFrame({
        "invoice": raw.InvoiceNo.astype(str),
        "stock": raw.StockCode.astype(str),
        "description": raw.Description.map(lambda value: None if pd.isna(value) else " ".join(str(value).split())),
        "quantity": raw.Quantity,
        "unit_price": raw.UnitPrice,
        "invoice_date": raw.InvoiceDate.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "customer_id": raw.CustomerID.map(lambda value: None if pd.isna(value) else str(int(value))),
    })


def _one(conn: sqlite3.Connection, query: str) -> int:
    return int(conn.execute(query).fetchone()[0])


def summary(conn: sqlite3.Connection, source_hash: str) -> dict:
    splits = {}
    for split in ("train", "validation", "test"):
        splits[split] = {
            "baskets": _one(conn, "SELECT COUNT(*) FROM split_baskets WHERE split = '" + split + "'"),
            "product_presences": _one(conn, "SELECT COUNT(*) FROM basket_items WHERE split = '" + split + "'"),
        }
    large_by_split = {}
    for split, lower, upper in (
        ("train", "2010-12-01 00:00:00", "2011-09-01 00:00:00"),
        ("validation", "2011-09-01 00:00:00", "2011-11-01 00:00:00"),
        ("test", "2011-11-01 00:00:00", "2011-12-10 00:00:00"),
    ):
        row = conn.execute("""SELECT COUNT(*), COALESCE(SUM(b.basket_size), 0),
                   COALESCE(SUM(b.basket_size * (b.basket_size - 1) / 2), 0)
            FROM basket_sizes b JOIN invoice_times t USING (invoice)
            WHERE b.basket_size >= 100 AND t.first_time >= ? AND t.last_time < ?""",
            (lower, upper),
        ).fetchone()
        large_by_split[split] = {
            "invoices": int(row[0]), "product_presences": int(row[1]),
            "possible_pairs": int(row[2]),
        }
    return {
        "source_sha256": source_hash,
        "raw_rows": _one(conn, "SELECT COUNT(*) FROM source_lines"),
        "raw_invoices": _one(conn, "SELECT COUNT(DISTINCT invoice) FROM source_lines"),
        "positive_rows": _one(conn, "SELECT COUNT(*) FROM positive_lines"),
        "positive_invoices": _one(conn, "SELECT COUNT(DISTINCT invoice) FROM positive_lines"),
        "excluded_nonmerchandise_rows": _one(conn, "SELECT COUNT(*) FROM positive_lines") - _one(conn, "SELECT COUNT(*) FROM merchandise_lines"),
        "merchandise_rows": _one(conn, "SELECT COUNT(*) FROM merchandise_lines"),
        "merchandise_invoices": _one(conn, "SELECT COUNT(DISTINCT invoice) FROM merchandise_lines"),
        "distinct_invoice_product_presences": _one(conn, "SELECT COUNT(*) FROM invoice_products"),
        "single_product_invoices": _one(conn, "SELECT COUNT(*) FROM basket_sizes WHERE basket_size = 1"),
        "multi_product_invoices": _one(conn, "SELECT COUNT(*) FROM basket_sizes WHERE basket_size >= 2"),
        "multi_product_presences": _one(conn, "SELECT COALESCE(SUM(basket_size), 0) FROM basket_sizes WHERE basket_size >= 2"),
        "multi_product_unique_products": _one(conn, "SELECT COUNT(DISTINCT p.product) FROM invoice_products p JOIN basket_sizes b USING (invoice) WHERE b.basket_size >= 2"),
        "multi_product_possible_pairs": _one(conn, "SELECT COALESCE(SUM(basket_size * (basket_size - 1) / 2), 0) FROM basket_sizes WHERE basket_size >= 2"),
        "excluded_at_least_100_products": _one(conn, "SELECT COUNT(*) FROM basket_sizes WHERE basket_size >= 100"),
        "excluded_large_baskets_by_split": large_by_split,
        "split_boundary_crossers": _one(conn, """SELECT COUNT(*) FROM invoice_times t JOIN basket_sizes b USING (invoice)
            WHERE b.basket_size >= 2 AND b.basket_size < 100 AND (
            (t.first_time < '2011-09-01 00:00:00' AND t.last_time >= '2011-09-01 00:00:00') OR
            (t.first_time < '2011-11-01 00:00:00' AND t.last_time >= '2011-11-01 00:00:00'))"""),
        "splits": splits,
        "primary_product_presences": _one(conn, "SELECT COUNT(*) FROM basket_items"),
        "primary_unique_products": _one(conn, "SELECT COUNT(DISTINCT product) FROM basket_items"),
        "primary_possible_pairs": _one(conn, "SELECT COALESCE(SUM(basket_size * (basket_size - 1) / 2), 0) FROM split_baskets"),
        "training_catalog_products": _one(conn, "SELECT COUNT(*) FROM train_catalog"),
        "training_popularity_total_basket_votes": _one(conn, "SELECT COALESCE(SUM(basket_count), 0) FROM train_popularity"),
    }


def build_database(source: Path, database: Path) -> dict:
    before = sha256(source)
    frame = _source_frame(source)
    after = sha256(source)
    if before != after:
        raise RuntimeError("Source workbook changed during read")
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()
    with sqlite3.connect(database) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("""CREATE TABLE source_lines (
            invoice TEXT NOT NULL, stock TEXT NOT NULL, description TEXT,
            quantity INTEGER NOT NULL, unit_price REAL NOT NULL,
            invoice_date TEXT NOT NULL, customer_id TEXT)""")
        frame.to_sql("source_lines", conn, if_exists="append", index=False, chunksize=10_000)
        conn.execute("CREATE INDEX source_invoice ON source_lines(invoice)")
        conn.executescript((SQL_DIR / "prepare.sql").read_text(encoding="utf-8"))
        conn.executescript((SQL_DIR / "catalog.sql").read_text(encoding="utf-8"))
        result = summary(conn, before)
        if result["training_popularity_total_basket_votes"] != result["splits"]["train"]["product_presences"]:
            raise AssertionError("Training popularity includes non-training or duplicate presence")
        if sum(x["baskets"] for x in result["splits"].values()) != _one(conn, "SELECT COUNT(*) FROM split_baskets"):
            raise AssertionError("Split baskets do not reconcile")
        if sum(x["product_presences"] for x in result["splits"].values()) != result["primary_product_presences"]:
            raise AssertionError("Split product presences do not reconcile")
        if result["multi_product_invoices"] != sum(x["baskets"] for x in result["splits"].values()) + result["excluded_at_least_100_products"] + result["split_boundary_crossers"]:
            raise AssertionError("Basket exclusions do not reconcile")
        if _one(conn, "SELECT COUNT(*) FROM train_catalog c WHERE NOT EXISTS (SELECT 1 FROM basket_items b WHERE b.split='train' AND b.product=c.product)"):
            raise AssertionError("Training catalog contains a product outside training")
        if _one(conn, "SELECT COUNT(*) FROM train_name_votes v WHERE NOT EXISTS (SELECT 1 FROM split_baskets b WHERE b.invoice=v.invoice AND b.split='train')"):
            raise AssertionError("Display names contain an invoice outside training")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AssertionError("SQLite integrity check failed")
    if sha256(source) != before:
        raise RuntimeError("Source workbook changed during build")
    return result


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = DB_PATH.with_suffix(".building.sqlite")
    try:
        result = build_database(SOURCE, temporary)
        audit = json.loads((ROOT / "reports/data_audit.json").read_text(encoding="utf-8"))
        if result["source_sha256"] != audit["source"]["sha256_before"]:
            raise RuntimeError("Source hash differs from reviewed audit")
        os.replace(temporary, DB_PATH)
        SUMMARY_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
