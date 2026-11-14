"""Training-pair association candidates with separately labeled popularity fallback."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .prepare import DB_PATH, SQL_DIR

Score = Literal["confidence", "lift"]
Aggregation = Literal["maximum", "sum"]


@dataclass(frozen=True)
class Setting:
    min_pair_count: int
    score: Score
    aggregation: Aggregation

    def __post_init__(self) -> None:
        if self.min_pair_count < 1 or self.score not in ("confidence", "lift") or self.aggregation not in ("maximum", "sum"):
            raise ValueError("Invalid association setting")

    @property
    def key(self) -> str:
        return f"count{self.min_pair_count}_{self.score}_{self.aggregation}"


SETTINGS = tuple(
    Setting(count, score, aggregation)
    for count in (3, 10)
    for score in ("confidence", "lift")
    for aggregation in ("maximum", "sum")
)


@dataclass(frozen=True)
class PairEvidence:
    antecedent: str
    candidate: str
    pair_count: int
    support: float
    confidence: float
    lift: float


@dataclass(frozen=True)
class Suggestion:
    product: str
    source: Literal["association", "popularity"]
    score: float | None = None
    evidence: PairEvidence | None = None


@dataclass(frozen=True)
class AssociationResult:
    association_only: tuple[Suggestion, ...]
    combined: tuple[Suggestion, ...]
    eligible_association_candidates: int


def build_training_pairs(database: Path = DB_PATH) -> int:
    with sqlite3.connect(database) as conn:
        conn.executescript((SQL_DIR / "pairs.sql").read_text(encoding="utf-8"))
        pair_count = conn.execute("SELECT COUNT(*) FROM train_pairs").fetchone()[0]
        invalid = conn.execute("""SELECT COUNT(*) FROM train_pairs p
            JOIN train_popularity a ON a.product=p.product_a
            JOIN train_popularity b ON b.product=p.product_b
            WHERE p.pair_count < 1 OR p.pair_count > a.basket_count OR p.pair_count > b.basket_count""").fetchone()[0]
        if invalid:
            raise AssertionError(f"Invalid training pair-count bounds: {invalid}")
    return int(pair_count)


def pair_rows_for_visible(conn: sqlite3.Connection, visible: tuple[str, ...]) -> tuple[PairEvidence, ...]:
    if not visible:
        return ()
    placeholders = ",".join("?" for _ in visible)
    rows = conn.execute(
        f"""SELECT antecedent,candidate,pair_count,support,confidence,lift
            FROM train_directional_stats WHERE antecedent IN ({placeholders}) AND pair_count >= 3
            ORDER BY antecedent, candidate""",
        visible,
    )
    return tuple(PairEvidence(*row) for row in rows)


def recommend_from_rows(
    rows: tuple[PairEvidence, ...], visible: tuple[str, ...],
    popularity: dict[str, int], setting: Setting, limit: int = 5,
) -> AssociationResult:
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    present = set(visible)
    scores: dict[str, list[float]] = {}
    evidence: dict[str, PairEvidence] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for row in rows:
        pair_key = (row.antecedent, row.candidate)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        if row.pair_count < setting.min_pair_count or row.antecedent not in present:
            continue
        if row.candidate in present or row.candidate not in popularity:
            continue
        value = getattr(row, setting.score)
        scores.setdefault(row.candidate, []).append(value)
        previous = evidence.get(row.candidate)
        if previous is None or value > getattr(previous, setting.score) or (
            value == getattr(previous, setting.score)
            and (row.pair_count > previous.pair_count or (
                row.pair_count == previous.pair_count and row.antecedent < previous.antecedent
            ))
        ):
            evidence[row.candidate] = row
    aggregated = {
        product: max(values) if setting.aggregation == "maximum" else sum(values)
        for product, values in scores.items()
    }
    ranked = sorted(aggregated, key=lambda product: (-aggregated[product], -popularity[product], product))
    association_only = tuple(
        Suggestion(product, "association", aggregated[product], evidence[product])
        for product in ranked[:limit]
    )
    combined = list(association_only)
    selected = {item.product for item in combined} | present
    if len(combined) < limit:
        for product in sorted(popularity, key=lambda item: (-popularity[item], item)):
            if product not in selected:
                combined.append(Suggestion(product, "popularity"))
                selected.add(product)
                if len(combined) == limit:
                    break
    return AssociationResult(association_only, tuple(combined), len(ranked))


def recommend_all_settings(
    rows: tuple[PairEvidence, ...], visible: tuple[str, ...],
    popularity: dict[str, int], limit: int = 5,
) -> dict[Setting, AssociationResult]:
    """Score the fixed eight settings in one pass over pair evidence."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    present = set(visible)
    # For each threshold and metric: candidate -> [sum, maximum, best evidence].
    buckets: dict[tuple[int, str], dict[str, list]] = {
        (count, metric): {} for count in (3, 10) for metric in ("confidence", "lift")
    }
    seen_pairs: set[tuple[str, str]] = set()
    for row in rows:
        pair_key = (row.antecedent, row.candidate)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        if row.antecedent not in present or row.candidate in present or row.candidate not in popularity:
            continue
        for count in (3, 10):
            if row.pair_count < count:
                continue
            for metric in ("confidence", "lift"):
                value = getattr(row, metric)
                state = buckets[(count, metric)].get(row.candidate)
                if state is None:
                    buckets[(count, metric)][row.candidate] = [value, value, row]
                else:
                    state[0] += value
                    best = state[2]
                    if value > state[1] or (value == state[1] and (
                        row.pair_count > best.pair_count or (
                            row.pair_count == best.pair_count and row.antecedent < best.antecedent
                        )
                    )):
                        state[1], state[2] = value, row
    popular_order = sorted(popularity, key=lambda product: (-popularity[product], product))
    results = {}
    for setting in SETTINGS:
        bucket = buckets[(setting.min_pair_count, setting.score)]
        offset = 1 if setting.aggregation == "maximum" else 0
        ranked = sorted(bucket, key=lambda product: (-bucket[product][offset], -popularity[product], product))
        association_only = tuple(
            Suggestion(product, "association", bucket[product][offset], bucket[product][2])
            for product in ranked[:limit]
        )
        combined = list(association_only)
        selected = present | {item.product for item in association_only}
        if len(combined) < limit:
            for product in popular_order:
                if product not in selected:
                    combined.append(Suggestion(product, "popularity"))
                    selected.add(product)
                    if len(combined) == limit:
                        break
        results[setting] = AssociationResult(association_only, tuple(combined), len(ranked))
    return results
