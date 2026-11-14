"""Deterministic training-basket popularity recommendations."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable


def recommend_popular(conn: sqlite3.Connection, visible: Iterable[str], limit: int = 5) -> list[str]:
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    if limit == 0:
        return []
    present = set(visible)
    ordered = conn.execute(
        "SELECT product FROM train_popularity ORDER BY basket_count DESC, product ASC"
    )
    result = []
    for (product,) in ordered:
        if product not in present:
            result.append(product)
            if len(result) >= limit:
                break
    return result
