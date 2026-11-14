"""Render the three Checkpoint D figures from saved final-test metrics only.

Run with a Python environment containing matplotlib:
    MPLBACKEND=Agg MPLCONFIGDIR=/tmp/basket-mpl python3 reports/figures/build_final_charts.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
METRICS = ROOT / "reports/final_test_metrics.json"
COLORS = {"popularity": "#718096", "association": "#2b6cb0", "combined": "#187a61",
          "mixed": "#d69e2e", "fallback": "#c05640", "unseen": "#cbd5e0"}


def main() -> None:
    data = json.loads(METRICS.read_text(encoding="utf-8"))
    result = data["primary"]
    n = result["invoices"]
    assert n > 0 and result["known_targets"] + result["unseen_targets"] == n
    assert sum(g["invoices"] for g in result["groups"].values()) == n
    assert result["association_coverage_invoices"] + result["full_fallback_invoices"] == n
    assert result["full_five_association_invoices"] + result["any_fallback_invoices"] == n

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "white"})

    # One target per eligible invoice; show distinct association-only and filled lists.
    labels = ["Popularity", "Association only", "Association + fill"]
    hits = [result["baseline_hits"], result["association_only_hits"], result["combined_hits"]]
    fig, ax = plt.subplots(figsize=(8.2, 4.7), layout="constrained")
    bars = ax.bar(labels, [100 * h / n for h in hits],
                  color=[COLORS["popularity"], COLORS["association"], COLORS["combined"]], width=.58)
    for bar, h in zip(bars, hits):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + .55,
                f"{h:,}/{n:,}  ({100*h/n:.2f}%)", ha="center", fontsize=9)
    ax.set_ylim(0, max(100*h/n for h in hits) + 4.2)
    ax.set_ylabel("Hit rate@5 (% of eligible test invoices)")
    ax.set_title("Cart-based recovery in the frozen test period", loc="left", weight="bold", pad=16)
    ax.text(0, 1.02, "Same hidden target and candidate universe for all methods", transform=ax.transAxes,
            color="#4a5568", fontsize=9)
    ax.grid(axis="y", alpha=.22)
    ax.set_axisbelow(True)
    fig.savefig(OUT / "method_comparison.svg")
    fig.savefig(OUT / "method_comparison.png", dpi=180)
    plt.close(fig)

    # Groups are fixed by primary training popularity ranks, never by test frequency.
    names = ["Head", "Middle", "Tail", "Unseen"]
    groups = [result["groups"][x.lower()] for x in names]
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    xs = list(range(4))
    width = .34
    baseline = ax.bar([x-width/2 for x in xs], [100*g["baseline_hits"]/g["invoices"] for g in groups],
                      width, label="Popularity", color=COLORS["popularity"])
    combined = ax.bar([x+width/2 for x in xs], [100*g["combined_hits"]/g["invoices"] for g in groups],
                      width, label="Association + fill", color=COLORS["combined"])
    for bars, field in ((baseline, "baseline_hits"), (combined, "combined_hits")):
        for bar, group in zip(bars, groups):
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+.55,
                    f"{group[field]}/{group['invoices']}", ha="center", fontsize=8)
    ax.set_xticks(xs, [f"{name}\nn={group['invoices']:,}" for name,group in zip(names,groups)])
    ax.set_ylim(0, max(100*g["combined_hits"]/g["invoices"] for g in groups)+5)
    ax.set_ylabel("Hit rate@5 within target group (%)")
    ax.set_title("Test recovery by training-defined target popularity", loc="left", weight="bold", pad=16)
    products = data["training_catalog_product_counts"]
    ax.text(0, 1.02, f"Training catalog: head {products['head']:,}, middle {products['middle']:,}, tail {products['tail']:,} products",
            transform=ax.transAxes, color="#4a5568", fontsize=9)
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="y", alpha=.22)
    ax.set_axisbelow(True)
    fig.savefig(OUT / "popularity_breakdown.svg")
    fig.savefig(OUT / "popularity_breakdown.png", dpi=180)
    plt.close(fig)

    # Order-level evidence and suggestion-slot fill are different coverage concepts.
    full_assoc = result["full_five_association_invoices"]
    full_fallback = result["full_fallback_invoices"]
    mixed = result["any_fallback_invoices"] - full_fallback
    assert full_assoc + mixed + full_fallback == n
    fig, ax = plt.subplots(figsize=(9, 4.6), layout="constrained")
    rows = [
        ("Suggestion source", [(full_assoc, COLORS["association"], "Five association slots"),
                               (mixed, COLORS["mixed"], "Mixed list"),
                               (full_fallback, COLORS["fallback"], "Full popularity fallback")]),
        ("Target catalog", [(result["known_targets"], COLORS["combined"], "Known target"),
                             (result["unseen_targets"], COLORS["unseen"], "Unseen target")]),
    ]
    for y,(label,parts) in enumerate(rows):
        left = 0
        for count,color,name in parts:
            ax.barh(y, count, left=left, color=color, height=.52, label=name)
            if count >= 100:
                ax.text(left+count/2, y, f"{count:,}", va="center", ha="center",
                        color="white" if color != COLORS["unseen"] else "#1a202c", weight="bold", fontsize=9)
            left += count
    ax.set_yticks([0,1], [row[0] for row in rows])
    ax.invert_yaxis()
    ax.set_xlim(0,n)
    ax.set_xlabel(f"Eligible test invoices (n={n:,})")
    ax.set_title("Association coverage, fallback and catalog reach", loc="left", weight="bold", pad=16)
    ax.text(0, 1.02, f"Association candidates: {result['association_coverage_invoices']:,}/{n:,}; "
            f"fill: {mixed} mixed list + {full_fallback} full fallback",
            transform=ax.transAxes, color="#4a5568", fontsize=9)
    handles, legends = ax.get_legend_handles_labels()
    ax.legend(handles, legends, frameon=False, loc="lower center", bbox_to_anchor=(.5,-.4), ncol=3, fontsize=8)
    fig.savefig(OUT / "coverage_fallback.svg", bbox_inches="tight")
    fig.savefig(OUT / "coverage_fallback.png", bbox_inches="tight", dpi=180)
    plt.close(fig)
    print("Wrote three charts from", METRICS)


if __name__ == "__main__":
    main()
