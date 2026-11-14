"""One fixed Gate C configuration on the untouched chronological test period."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from itertools import groupby
from pathlib import Path

from .association import Setting, pair_rows_for_visible, recommend_from_rows
from .holdout import SEED, hide_one
from .prepare import DB_PATH, ROOT
from .sensitivity import SENSITIVITY_DB
from .validation import paired_cluster_interval, rate

FREEZE_PATH = ROOT / "docs/frozen_config.json"
METRICS_PATH = ROOT / "reports/final_test_metrics.json"
REPORT_PATH = ROOT / "reports/final_test_results.md"
SETTING = Setting(3, "confidence", "maximum")


def verify_freeze() -> dict:
    frozen = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    assert frozen["setting"] == SETTING.key and frozen["holdout_seed"] == SEED
    for name, expected in frozen["sha256"].items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if actual != expected:
            raise AssertionError(f"Frozen file changed: {name}")
    return frozen


def evaluate(database: Path, group_by_size: bool = False) -> dict:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
        catalog = conn.execute("SELECT product,basket_count FROM train_catalog ORDER BY basket_count DESC,product").fetchall()
        popularity = dict(catalog)
        ordered = tuple(product for product, _ in catalog)
        head_end, middle_end = math.ceil(.1 * len(ordered)), math.ceil(.4 * len(ordered))
        groups = {product: "head" if i < head_end else "middle" if i < middle_end else "tail"
                  for i, product in enumerate(ordered)}
        results = {}
        query = """SELECT b.invoice,b.customer_id,b.basket_size,i.product
            FROM split_baskets b JOIN basket_items i USING(invoice)
            WHERE b.split='test' ORDER BY b.invoice,i.product"""
        for invoice, rows_iter in groupby(conn.execute(query), lambda row: row[0]):
            rows = list(rows_iter)
            customer, size = rows[0][1:3]
            target, visible = hide_one(invoice, (row[3] for row in rows))
            if target in visible or size != len(rows):
                raise AssertionError("Invalid test basket or holdout")
            cohort = ("under_100" if size < 100 else "100_to_199") if group_by_size else "all"
            item = results.setdefault(cohort, {"invoices": 0, "baseline_hits": 0,
                "association_only_hits": 0, "combined_hits": 0, "known_targets": 0,
                "known_target_baseline_hits": 0, "known_target_association_only_hits": 0,
                "known_target_combined_hits": 0,
                "association_coverage_invoices": 0, "full_five_association_invoices": 0,
                "any_fallback_invoices": 0, "full_fallback_invoices": 0,
                "fewer_than_five_invoices": 0, "groups": {g: {"invoices": 0, "baseline_hits": 0,
                    "association_only_hits": 0, "combined_hits": 0} for g in ("head", "middle", "tail", "unseen")},
                "paired_outcomes": []})
            present = set(visible)
            baseline = tuple(p for p in ordered if p not in present)[:5]
            suggestion = recommend_from_rows(pair_rows_for_visible(conn, visible), visible, popularity, SETTING)
            assoc = tuple(p.product for p in suggestion.association_only)
            combined = tuple(p.product for p in suggestion.combined)
            if len(set(combined)) != len(combined) or present.intersection(combined):
                raise AssertionError("Duplicate or visible test suggestion")
            bh, ah, ch = int(target in baseline), int(target in assoc), int(target in combined)
            group = groups.get(target, "unseen")
            item["invoices"] += 1
            item["baseline_hits"] += bh
            item["association_only_hits"] += ah
            item["combined_hits"] += ch
            item["known_targets"] += group != "unseen"
            if group != "unseen":
                item["known_target_baseline_hits"] += bh
                item["known_target_association_only_hits"] += ah
                item["known_target_combined_hits"] += ch
            item["association_coverage_invoices"] += suggestion.eligible_association_candidates > 0
            item["full_five_association_invoices"] += suggestion.eligible_association_candidates >= 5
            item["any_fallback_invoices"] += any(p.source == "popularity" for p in suggestion.combined)
            item["full_fallback_invoices"] += suggestion.eligible_association_candidates == 0
            item["fewer_than_five_invoices"] += len(combined) < 5
            for key, value in (("invoices", 1), ("baseline_hits", bh),
                               ("association_only_hits", ah), ("combined_hits", ch)):
                item["groups"][group][key] += value
            cluster = f"customer:{customer}" if customer is not None else f"invoice:{invoice}"
            item["paired_outcomes"].append((cluster, bh, ch))
        for item in results.values():
            n = item["invoices"]
            item["unseen_targets"] = n - item["known_targets"]
            item["catalog_coverage"] = rate(item["known_targets"], n)
            for method in ("baseline", "association_only", "combined"):
                item[f"known_target_{method}_hit_rate_at_5"] = rate(item[f"known_target_{method}_hits"], item["known_targets"])
            item["baseline_hit_rate_at_5"] = rate(item["baseline_hits"], n)
            item["association_only_hit_rate_at_5"] = rate(item["association_only_hits"], n)
            item["combined_hit_rate_at_5"] = rate(item["combined_hits"], n)
            item["difference_from_popularity"] = rate(item["combined_hits"]-item["baseline_hits"], n)
            item["association_coverage"] = rate(item["association_coverage_invoices"], n)
            item["any_fallback_rate"] = rate(item["any_fallback_invoices"], n)
            item["full_fallback_rate"] = rate(item["full_fallback_invoices"], n)
            item["paired_cluster_bootstrap_95pct_difference"] = paired_cluster_interval(item.pop("paired_outcomes"))
            assert sum(g["invoices"] for g in item["groups"].values()) == n
            assert item["groups"]["unseen"]["combined_hits"] == 0
        results["training_catalog_product_counts"] = {"head": head_end, "middle": middle_end-head_end,
                                                       "tail": len(ordered)-middle_end}
        return results


def markdown(metrics: dict) -> str:
    main = metrics["primary"]
    n = main["invoices"]
    low, high = main["paired_cluster_bootstrap_95pct_difference"]
    lines = ["# Final test results — frozen Gate C configuration", "",
        "One hidden product per eligible complete test invoice. The model and all training-derived artifacts remained fixed after validation. The source is gift-retail data; this offline recovery task does not measure sales impact.", "",
        f"- Popularity: **{main['baseline_hits']:,}/{n:,} ({main['baseline_hit_rate_at_5']:.2%})**.",
        f"- Association-only: **{main['association_only_hits']:,}/{n:,} ({main['association_only_hit_rate_at_5']:.2%})**.",
        f"- Association with labeled popularity fill: **{main['combined_hits']:,}/{n:,} ({main['combined_hit_rate_at_5']:.2%})**, **{100*main['difference_from_popularity']:+.2f} percentage points** versus popularity.",
        f"- Paired 95% customer-cluster bootstrap interval for the combined-minus-popularity difference: **[{100*low:+.2f}, {100*high:+.2f}] percentage points**; 1,000 fixed-seed resamples. Missing IDs may conceal repeated customers.",
        f"- Training catalog contains **{main['known_targets']:,}/{n:,} ({main['catalog_coverage']:.1%})** hidden targets; **{main['unseen_targets']:,}** unseen targets remain misses in the main denominator.",
        f"- Known-target subset: popularity **{main['known_target_baseline_hits']:,}/{main['known_targets']:,} ({main['known_target_baseline_hit_rate_at_5']:.2%})**; association-only **{main['known_target_association_only_hits']:,}/{main['known_targets']:,} ({main['known_target_association_only_hit_rate_at_5']:.2%})**; combined **{main['known_target_combined_hits']:,}/{main['known_targets']:,} ({main['known_target_combined_hit_rate_at_5']:.2%})**.",
        f"- Association coverage: **{main['association_coverage_invoices']:,}/{n:,} ({main['association_coverage']:.1%})**; full five association candidates: **{main['full_five_association_invoices']:,}/{n:,}**.",
        f"- Any popularity fill: **{main['any_fallback_invoices']:,}/{n:,} ({main['any_fallback_rate']:.1%})**; full popularity fallback: **{main['full_fallback_invoices']:,}/{n:,} ({main['full_fallback_rate']:.1%})**; fewer than five final suggestions: **{main['fewer_than_five_invoices']:,}/{n:,}**.",
        "", "## Training-defined target groups", "",
        "| Group | Test invoices | Popularity hits | Association-only hits | Combined hits |",
        "| --- | ---: | ---: | ---: | ---: |"]
    for name, group in main["groups"].items():
        lines.append(f"| {name} | {group['invoices']:,} | {group['baseline_hits']:,} | {group['association_only_hits']:,} | {group['combined_hits']:,} |")
    lines += ["", "## Prespecified larger-basket sensitivity", "",
        "Only the basket-size ceiling changes from <100 to <200. This adds eligible training baskets, so the sensitivity training catalog, popularity frequencies, and pair evidence are rebuilt from its own training split. The chronological boundaries, cleaning, holdout, candidate restrictions, scoring rule, and popularity-fill rule stay fixed. The selected configuration was not re-searched. Compare the common <100 test cohort to isolate the effect of the expanded training setup; report additional 100–199 baskets separately.", "",
        "| Test cohort | Baskets | Primary popularity hits | Primary combined hits | Sensitivity popularity hits | Sensitivity combined hits |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    common = metrics["sensitivity"]["under_100"]
    extra = metrics["sensitivity"]["100_to_199"]
    lines.append(f"| Common <100 | {common['invoices']:,} | {main['baseline_hits']:,} | {main['combined_hits']:,} | {common['baseline_hits']:,} | {common['combined_hits']:,} |")
    lines.append(f"| Additional 100–199 | {extra['invoices']:,} | — | — | {extra['baseline_hits']:,} | {extra['combined_hits']:,} |")
    lines += ["", "Test results did not alter the frozen method. The sensitivity is a robustness check, not a post-test alternative for selection.", ""]
    return "\n".join(lines)


def main() -> None:
    frozen = verify_freeze()
    primary_results = evaluate(DB_PATH)
    primary = primary_results["all"]
    sensitivity = evaluate(SENSITIVITY_DB, group_by_size=True)
    sensitivity_groups = sensitivity.pop("training_catalog_product_counts")
    if primary["invoices"] != 3205 or sensitivity["under_100"]["invoices"] != 3205 or sensitivity["100_to_199"]["invoices"] != 64:
        raise AssertionError("Test counts differ from approved preparation")
    metrics = {"configuration": SETTING.key, "freeze_manifest": str(FREEZE_PATH.relative_to(ROOT)),
               "freeze_sha256": hashlib.sha256(FREEZE_PATH.read_bytes()).hexdigest(),
               "source_sha256": frozen["sha256"]["data/raw/Online Retail.xlsx"],
               "training_catalog_product_counts": primary_results["training_catalog_product_counts"],
               "sensitivity_training_catalog_product_counts": sensitivity_groups,
               "primary": primary, "sensitivity": sensitivity}
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(markdown(metrics), encoding="utf-8")
    print(f"Wrote {METRICS_PATH} and {REPORT_PATH}")


if __name__ == "__main__":
    main()
