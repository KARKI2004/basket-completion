"""Hand-verifiable UI service and basket state checks."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from basket_completion.association import pair_rows_for_visible, recommend_from_rows
from basket_completion.demo import (
    DemoService, FROZEN_SETTING, Product, add_product, basket_for_url,
    basket_from_url, load_saved_results, remove_product, set_quantity,
)


class DemoServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "toy.sqlite"
        with sqlite3.connect(self.database) as conn:
            conn.execute("""CREATE TABLE train_directional_stats
                (antecedent TEXT,candidate TEXT,pair_count INTEGER,support REAL,confidence REAL,lift REAL)""")
            conn.executemany("INSERT INTO train_directional_stats VALUES (?,?,?,?,?,?)", [
                ("A", "C", 3, .3, .6, 2.0),
                ("A", "D", 2, .2, .4, 1.0),  # Below frozen minimum evidence.
            ])
        self.service = DemoService(self.database, (
            Product("A", "Apron", 5), Product("B", "Bowl", 4),
            Product("C", "Cup", 3), Product("D", "Dish", 2),
            Product("E", "Egg cup", 1), Product("F", "Fork", 1),
        ))

    def tearDown(self):
        self.temp.cleanup()

    def test_frozen_recommendation_parity_and_labels(self):
        actual = self.service.recommend(("A",))
        with sqlite3.connect(self.database) as conn:
            rows = pair_rows_for_visible(conn, ("A",))
        expected = recommend_from_rows(rows, ("A",), self.service.popularity, FROZEN_SETTING)
        self.assertEqual(actual, expected)
        self.assertEqual([(x.product, x.source) for x in actual.combined], [
            ("C", "association"), ("B", "popularity"), ("D", "popularity"),
            ("E", "popularity"), ("F", "popularity"),
        ])
        self.assertEqual(actual.combined[0].evidence.pair_count, 3)
        self.assertNotIn("A", [x.product for x in actual.combined])

    def test_multiple_supporting_rows_are_read_only_and_ordered(self):
        with sqlite3.connect(self.database) as conn:
            conn.execute("INSERT INTO train_directional_stats VALUES (?,?,?,?,?,?)",
                         ("B", "C", 3, .3, .5, 1.7))
        result = self.service.recommend(("A", "B"))
        self.assertEqual(result.combined[0].product, "C")
        self.assertEqual(result.combined[0].score, .6)  # frozen maximum, not sum
        self.assertEqual(result.combined[0].evidence.antecedent, "A")
        rows = self.service.supporting_evidence(("A", "B"), ("C",))
        self.assertEqual([row.antecedent for row in rows["C"]], ["A", "B"])
        self.assertEqual([(row.confidence, row.lift) for row in rows["C"]], [(.6, 2.0), (.5, 1.7)])
        self.assertEqual(result, self.service.recommend(("A", "B")))

    def test_empty_unknown_search_and_sparse_evidence(self):
        self.assertEqual([x.source for x in self.service.recommend(()).combined], ["popularity"] * 5)
        self.assertEqual([x.source for x in self.service.recommend(("UNKNOWN",)).combined], ["popularity"] * 5)
        self.assertEqual(self.service.search("bOw")[0].code, "B")
        self.assertEqual(self.service.search("does not exist"), ())
        self.assertEqual([x.product for x in self.service.recommend(("A", "B", "C", "D", "E")).combined], ["F"])

    def test_three_item_browse_pages_and_search(self):
        first, total, page = self.service.browse("", 0)
        self.assertEqual((len(first), total, page), (3, 6, 0))
        second, _, page = self.service.browse("", 1)
        self.assertEqual(([item.code for item in second], page), (["D", "E", "F"], 1))
        found, total, page = self.service.browse("bowl", 9)
        self.assertEqual(([item.code for item in found], total, page), (["B"], 1, 0))
        empty, total, page = self.service.browse("unknown", 2)
        self.assertEqual((empty, total, page), ((), 0, 0))

    def test_state_changes_and_quantity_independence(self):
        basket = {}
        catalog = set(self.service.names)
        self.assertEqual(add_product(basket, "A", catalog), "added")
        before = self.service.recommend(tuple(basket))
        self.assertEqual(add_product(basket, "A", catalog), "duplicate")
        self.assertEqual(add_product(basket, "UNKNOWN", catalog), "unknown")
        set_quantity(basket, "A", 7)
        self.assertEqual(before, self.service.recommend(tuple(basket)))
        with self.assertRaises(ValueError):
            set_quantity(basket, "A", 0)
        remove_product(basket, "A")
        self.assertEqual(basket, {})

    def test_displayed_results_match_saved_reviewed_metrics(self):
        metrics = load_saved_results()
        main = metrics["primary"]
        self.assertAlmostEqual(main["combined_hit_rate_at_5"], main["combined_hits"] / main["invoices"])
        self.assertAlmostEqual(main["baseline_hit_rate_at_5"], main["baseline_hits"] / main["invoices"])
        self.assertEqual(main["known_targets"] + main["unseen_targets"], main["invoices"])
        self.assertEqual(sum(group["combined_hits"] for group in main["groups"].values()), main["combined_hits"])

    def test_refresh_state_only_restores_known_positive_items(self):
        catalog = set(self.service.names)
        saved = basket_for_url({"B": 3, "A": 1})
        self.assertEqual(basket_from_url(saved, catalog), {"A": 1, "B": 3})
        self.assertEqual(basket_from_url('{"A":2,"UNKNOWN":4,"B":0,"C":true}', catalog), {"A": 2})
        self.assertEqual(basket_from_url("not json", catalog), {})

    def test_missing_artifacts_fail_closed(self):
        with patch("basket_completion.demo.DEPLOY_DB", Path(self.temp.name) / "missing.sqlite"):
            with self.assertRaisesRegex(FileNotFoundError, "Run `python -m basket_completion.export_demo`"):
                DemoService.from_frozen()
        with patch("basket_completion.demo.REVIEWED_REPORT", Path(self.temp.name) / "missing.md"):
            with self.assertRaises(FileNotFoundError):
                load_saved_results()


if __name__ == "__main__":
    unittest.main()
