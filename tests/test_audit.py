"""Small examples whose expected answers can be checked by hand."""
import unittest

import pandas as pd

from basket_completion.audit import (
    distinct_presence,
    invoice_anomalies,
    monthly_invoice_counts,
    possible_pairs,
    row_flags,
)


class AuditHelpersTest(unittest.TestCase):
    def test_flags_overlap_without_double_counting_rows(self):
        rows = pd.DataFrame(
            {
                "InvoiceNo": ["C1", "2", "3"],
                "Quantity": [-1, 2, 1],
                "UnitPrice": [0, 0, 1],
                "Description": [None, "gift", "gift"],
            }
        )
        flags = row_flags(rows)
        self.assertEqual(flags.sum().to_dict(), {
            "cancellation_prefix": 1,
            "nonpositive_quantity": 1,
            "nonpositive_price": 2,
            "missing_description": 1,
        })
        self.assertEqual(int(flags.any(axis=1).sum()), 2)

    def test_presence_counts_distinct_products_per_invoice(self):
        rows = pd.DataFrame({
            "invoice": ["A", "A", "A", "B", "B"],
            "stock": ["X", "X", "Y", "X", "Z"],
        })
        presence = distinct_presence(rows)
        self.assertEqual(len(presence), 4)
        self.assertEqual(presence.groupby("invoice").size().to_dict(), {"A": 2, "B": 2})
        self.assertEqual(presence.groupby("stock").size().to_dict(), {"X": 2, "Y": 1, "Z": 1})

    def test_possible_pairs_use_distinct_basket_sizes(self):
        sizes = pd.Series([1, 2, 4])
        self.assertEqual(possible_pairs(sizes).tolist(), [0, 1, 6])

    def test_monthly_counts_each_invoice_once_at_earliest_time(self):
        rows = pd.DataFrame({
            "invoice": ["A", "A", "B"],
            "InvoiceDate": pd.to_datetime(["2020-02-01", "2020-01-31", "2020-02-02"]),
        })
        self.assertEqual(monthly_invoice_counts(rows), {"2020-01": 1, "2020-02": 1})

    def test_customer_and_timestamp_anomalies_are_invoice_level(self):
        rows = pd.DataFrame({
            "invoice": ["A", "A", "B", "B"],
            "InvoiceDate": pd.to_datetime(["2020-01-01 10:00", "2020-01-01 10:01", "2020-01-02 00:00", "2020-01-02 00:00"]),
            "CustomerID": [1.0, 2.0, None, None],
        })
        result = invoice_anomalies(rows)
        self.assertEqual(result["multiple_timestamps"], 1)
        self.assertEqual(result["multiple_known_customer_ids"], 1)
        self.assertEqual(result["mixed_missing_and_known_customer_ids"], 0)


if __name__ == "__main__":
    unittest.main()
