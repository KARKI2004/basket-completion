"""Read-only service for the frozen basket-completion demonstration."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import MutableMapping

from .association import AssociationResult, PairEvidence, Setting, pair_rows_for_visible, recommend_from_rows
from .final_test import FREEZE_PATH, METRICS_PATH
from .prepare import ROOT

FROZEN_SETTING = Setting(3, "confidence", "maximum")
DEPLOY_DB = ROOT / "data/deploy/training.sqlite"
REVIEWED_REPORT = ROOT / "reports/test_results.md"
REVIEWED_METRICS_SHA256 = "687678e420c00f4d4a0a6ddfd46b9b83d3fc6c07dd0031252a8325b00d0c2758"


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    training_baskets: int


@dataclass(frozen=True)
class DemoService:
    database: Path
    products: tuple[Product, ...]

    @classmethod
    def from_frozen(cls) -> "DemoService":
        """Read the compact, training-only deployment snapshot."""
        frozen = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
        if frozen["setting"] != FROZEN_SETTING.key:
            raise RuntimeError("Demo setting differs from the Gate C freeze")
        if not DEPLOY_DB.is_file():
            raise FileNotFoundError(
                f"Deployment artifact missing: {DEPLOY_DB}. "
                "Run `python -m basket_completion.export_demo` locally and commit data/deploy/training.sqlite."
            )
        manifest_path = DEPLOY_DB.parent / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Deployment manifest missing: {manifest_path}. Re-run the export and commit it.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest["setting"] != frozen["setting"] or
                manifest["source_database_sha256"] != frozen["sha256"]["data/processed/basket_completion.sqlite"] or
                hashlib.sha256(DEPLOY_DB.read_bytes()).hexdigest() != manifest["sha256"]):
            raise RuntimeError("Deployment artifact does not match the frozen training snapshot; re-run the export")
        with sqlite3.connect(f"file:{DEPLOY_DB}?mode=ro", uri=True) as conn:
            rows = conn.execute("""SELECT product,display_name,basket_count FROM train_catalog
                ORDER BY basket_count DESC,product ASC""").fetchall()
            if not rows or conn.execute("SELECT COUNT(*) FROM train_directional_stats").fetchone()[0] == 0:
                raise RuntimeError("Frozen training catalog or pair evidence is missing")
        return cls(DEPLOY_DB, tuple(Product(*row) for row in rows))

    @property
    def popularity(self) -> dict[str, int]:
        return {item.code: item.training_baskets for item in self.products}

    @property
    def names(self) -> dict[str, str]:
        return {item.code: item.name for item in self.products}

    def search(self, query: str, limit: int = 20) -> tuple[Product, ...]:
        if limit < 0:
            raise ValueError("limit must be nonnegative")
        needle = query.strip().casefold()
        return tuple(item for item in self.products
                     if not needle or needle in item.code.casefold() or needle in item.name.casefold())[:limit]

    def browse(self, query: str, page: int, page_size: int = 3) -> tuple[tuple[Product, ...], int, int]:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        matches = self.search(query, limit=len(self.products))
        total = len(matches)
        current = min(max(page, 0), (total - 1) // page_size if total else 0)
        return matches[current * page_size:(current + 1) * page_size], total, current

    def supporting_evidence(self, visible: tuple[str, ...], candidates: tuple[str, ...]) -> dict[str, tuple[PairEvidence, ...]]:
        """Return all qualifying training relationships for displayed candidates.

        This is explanatory data only. It does not change frozen ranking.
        """
        present = set(visible)
        wanted = set(candidates) - present
        with sqlite3.connect(f"file:{self.database}?mode=ro", uri=True) as conn:
            rows = pair_rows_for_visible(conn, tuple(sorted(present)))
        grouped: dict[str, list[PairEvidence]] = {code: [] for code in wanted}
        for row in rows:
            if row.antecedent in present and row.candidate in wanted:
                grouped[row.candidate].append(row)
        return {code: tuple(sorted(items, key=lambda row: (-row.confidence, -row.pair_count, row.antecedent)))
                for code, items in grouped.items()}

    def recommend(self, visible: tuple[str, ...], limit: int = 5) -> AssociationResult:
        """Use the exact accepted scorer; quantities do not enter this call."""
        unique_visible = tuple(sorted(set(visible)))
        with sqlite3.connect(f"file:{self.database}?mode=ro", uri=True) as conn:
            rows = pair_rows_for_visible(conn, unique_visible)
        return recommend_from_rows(rows, unique_visible, self.popularity, FROZEN_SETTING, limit)


def add_product(basket: MutableMapping[str, int], code: str, catalog: set[str]) -> str:
    if code not in catalog:
        return "unknown"
    if code in basket:
        return "duplicate"
    basket[code] = 1
    return "added"


def set_quantity(basket: MutableMapping[str, int], code: str, quantity: int) -> None:
    if code not in basket:
        raise KeyError(code)
    if not isinstance(quantity, int) or quantity < 1:
        raise ValueError("Quantity must be a positive integer")
    basket[code] = quantity


def remove_product(basket: MutableMapping[str, int], code: str) -> None:
    basket.pop(code, None)


def basket_from_url(value: str, catalog: set[str]) -> dict[str, int]:
    """Restore only known products with positive integer quantities."""
    try:
        saved = json.loads(value)
    except (TypeError, ValueError):
        return {}
    if not isinstance(saved, dict):
        return {}
    return {code: quantity for code, quantity in saved.items()
            if isinstance(code, str) and code in catalog
            and type(quantity) is int and 1 <= quantity <= 9999}


def basket_for_url(basket: MutableMapping[str, int]) -> str:
    return json.dumps(dict(sorted(basket.items())), separators=(",", ":"))


def load_saved_results() -> dict:
    """Read verified aggregate results for display; never score test baskets here."""
    if not REVIEWED_REPORT.is_file():
        raise FileNotFoundError(f"Reviewed report missing: {REVIEWED_REPORT}")
    if hashlib.sha256(METRICS_PATH.read_bytes()).hexdigest() != REVIEWED_METRICS_SHA256:
        raise RuntimeError("Saved test metrics differ from the reviewed run")
    frozen = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    if metrics["configuration"] != frozen["setting"]:
        raise RuntimeError("Saved test setting differs from the freeze")
    if metrics["freeze_sha256"] != hashlib.sha256(FREEZE_PATH.read_bytes()).hexdigest():
        raise RuntimeError("Saved test metrics refer to a different freeze")
    primary = metrics["primary"]
    n = primary["invoices"]
    if n <= 0 or primary["known_targets"] + primary["unseen_targets"] != n:
        raise RuntimeError("Saved test denominators do not reconcile")
    for key in ("baseline", "association_only", "combined"):
        if abs(primary[f"{key}_hit_rate_at_5"] - primary[f"{key}_hits"] / n) > 1e-12:
            raise RuntimeError(f"Saved {key} rate does not match its numerator")
    return metrics
