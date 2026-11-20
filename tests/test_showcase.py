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


class PartialQuoteTests(unittest.TestCase):
    def test_employee_accepts_a_bounded_shortfall_and_recovery_preserves_it(self):
        import tempfile
        from pathlib import Path
        from uuid import uuid4

        from vee import backup

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workspace.sqlite"
            store.init(path)
            key = store.receive(path, str(uuid4()), "Kauri Engineering", "Bearing quotation", "10 x BRG-6203-ZZ")
            item = store.detail(path, key)

            def act(action, **fields):
                nonlocal item
                item = store.act(path, key, action, {"revision": item["revision"], **fields})

            self.assertEqual(item["status"], "commercial_hold")
            for action in ("verify_match", "create_quote", "approve_quote"):
                with self.assertRaises(ValueError):
                    act(action, sku="BRG-6203-ZZ")
            act("verify_partial", sku="BRG-6203-ZZ")
            act("create_quote")
            line = item["quotes"][0]["lines"][0]
            self.assertEqual((line["requested_quantity"], line["quantity"], line["stock"]), (10, 6, 6))
            self.assertEqual(item["quotes"][0]["total"], "67.62")
            with self.assertRaises(ValueError):
                act("edit_quote", quantity="7")
            act("approve_quote")
            recovered = Path(directory) / "copy.sqlite"
            backup.copy_workspace(path, recovered)
            self.assertEqual(store.detail(recovered, key), item)

    def test_only_safe_single_line_shortages_qualify(self):
        for body, account in [
            ("1 x ADP-NPT-14", ""), ("2 x BRG-6208-ZZ", ""),
            ("10 x BRG-6203-ZZ", "Contract Only Engineering"),
            ("10 x BRG-6203-ZZ, bore 42 mm", ""),
            ("10 x BRG-6203-ZZ\n1 x BLT-M12-80", ""),
            ("1 x CYL-32-OLD", ""),
        ]:
            with self.subTest(body=body, account=account):
                self.assertIsNone(catalogue.partial_offer(catalogue.analyse(body, account)))
