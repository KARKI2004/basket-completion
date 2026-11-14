"""Small training baskets with pair statistics calculable by hand."""
import sqlite3
import unittest

from basket_completion.association import (
    PairEvidence,
    SETTINGS,
    Setting,
    pair_rows_for_visible,
    recommend_all_settings,
    recommend_from_rows,
)
from basket_completion.prepare import SQL_DIR


class AssociationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE split_baskets (invoice TEXT, split TEXT)")
        self.db.execute("CREATE TABLE basket_items (invoice TEXT, split TEXT, product TEXT)")
        baskets = {"I1": ("A", "B", "C"), "I2": ("A", "B"), "I3": ("A", "C"),
                   "I4": ("A", "D"), "I5": ("C", "D")}
        self.db.executemany("INSERT INTO split_baskets VALUES (?, 'train')", [(invoice,) for invoice in baskets])
        self.db.executemany("INSERT INTO basket_items VALUES (?, 'train', ?)", [
            (invoice, product) for invoice, products in baskets.items() for product in products
        ])
        self.db.execute("CREATE UNIQUE INDEX basket_items_key ON basket_items(invoice,product)")
        self.db.execute("CREATE INDEX basket_items_split_product ON basket_items(split,product)")
        self.db.execute("CREATE TABLE train_popularity AS SELECT product, COUNT(*) AS basket_count FROM basket_items GROUP BY product")
        self.db.executescript((SQL_DIR / "pairs.sql").read_text())
        self.popularity = dict(self.db.execute("SELECT product,basket_count FROM train_popularity"))

    def tearDown(self):
        self.db.close()

    def test_pair_count_support_directional_confidence_and_lift(self):
        self.assertEqual(dict(self.db.execute("SELECT product_a||'-'||product_b,pair_count FROM train_pairs")),
                         {"A-B": 2, "A-C": 2, "A-D": 1, "B-C": 1, "C-D": 1})
        a_to_b = self.db.execute("SELECT pair_count,support,confidence,lift FROM train_directional_stats WHERE antecedent='A' AND candidate='B'").fetchone()
        b_to_a = self.db.execute("SELECT pair_count,support,confidence,lift FROM train_directional_stats WHERE antecedent='B' AND candidate='A'").fetchone()
        self.assertEqual(a_to_b[0], 2)
        self.assertAlmostEqual(a_to_b[1], 0.4)
        self.assertAlmostEqual(a_to_b[2], 0.5)
        self.assertAlmostEqual(b_to_a[2], 1.0)
        self.assertAlmostEqual(a_to_b[3], 1.25)
        self.assertAlmostEqual(b_to_a[3], 1.25)
        self.assertEqual(self.db.execute("""SELECT COUNT(*) FROM train_pairs p
            JOIN train_popularity a ON a.product=p.product_a
            JOIN train_popularity b ON b.product=p.product_b
            WHERE p.pair_count>MIN(a.basket_count,b.basket_count)""").fetchone()[0], 0)

    def test_multi_item_aggregation_duplicate_candidates_and_fallback(self):
        rows = pair_rows_for_visible(self.db, ("A", "B"))
        # Helper queries approved count >=3, so toy rows below are supplied directly.
        toy_rows = tuple(PairEvidence(*row) for row in self.db.execute(
            "SELECT antecedent,candidate,pair_count,support,confidence,lift FROM train_directional_stats WHERE antecedent IN ('A','B')"))
        result = recommend_from_rows(toy_rows + toy_rows[:1], ("A", "B"), self.popularity,
                                     Setting(1, "confidence", "sum"))
        self.assertEqual([item.product for item in result.association_only], ["C", "D"])
        self.assertEqual([item.product for item in result.combined], ["C", "D"])
        self.assertEqual(result.association_only[0].score, 1.0)  # A->C .5 + B->C .5, once each
        self.assertEqual(result.association_only[0].source, "association")
        self.assertTrue(all(item.product not in {"A", "B"} for item in result.combined))
        self.assertEqual(rows, ())
        strict = recommend_from_rows(toy_rows, ("A", "B"), self.popularity,
                                     Setting(2, "confidence", "maximum"))
        self.assertEqual([item.product for item in strict.association_only], ["C"])
        self.assertEqual([(item.product, item.source) for item in strict.combined],
                         [("C", "association"), ("D", "popularity")])

    def test_unknown_input_and_deterministic_ties(self):
        unknown = recommend_from_rows((), ("UNKNOWN",), self.popularity,
                                      Setting(1, "confidence", "maximum"))
        self.assertEqual([item.product for item in unknown.combined], ["A", "C", "B", "D"])
        self.assertTrue(all(item.source == "popularity" for item in unknown.combined))
        self.assertEqual(unknown, recommend_from_rows((), ("UNKNOWN",), self.popularity,
                                                       Setting(1, "confidence", "maximum")))

    def test_frozen_overlap_exclusion_and_tie_order(self):
        rows = (
            PairEvidence("A", "C", 3, .03, .6, 2.0),
            PairEvidence("B", "C", 4, .04, .5, 1.5),
            PairEvidence("A", "D", 3, .03, .6, 1.1),
            PairEvidence("B", "A", 5, .05, .9, 2.0),  # already in cart
            PairEvidence("A", "E", 2, .02, .9, 3.0),  # below frozen threshold
        )
        popularity = {"A": 10, "B": 9, "C": 7, "D": 7, "E": 6, "F": 5}
        actual = recommend_from_rows(rows, ("A", "B"), popularity,
                                     Setting(3, "confidence", "maximum"), limit=4)
        self.assertEqual([item.product for item in actual.combined], ["C", "D", "E", "F"])
        self.assertEqual([item.source for item in actual.combined],
                         ["association", "association", "popularity", "popularity"])
        self.assertEqual(actual.association_only[0].score, .6)  # C once, maximum of .6 and .5
        self.assertEqual(actual.association_only[0].evidence.antecedent, "A")
        self.assertEqual(actual.eligible_association_candidates, 2)

    def test_all_settings_match_individual_scoring(self):
        rows = (
            PairEvidence("A", "C", 10, .1, .5, 2.0),
            PairEvidence("B", "C", 3, .03, .25, 1.0),
            PairEvidence("A", "D", 3, .03, .25, 1.0),
        )
        together = recommend_all_settings(rows, ("A", "B"), self.popularity)
        self.assertEqual(set(together), set(SETTINGS))
        for setting in SETTINGS:
            self.assertEqual(together[setting], recommend_from_rows(rows, ("A", "B"), self.popularity, setting))

    def test_pair_rows_have_stable_order_and_minimum_evidence(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE train_directional_stats (antecedent TEXT,candidate TEXT,pair_count INTEGER,support REAL,confidence REAL,lift REAL)")
            db.executemany("INSERT INTO train_directional_stats VALUES (?,?,?,?,?,?)", [
                ("B", "Z", 3, .3, .5, 1.0),
                ("A", "Y", 2, .2, .4, 1.0),
                ("A", "X", 3, .3, .5, 1.0),
                ("B", "X", 3, .3, .5, 1.0),
            ])
            rows = pair_rows_for_visible(db, ("B", "A"))
            self.assertEqual([(row.antecedent, row.candidate) for row in rows],
                             [("A", "X"), ("B", "X"), ("B", "Z")])


if __name__ == "__main__":
    unittest.main()
