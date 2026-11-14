"""Approved <200 basket sensitivity, with the primary-selected method fixed."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .association import Setting, build_training_pairs, pair_rows_for_visible, recommend_from_rows
from .holdout import hide_one
from .prepare import DB_PATH, ROOT, SQL_DIR

SENSITIVITY_DB = ROOT / "data/processed/basket_completion_200.sqlite"


def build_sensitivity_database(primary: Path = DB_PATH, output: Path = SENSITIVITY_DB) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".building.sqlite")
    try:
        if temporary.exists():
            temporary.unlink()
        with sqlite3.connect(f"file:{primary}?mode=ro", uri=True) as source, sqlite3.connect(temporary) as dest:
            source.backup(dest)
            dest.executescript((SQL_DIR / "sensitivity.sql").read_text(encoding="utf-8"))
            dest.executescript((SQL_DIR / "catalog.sql").read_text(encoding="utf-8"))
        pair_count = build_training_pairs(temporary)
        with sqlite3.connect(temporary) as conn:
            counts = dict(conn.execute("SELECT split,COUNT(*) FROM split_baskets GROUP BY split"))
            if counts != {"train": 11250, "validation": 3518, "test": 3269}:
                raise AssertionError(f"Sensitivity basket counts differ from approved estimates: {counts}")
            invalid = conn.execute("""SELECT COUNT(*) FROM train_catalog c WHERE NOT EXISTS
                (SELECT 1 FROM basket_items b WHERE b.split='train' AND b.product=c.product)""").fetchone()[0]
            if invalid:
                raise AssertionError("Sensitivity catalog contains a product outside training")
        os.replace(temporary, output)
        return {"splits": counts, "training_distinct_pairs": pair_count}
    finally:
        if temporary.exists():
            temporary.unlink()


def evaluate_sensitivity(database: Path, setting: Setting) -> dict:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
        popularity = dict(conn.execute("SELECT product,basket_count FROM train_popularity"))
        order = sorted(popularity, key=lambda product: (-popularity[product], product))
        results = {"common_under_100": {"invoices": 0, "baseline_hits": 0, "combined_hits": 0},
                   "additional_100_to_199": {"invoices": 0, "baseline_hits": 0, "combined_hits": 0}}
        invoices = conn.execute("SELECT invoice,basket_size FROM split_baskets WHERE split='validation' ORDER BY invoice").fetchall()
        for index, (invoice, size) in enumerate(invoices, 1):
            products = [row[0] for row in conn.execute("SELECT product FROM basket_items WHERE invoice=? ORDER BY product", (invoice,))]
            target, visible = hide_one(invoice, products)
            baseline = [product for product in order if product not in set(visible)][:5]
            rows = pair_rows_for_visible(conn, visible)
            combined = recommend_from_rows(rows, visible, popularity, setting).combined
            group = "common_under_100" if size < 100 else "additional_100_to_199"
            results[group]["invoices"] += 1
            results[group]["baseline_hits"] += target in baseline
            results[group]["combined_hits"] += target in {item.product for item in combined}
            if index % 500 == 0:
                print(f"sensitivity validated {index} baskets", flush=True)
        return results
