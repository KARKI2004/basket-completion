"""Hand-checkable approved-policy examples; no source workbook is needed."""
import sqlite3
import unittest

from basket_completion.holdout import hide_one
from basket_completion.popularity import recommend_popular
from basket_completion.prepare import SQL_DIR


class PreparationTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""CREATE TABLE source_lines (
            invoice TEXT, stock TEXT, description TEXT, quantity INTEGER,
            unit_price REAL, invoice_date TEXT, customer_id TEXT)""")
        rows = [
            ("A", "X", "Widget A", 1, 2, "2011-08-01 10:00:00", None),
            ("A", "X", "Widget A", 2, 2, "2011-08-01 10:00:00", None),
            ("A", "Y", "Other", 1, 2, "2011-08-01 10:00:00", None),
            ("A", "POST", "POSTAGE", 1, 2, "2011-08-01 10:00:00", None),
            ("B", "X", "Widget B", 1, 2, "2011-08-02 10:00:00", "1"),
            ("B", "15056n", "Parasol", 1, 2, "2011-08-02 10:00:00", "1"),
            ("B", "15056N", "Parasol", 1, 2, "2011-08-02 10:00:00", "1"),
            ("V", "X", "Validation name", 1, 2, "2011-09-02 10:00:00", None),
            ("V", "Z", "Only validation", 1, 2, "2011-09-02 10:00:00", None),
            ("T", "X", "Test name", 1, 2, "2011-11-02 10:00:00", None),
            ("T", "Q", "Only test", 1, 2, "2011-11-02 10:00:00", None),
            ("C1", "X", "Cancelled", -1, 2, "2011-08-01 10:00:00", None),
            ("C1", "Y", "Cancelled", -1, 2, "2011-08-01 10:00:00", None),
            ("FREE", "X", "Free", 1, 0, "2011-08-01 10:00:00", None),
            ("FREE", "Y", "Free", 1, 0, "2011-08-01 10:00:00", None),
            ("NEG", "X", "Returned", -1, 2, "2011-08-01 10:00:00", None),
            ("NEG", "Y", "Returned", -1, 2, "2011-08-01 10:00:00", None),
            ("c1", "X", "Lowercase invoice prefix", 1, 2, "2011-09-03 10:00:00", None),
            ("c1", "Y", "Lowercase invoice prefix", 1, 2, "2011-09-03 10:00:00", None),
            ("BOUNDARY", "X", "Cross", 1, 2, "2011-08-31 23:59:00", None),
            ("BOUNDARY", "Y", "Cross", 1, 2, "2011-09-01 00:00:00", None),
            ("BOUNDARY_SERVICE", "X", "Cross", 1, 2, "2011-08-31 23:59:00", None),
            ("BOUNDARY_SERVICE", "Y", "Cross", 1, 2, "2011-08-31 23:59:00", None),
            ("BOUNDARY_SERVICE", "POST", "POSTAGE", 1, 2, "2011-09-01 00:00:00", None),
            ("SINGLE", "X", "Only one", 1, 2, "2011-08-03 10:00:00", None),
        ]
        rows += [("BIG", f"P{i:03d}", "Large", 1, 2, "2011-08-03 10:00:00", None) for i in range(100)]
        self.conn.executemany("INSERT INTO source_lines VALUES (?,?,?,?,?,?,?)", rows)
        self.conn.executescript((SQL_DIR / "prepare.sql").read_text())
        self.conn.executescript((SQL_DIR / "catalog.sql").read_text())

    def tearDown(self):
        self.conn.close()

    def test_cleaning_presence_and_complete_invoice_split(self):
        baskets = dict(self.conn.execute("SELECT invoice, split FROM split_baskets"))
        self.assertEqual(baskets, {"A": "train", "B": "train", "c1": "validation", "V": "validation", "T": "test"})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM basket_items WHERE invoice='A'").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM basket_items WHERE invoice='B'").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT customer_id FROM split_baskets WHERE invoice='A'").fetchone()[0], None)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM merchandise_lines WHERE product='POST'").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM positive_lines WHERE invoice='C1'").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM positive_lines WHERE invoice='FREE'").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM positive_lines WHERE invoice='NEG'").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT basket_size FROM basket_sizes WHERE invoice='BOUNDARY'").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT basket_size FROM basket_sizes WHERE invoice='BOUNDARY_SERVICE'").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM merchandise_lines WHERE invoice='BOUNDARY_SERVICE'").fetchone()[0], 2)

    def test_training_catalog_names_popularity_and_recommendations(self):
        catalog = {p: (name, count) for p, name, count in self.conn.execute(
            "SELECT product, display_name, basket_count FROM train_catalog")}
        self.assertEqual(catalog, {"X": ("Widget A", 2), "Y": ("Other", 1), "15056N": ("Parasol", 1)})
        self.assertNotIn("Z", catalog)
        self.assertNotIn("Q", catalog)
        self.assertEqual(recommend_popular(self.conn, {"X"}), ["15056N", "Y"])
        self.assertEqual(recommend_popular(self.conn, {"X", "15056N"}), ["Y"])
        self.assertEqual(recommend_popular(self.conn, set(), 0), [])

    def test_holdout_is_stable_and_removes_target(self):
        target, visible = hide_one("V", ["Z", "X", "X"])
        self.assertEqual((target, visible), ("X", ("Z",)))
        self.assertEqual((target, visible), hide_one("V", ["X", "Z"]))
        self.assertEqual(set(visible) | {target}, {"X", "Z"})
        self.assertNotIn(target, visible)
        with self.assertRaises(ValueError):
            hide_one("SINGLE", ["X"])


if __name__ == "__main__":
    unittest.main()
