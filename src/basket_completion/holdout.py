"""Fixed one-product holdout shared by all later recommendation methods."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable

SEED = "basket-completion-v1"


def hide_one(invoice: str, products: Iterable[str]) -> tuple[str, tuple[str, ...]]:
    ordered = tuple(sorted(set(products)))
    if len(ordered) < 2:
        raise ValueError("holdout requires at least two distinct products")
    digest = hashlib.sha256(f"{SEED}|{invoice}".encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big") % len(ordered)
    target = ordered[index]
    visible = ordered[:index] + ordered[index + 1 :]
    return target, visible
