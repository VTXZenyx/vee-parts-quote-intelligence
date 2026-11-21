"""Employee quote edits never establish customer quantities."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from vee import backup, customer, store


class QuoteQuantityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "workspace.sqlite"
        store.init(self.path)
        self.item = store.detail(self.path, "ENQ-1041")

    def act(self, action, **fields):
        self.item = store.act(self.path, self.item["id"], action, {"revision": self.item["revision"], **fields})

    def overage(self):
        self.act("verify_match", sku="BRG-6205-2RS")
        self.act("create_quote")
        self.act("edit_quote", quantity="6", notes="Customer wants six.")

    def test_six_requires_recorded_complete_reply_reconciliation_and_fresh_review(self):
        self.overage()
        draft = self.item
        with self.assertRaisesRegex(ValueError, "BRG-6205-2RS"):
            self.act("approve_quote")
        self.assertEqual(store.detail(self.path, self.item["id"]), draft)
        self.act("request_quantity_confirmation")
        ask = self.item["thread"][-1]
        self.assertEqual(ask["direction"], "outbound")
        self.assertIn("BRG-6205-2RS", ask["body"])
        self.assertIn("4", ask["body"])
        self.assertIn("6", ask["body"])
        self.assertFalse(self.item["selected_skus"])
        backup.copy_workspace(self.path, self.path.with_suffix(".waiting"))
        self.act("simulate_reply", body="Yes, sounds good.")
        self.assertEqual(self.item["status"], "needs_clarification")
        with self.assertRaises(ValueError):
            self.act("reconcile_requirements", reason="Six seems fine.")
        self.act("approve_clarification")
        self.act("simulate_reply", body="Revised request: 6 x BRG-6205-2RS.")
        self.act("reconcile_requirements", reason="Checked the complete list in the customer's reply.")
        self.assertEqual(self.item["status"], "needs_verification")
        with self.assertRaises(ValueError):
            self.act("approve_quote")
        self.act("verify_match", sku="BRG-6205-2RS")
        self.act("create_quote")
        with self.assertRaises(ValueError):
            store.act(self.path, self.item["id"], "approve_quote", {"revision": draft["revision"]})
        self.act("approve_quote")
        self.assertEqual(self.item["quotes"][:-1], draft["quotes"])
        self.assertFalse(customer.current_approved(self.item, "2"))
        self.assertTrue(customer.current_approved(self.item, "3"))
        line = self.item["quotes"][-1]["lines"][0]
        self.assertEqual((line["requested_quantity"], line["quantity"]), (6, 6))
        backup.copy_workspace(self.path, self.path.with_suffix(".approved"))

    def test_multi_product_changes_are_checked_separately(self):
        self.item = store.detail(self.path, "ENQ-1040")
        self.act("verify_match", sku_0="BRG-6205-2RS", sku_1="BLT-M12-80")
        self.act("create_quote")
        self.act("edit_quote", **{"quantity_BRG-6205-2RS": "1", "quantity_BLT-M12-80": "4"})
        with self.assertRaisesRegex(ValueError, "BLT-M12-80"):
            self.act("approve_quote")
        self.act("edit_quote", **{"quantity_BLT-M12-80": "3"})
        self.act("approve_quote")
        self.assertEqual([line["quantity"] for line in self.item["quotes"][-1]["lines"]], [1, 3])

    def test_backup_checks_approved_quantities_against_recorded_customer_evidence(self):
        self.act("verify_match", sku="BRG-6205-2RS")
        self.act("create_quote")
        self.act("approve_quote")
        for damage in (
            "UPDATE enquiries SET state=json_set(state,'$.thread[0].body','2 x BRG-6205-2RS') WHERE id='ENQ-1041'",
            "UPDATE quotes SET snapshot=json_set(snapshot,'$.lines[0].requested_quantity',6) WHERE enquiry_id='ENQ-1041'",
            "UPDATE enquiries SET state=json_set(state,'$.basis_inbound',1) WHERE id='ENQ-1041'",
        ):
            with self.subTest(damage=damage):
                damaged = self.path.with_suffix(".damaged" + str(len(damage)))
                backup.copy_workspace(self.path, damaged)
                with sqlite3.connect(damaged) as db:
                    db.execute(damage)
                with self.assertRaises(ValueError):
                    backup.copy_workspace(damaged, damaged.with_name(damaged.name + ".copy"))

    def test_unsafe_v6_approval_is_historical_after_upgrade_and_restore(self):
        self.overage()
        key = self.item["id"]
        quote = self.item["quotes"][-1]
        revision = self.item["revision"] + 1
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE enquiries SET revision=?,state=json_set(state,'$.status','approved','$.revision',?) "
                       "WHERE id=?", (revision, revision, key))
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (key, revision, quote["created_at"], "Demo employee",
                       "approve_quote", f"Employee approved quotation version 2 for NZD {quote['total']}."))
        unsafe = store.detail(self.path, key)
        self.assertFalse(customer.current_approved(unsafe))
        with self.assertRaisesRegex(ValueError, "quantity"):
            backup.copy_workspace(self.path, self.path.with_suffix(".unsafe"))
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA user_version=4")
        original = self.path.with_suffix(".v6")
        backup.copy_workspace(self.path, original)
        restored = self.path.with_suffix(".restored")
        backup.copy_workspace(original, restored)
        store.init(restored)
        reopened = store.detail(restored, key)
        self.assertEqual(reopened["status"], "needs_verification")
        self.assertEqual(reopened["history"][:-1], unsafe["history"])
        self.assertEqual(reopened["quotes"], unsafe["quotes"])
        self.assertFalse(reopened["selected_skus"])
        self.assertIn("quantity", reopened["history"][-1]["detail"])
        store.init(restored)
        self.assertEqual(store.detail(restored, key), reopened)
        backup.copy_workspace(restored, self.path.with_suffix(".v7"))
