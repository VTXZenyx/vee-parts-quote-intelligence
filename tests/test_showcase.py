import unittest
from collections import Counter

from vee import catalogue, store


class DistributorTests(unittest.TestCase):
    def test_price_book_and_references(self):
        parts = catalogue.catalogue()
        counts = Counter(part["family"] for part in parts)
        self.assertGreaterEqual(min(counts.values()), 5)
        self.assertTrue(40 <= len(parts) == len(catalogue.PARTS) <= 60)
        self.assertEqual(len(store.CUSTOMERS), 6)
        for part in parts:
            with self.subTest(sku=part["sku"]):
                result = catalogue.analyse("1 x " + part["sku"])
                self.assertEqual(result["ready"], bool(part["stock"]) and not part["discontinued"])

    def test_distinguishes_missing_stock_from_zero_and_restricted_prices(self):
        availability = catalogue.current_record("BRG-6208-ZZ")
        self.assertIsNone(availability["stock"])
        self.assertIn("unknown", availability["availability"].lower())
        self.assertEqual(catalogue.current_record("ADP-NPT-14")["stock"], 0)
        self.assertIsNone(catalogue.current_record("BRG-6205-ZZ", "Contract Only Engineering")["unit_price"])
        self.assertEqual(catalogue.current_record("BRG-6205-2RS", "Contract Only Engineering")["unit_price"], "10.00")
