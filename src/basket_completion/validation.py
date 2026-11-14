"""Validation-only comparison of the fixed eight association settings and popularity."""
from __future__ import annotations

import json
import math
import random
import sqlite3
from collections import defaultdict
from itertools import groupby
from pathlib import Path

from .association import SETTINGS, Setting, build_training_pairs, pair_rows_for_visible, recommend_all_settings
from .holdout import hide_one
from .prepare import DB_PATH, ROOT

METRICS_PATH = ROOT / "reports/validation_metrics.json"
REPORT_PATH = ROOT / "reports/validation_results.md"


def rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def paired_cluster_interval(outcomes: list[tuple[str, int, int]], repeats: int = 1000) -> tuple[float, float]:
    """Resample known customers together; each missing-customer invoice is a singleton."""
    clusters: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for cluster, baseline_hit, combined_hit in outcomes:
        clusters[cluster][0] += combined_hit - baseline_hit
        clusters[cluster][1] += 1
    keys = sorted(clusters)
    rng = random.Random(20261031)
    differences = []
    for _ in range(repeats):
        sample = rng.choices(keys, k=len(keys))
        numerator = sum(clusters[key][0] for key in sample)
        denominator = sum(clusters[key][1] for key in sample)
        differences.append(numerator / denominator)
    return percentile(differences, .025), percentile(differences, .975)


def _suggestion_dict(item, names: dict[str, str]) -> dict:
    result = {"product": item.product, "display_name": names.get(item.product, item.product), "source": item.source}
    if item.evidence is not None:
        result["evidence"] = {
            "visible_product": item.evidence.antecedent,
            "visible_display_name": names.get(item.evidence.antecedent, item.evidence.antecedent),
            "pair_count": item.evidence.pair_count,
            "support": item.evidence.support,
            "confidence": item.evidence.confidence,
            "lift": item.evidence.lift,
        }
    return result


def _example(target, visible, baseline, result, names) -> dict:
    return {
        "visible_product_count": len(visible),
        "visible_excerpt": [{"product": code, "display_name": names.get(code, code)} for code in visible[:2]],
        "hidden_target": {"product": target, "display_name": names.get(target, target)},
        "baseline_top_five": list(baseline),
        "association_top_five": [_suggestion_dict(item, names) for item in result.association_only],
        "combined_top_five": [_suggestion_dict(item, names) for item in result.combined],
    }


def evaluate_validation(database: Path = DB_PATH) -> dict:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
        catalog_rows = conn.execute(
            "SELECT product,display_name,basket_count FROM train_catalog ORDER BY basket_count DESC,product ASC"
        ).fetchall()
        popularity = {product: count for product, _, count in catalog_rows}
        names = {product: name for product, name, _ in catalog_rows}
        pop_order = tuple(popularity)
        catalog_size = len(pop_order)
        head_end = math.ceil(.10 * catalog_size)
        middle_end = math.ceil(.40 * catalog_size)
        groups = {
            product: ("head" if i < head_end else "middle" if i < middle_end else "tail")
            for i, product in enumerate(pop_order)
        }
        group_product_counts = {"head": head_end, "middle": middle_end - head_end,
                                "tail": catalog_size - middle_end, "unseen": 0}
        aggregate = {setting: {
            "combined_hits": 0, "association_only_hits": 0,
            "covered_invoices": 0, "full_five_association_invoices": 0,
            "any_fallback_invoices": 0, "full_fallback_invoices": 0,
            "known_target_combined_hits": 0, "fewer_than_five_invoices": 0,
            "group_hits": {group: 0 for group in group_product_counts},
            "examples": {}, "paired_outcomes": [],
        } for setting in SETTINGS}
        group_invoices = {group: 0 for group in group_product_counts}
        group_baseline_hits = {group: 0 for group in group_product_counts}
        total = baseline_hits = known_targets = known_baseline_hits = 0
        cursor = conn.execute("""SELECT b.invoice,b.customer_id,i.product
            FROM split_baskets b JOIN basket_items i USING(invoice)
            WHERE b.split='validation' ORDER BY b.invoice,i.product""")
        for invoice, items in groupby(cursor, key=lambda row: row[0]):
            rows = list(items)
            customer_id = rows[0][1]
            products = [row[2] for row in rows]
            target, visible = hide_one(invoice, products)
            if target in visible:
                raise AssertionError("Hidden target leaked into visible basket")
            present = set(visible)
            baseline = tuple(product for product in pop_order if product not in present)[:5]
            base_hit = int(target in baseline)
            group = groups.get(target, "unseen")
            known = group != "unseen"
            total += 1
            baseline_hits += base_hit
            known_targets += known
            known_baseline_hits += base_hit if known else 0
            group_invoices[group] += 1
            group_baseline_hits[group] += base_hit
            pair_rows = pair_rows_for_visible(conn, visible)
            outputs = recommend_all_settings(pair_rows, visible, popularity)
            for setting, result in outputs.items():
                stats = aggregate[setting]
                combined_codes = tuple(item.product for item in result.combined)
                association_codes = tuple(item.product for item in result.association_only)
                if len(set(combined_codes)) != len(combined_codes) or present.intersection(combined_codes):
                    raise AssertionError("Duplicate or already-visible recommendation")
                combined_hit = int(target in combined_codes)
                association_hit = int(target in association_codes)
                stats["combined_hits"] += combined_hit
                stats["association_only_hits"] += association_hit
                stats["covered_invoices"] += result.eligible_association_candidates > 0
                stats["full_five_association_invoices"] += result.eligible_association_candidates >= 5
                stats["any_fallback_invoices"] += any(item.source == "popularity" for item in result.combined)
                stats["full_fallback_invoices"] += result.eligible_association_candidates == 0
                stats["known_target_combined_hits"] += combined_hit if known else 0
                stats["fewer_than_five_invoices"] += len(combined_codes) < 5
                stats["group_hits"][group] += combined_hit
                cluster = f"customer:{customer_id}" if customer_id is not None else f"invoice:{invoice}"
                stats["paired_outcomes"].append((cluster, base_hit, combined_hit))
                examples = stats["examples"]
                category = (
                    "association_success_baseline_miss" if association_hit and not base_hit else
                    "baseline_success_combined_miss" if base_hit and not combined_hit else
                    "fallback_success" if combined_hit and not association_hit and not base_hit else
                    "both_miss" if not base_hit and not combined_hit else None
                )
                if category and category not in examples:
                    examples[category] = _example(target, visible, baseline, result, names)
                if "fallback_used" not in examples and any(item.source == "popularity" for item in result.combined):
                    examples["fallback_used"] = _example(target, visible, baseline, result, names)
            if total % 500 == 0:
                print(f"validated {total} baskets", flush=True)
        expected = conn.execute("SELECT COUNT(*) FROM split_baskets WHERE split='validation'").fetchone()[0]
        if total != expected:
            raise AssertionError(f"Validation denominator {total} != {expected}")
        if group_invoices["unseen"] + sum(group_invoices[g] for g in ("head", "middle", "tail")) != total:
            raise AssertionError("Popularity group denominators do not reconcile")
        settings_metrics = []
        for setting in SETTINGS:
            stats = aggregate[setting]
            lower, upper = paired_cluster_interval(stats["paired_outcomes"])
            settings_metrics.append({
                "key": setting.key,
                "min_pair_count": setting.min_pair_count,
                "score": setting.score,
                "aggregation": setting.aggregation,
                "denominator": total,
                "combined_hits": stats["combined_hits"],
                "combined_hit_rate_at_5": rate(stats["combined_hits"], total),
                "difference_from_popularity": rate(stats["combined_hits"] - baseline_hits, total),
                "association_only_hits": stats["association_only_hits"],
                "association_only_hit_rate_at_5": rate(stats["association_only_hits"], total),
                "association_coverage_invoices": stats["covered_invoices"],
                "association_coverage": rate(stats["covered_invoices"], total),
                "full_five_association_invoices": stats["full_five_association_invoices"],
                "any_fallback_invoices": stats["any_fallback_invoices"],
                "any_fallback_rate": rate(stats["any_fallback_invoices"], total),
                "full_fallback_invoices": stats["full_fallback_invoices"],
                "full_fallback_rate": rate(stats["full_fallback_invoices"], total),
                "fewer_than_five_invoices": stats["fewer_than_five_invoices"],
                "known_target_combined_hits": stats["known_target_combined_hits"],
                "known_target_combined_hit_rate_at_5": rate(stats["known_target_combined_hits"], known_targets),
                "paired_cluster_bootstrap_95pct_difference": [lower, upper],
                "by_target_group": {
                    group: {"invoices": group_invoices[group], "combined_hits": stats["group_hits"][group],
                            "combined_hit_rate_at_5": rate(stats["group_hits"][group], group_invoices[group])}
                    for group in group_invoices
                },
                "examples": stats["examples"],
            })
        chosen = max(settings_metrics, key=lambda m: (
            m["combined_hits"], m["association_coverage_invoices"],
            int(m["score"] == "confidence"), int(m["min_pair_count"] == 10),
            int(m["aggregation"] == "maximum"),
        ))
        return {
            "scope": "validation_only",
            "training_baskets": conn.execute("SELECT COUNT(*) FROM split_baskets WHERE split='train'").fetchone()[0],
            "training_distinct_pairs": conn.execute("SELECT COUNT(*) FROM train_pairs").fetchone()[0],
            "training_catalog_products": catalog_size,
            "training_popularity_group_product_counts": group_product_counts,
            "validation_invoices": total,
            "baseline_hits": baseline_hits,
            "baseline_hit_rate_at_5": rate(baseline_hits, total),
            "known_targets": known_targets,
            "unseen_targets": total - known_targets,
            "catalog_coverage": rate(known_targets, total),
            "known_target_baseline_hits": known_baseline_hits,
            "known_target_baseline_hit_rate_at_5": rate(known_baseline_hits, known_targets),
            "validation_target_groups": {
                group: {"invoices": group_invoices[group], "baseline_hits": group_baseline_hits[group],
                        "baseline_hit_rate_at_5": rate(group_baseline_hits[group], group_invoices[group])}
                for group in group_invoices
            },
            "settings": settings_metrics,
            "best_association_setting_by_approved_tie_break": chosen["key"],
        }


def markdown(metrics: dict) -> str:
    n = metrics["validation_invoices"]
    best = next(m for m in metrics["settings"] if m["key"] == metrics["best_association_setting_by_approved_tie_break"])
    recommendation = "popularity alone" if best["combined_hits"] <= metrics["baseline_hits"] else best["key"]
    lines = ["# Validation-only basket completion results", "",
             "**Checkpoint C evidence.** All counts and scores below use validation invoices only. The final test period was not evaluated. The training-only pair table uses primary baskets with 2–99 distinct products; no pairs from larger excluded baskets were generated.", "",
             f"- Training baskets: {metrics['training_baskets']:,}; catalog products: {metrics['training_catalog_products']:,}; distinct unordered training pairs: {metrics['training_distinct_pairs']:,}.",
             f"- Validation invoices and common all-eligible denominator: **{n:,}**. One deterministic hidden product per invoice, shared by every method.",
             f"- Training-catalog target coverage: **{metrics['known_targets']:,}/{n:,} ({metrics['catalog_coverage']:.1%})**; unseen targets: **{metrics['unseen_targets']:,}**, retained as misses in the main denominator.",
             f"- Popularity hit rate@5: **{metrics['baseline_hits']:,}/{n:,} ({metrics['baseline_hit_rate_at_5']:.2%})**; known-target subset {metrics['known_target_baseline_hits']:,}/{metrics['known_targets']:,} ({metrics['known_target_baseline_hit_rate_at_5']:.2%}).",
             "", "## Fixed validation search", "",
             "Eight approved settings: minimum pair count {3, 10} × directional {confidence, lift} × multi-item {maximum, sum}. Pair support is count/N_train; confidence is count/frequency(visible product); lift is confidence divided by candidate frequency/N_train. Score each candidate from visible training products; exclude visible products; tie-break by training popularity then stock code. Association-only lists are measured separately from popularity-filled lists.", "",
             "| Setting | Assoc-only hit@5 | Combined hit@5 | Δ vs popularity | Assoc coverage | Any fallback | Full fallback |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for m in metrics["settings"]:
        lines.append(f"| `{m['key']}` | {m['association_only_hit_rate_at_5']:.2%} | {m['combined_hit_rate_at_5']:.2%} | {100*m['difference_from_popularity']:+.2f} pp | {m['association_coverage']:.1%} | {m['any_fallback_rate']:.1%} | {m['full_fallback_rate']:.1%} |")
    lines += ["", "Association coverage means at least one eligible evidence-backed candidate before fallback. Any fallback means at least one final suggestion is popularity-filled; full fallback means no eligible association candidate. See the JSON for exact numerators, full-five association coverage, and fewer-than-five cases.",
              "", "## Training-defined target popularity", "",
              f"Catalog group sizes: head {metrics['training_popularity_group_product_counts']['head']:,} products, middle {metrics['training_popularity_group_product_counts']['middle']:,}, tail {metrics['training_popularity_group_product_counts']['tail']:,}. Unseen targets are separate.",
              "", "| Target group | Validation invoices | Popularity hit@5 | Best combined hit@5 |", "| --- | ---: | ---: | ---: |"]
    for group in ("head", "middle", "tail", "unseen"):
        b = metrics["validation_target_groups"][group]
        c = best["by_target_group"][group]
        lines.append(f"| {group} | {b['invoices']:,} | {b['baseline_hit_rate_at_5']:.2%} | {c['combined_hit_rate_at_5']:.2%} |")
    low, high = best["paired_cluster_bootstrap_95pct_difference"]
    lines += ["", "## Recommendation and limits", "",
              f"The approved tie-break selects `{best['key']}` among association settings: {best['combined_hits']:,}/{n:,} combined hits ({best['combined_hit_rate_at_5']:.2%}), {100*best['difference_from_popularity']:+.2f} percentage points versus popularity. Its association-only list hits {best['association_only_hits']:,}/{n:,}; coverage is {best['association_coverage_invoices']:,}/{n:,}; {best['any_fallback_invoices']:,} invoices use at least one fallback and {best['full_fallback_invoices']:,} use full fallback.",
              f"Paired 95% customer-cluster bootstrap interval for the combined-minus-popularity hit-rate difference: [{100*low:+.2f}, {100*high:+.2f}] percentage points (1,000 fixed-seed resamples). This interval reuses the validation data that selected the setting, so it is descriptive, not untouched confirmation. Missing customer IDs may conceal repeated customers.",
              f"**Proposed configuration, not yet frozen: {recommendation}.** This recommendation is based only on validation; Gate C acceptance is required before final test evaluation. A positive offline hit-rate difference would not establish sales impact or superiority to a deployed recommendation system.",
              "", "### Approved large-basket sensitivity on validation", "",
              "The <200 policy uses its own training aggregates and the primary-selected setting without a second search. The common group contains the same <100 validation invoices and hidden targets; the additional group contains only 100–199-product validation baskets.",
              "", "| Validation group | Baskets | <100-train baseline hits | <100-train combined hits | <200-train baseline hits | <200-train combined hits |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    sensitivity = metrics["sensitivity"]
    common = sensitivity["validation"]["common_under_100"]
    additional = sensitivity["validation"]["additional_100_to_199"]
    lines.append(f"| Common <100 | {common['invoices']:,} | {metrics['baseline_hits']:,} | {best['combined_hits']:,} | {common['baseline_hits']:,} | {common['combined_hits']:,} |")
    lines.append(f"| Additional 100–199 | {additional['invoices']:,} | — | — | {additional['baseline_hits']:,} | {additional['combined_hits']:,} |")
    lines += ["", "Adding larger training baskets did not improve the selected setting on the common validation examples. The additional cohort is small and should not be compared as if it were the same evaluation set.",
              "", "### First matching validation examples (no invoice or customer IDs)", "",
              "Examples are the first in invoice sort order within each category, with at most two visible products shown. They illustrate individual outcomes and are **not representative performance evidence**; the denominators above carry that evidence. These source gift-retail products are not restaurant catalog examples. Each association suggestion in the machine-readable report carries its supporting visible product and pair statistics; fallback suggestions are labeled separately.", ""]
    examples = best["examples"]
    for category in ("association_success_baseline_miss", "fallback_used", "fallback_success", "baseline_success_combined_miss", "both_miss"):
        example = examples.get(category)
        if example is None:
            continue
        visible = ", ".join(item["display_name"] for item in example["visible_excerpt"])
        combined = ", ".join(f"{item['display_name']} ({item['source']})" for item in example["combined_top_five"])
        evidence = next((item["evidence"] for item in example["combined_top_five"] if item["product"] == example["hidden_target"]["product"] and item["source"] == "association"), None)
        support = f" Supporting pair: {evidence['visible_display_name']} → target, {evidence['pair_count']} training baskets." if evidence else ""
        lines.append(f"- **{category.replace('_', ' ')}:** visible excerpt {visible} (basket has {example['visible_product_count']} visible products); hidden {example['hidden_target']['display_name']}; final suggestions: {combined}.{support}")
    lines += ["", "No final test-period recommendation results were calculated. The sensitivity used the primary-selected setting and did not affect the eight-setting selection.", ""]
    return "\n".join(lines)


def main() -> None:
    build_training_pairs()
    metrics = evaluate_validation()
    from .sensitivity import SENSITIVITY_DB, build_sensitivity_database, evaluate_sensitivity

    setting = next(item for item in SETTINGS if item.key == metrics["best_association_setting_by_approved_tie_break"])
    sensitivity_build = build_sensitivity_database()
    metrics["sensitivity"] = {
        "setting": setting.key,
        "training_baskets": sensitivity_build["splits"]["train"],
        "training_distinct_pairs": sensitivity_build["training_distinct_pairs"],
        "validation": evaluate_sensitivity(SENSITIVITY_DB, setting),
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(markdown(metrics), encoding="utf-8")
    print(f"Wrote {METRICS_PATH} and {REPORT_PATH}")
    print("baseline", metrics["baseline_hit_rate_at_5"], "best", metrics["best_association_setting_by_approved_tie_break"])


if __name__ == "__main__":
    main()
