import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vee import store


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "workspace.sqlite"
        store.init(self.path)
        self.item = store.detail(self.path, "ENQ-1042")

    def act(self, action, **fields):
        self.item = store.act(self.path, self.item["id"], action, {"revision": self.item["revision"], **fields})

    def reply(self):
        self.act("approve_clarification")
        self.act("simulate_reply")

    def draft(self):
        self.reply()
        self.act("verify_match", sku="CYL-32-100-DA")
        self.act("create_quote")

    def test_employee_approval_and_reply_precede_technical_verification(self):
        self.assertEqual(self.item["status"], "needs_clarification")
        self.assertTrue(self.item["attachments"][0]["text"])
        for action in ("simulate_reply", "verify_match", "create_quote", "approve_quote"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.act(action, sku="CYL-32-100-DA")
        self.act("save_clarification", body="Can you confirm dimensions, type, ports, standard and mount?")
        self.assertEqual(len(self.item["thread"]), 1)
        self.act("approve_clarification")
        self.assertEqual(self.item["thread"][-1]["body"], self.item["clarification"])
        self.act("simulate_reply")
        self.assertEqual(len(self.item["thread"]), 3)
        with self.assertRaises(ValueError):
            self.act("verify_match", sku="UNKNOWN")
        with self.assertRaises(ValueError):
            self.act("create_quote")
        self.act("verify_match", sku="CYL-32-100-DA")
        self.assertEqual(self.item["selected_sku"], "CYL-32-100-DA")
        self.assertEqual(self.item["status"], "verified")

    def test_rejection_edit_and_approval_preserve_quote_versions_on_restart(self):
        self.draft()
        initial = self.item["quotes"][0].copy()
        self.act("reject_quote", reason="Adjust the quantity with the customer.")
        with self.assertRaises(ValueError):
            self.act("approve_quote")
        self.act("edit_quote", quantity="3", notes="Confirmed by buyer.")
        self.act("approve_quote")
        with self.assertRaises(ValueError):
            self.act("edit_quote", quantity="4")
        store.init(self.path)
        item = store.detail(self.path, self.item["id"])
        self.assertEqual(item["status"], "approved")
        self.assertEqual(item["quotes"][0], initial)
        self.assertEqual(item["quotes"][-1]["lines"][0]["quantity"], 3)
        self.assertEqual(item["quotes"][-1]["version"], 2)
        self.assertEqual(item["history"][-1]["action"], "approve_quote")

    def test_invalid_commercial_edits_do_not_change_saved_draft(self):
        self.draft()
        for fields in ({"quantity": "0"}, {"quantity": "-2"}, {"quantity": "1.5"},
                       {"quantity": "999999999"}, {"unit_price": "0.01"}, {"quantity_UNKNOWN": "2"}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.act("edit_quote", **fields)
        self.assertEqual(store.detail(self.path, self.item["id"]), self.item)

    def test_missing_revision_and_concurrent_edits_cannot_overwrite(self):
        with self.assertRaises(ValueError):
            store.act(self.path, self.item["id"], "save_clarification", {"body": "Missing control"})
        def edit(body):
            try:
                store.act(self.path, self.item["id"], "save_clarification",
                          {"revision": self.item["revision"], "body": body})
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(executor.map(edit, ("Version A", "Version B")), [True, False])
        saved = store.detail(self.path, self.item["id"])
        self.assertEqual(saved["revision"], self.item["revision"] + 1)
        self.assertEqual(len(saved["history"]), len(self.item["history"]) + 1)

    def test_audit_write_failure_rolls_back_enquiry_transition(self):
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'unavailable'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.act("approve_clarification")
        self.assertEqual(store.detail(self.path, self.item["id"]), self.item)

    def test_employee_can_reject_technical_suggestion_and_clarification(self):
        self.reply()
        self.act("reject_match", reason="Mounting detail needs a second measurement.")
        self.assertEqual(self.item["status"], "needs_clarification")
        with self.assertRaises(ValueError):
            self.act("verify_match", sku="CYL-32-100-DA")
        self.act("reject_clarification", reason="Check the part label first.")
        with self.assertRaises(ValueError):
            self.act("approve_clarification")
        self.act("save_clarification", body="Can you confirm the part label?")
        self.act("approve_clarification")
        self.assertEqual(self.item["status"], "awaiting_reply")

    def test_multi_line_verification_requires_all_products(self):
        self.item = next(r for r in store.inbox(self.path) if len(r["extraction"]["lines"]) > 1)
        with self.assertRaises(ValueError):
            self.act("verify_match", sku="BRG-6205-2RS")
        self.act("verify_match", sku_0="BRG-6205-2RS", sku_1="BLT-M12-80")
        self.act("create_quote")
        self.act("edit_quote", **{"quantity_BRG-6205-2RS": "1", "quantity_BLT-M12-80": "2"})
        self.assertEqual([line["quantity"] for line in self.item["quotes"][-1]["lines"]], [1, 2])

    def test_technical_match_with_unavailable_stock_has_commercial_hold(self):
        held = store.detail(self.path, "ENQ-1038")
        self.assertEqual(held["status"], "commercial_hold")
        self.assertEqual(held["extraction"]["lines"][0]["status"], "verified")
        self.assertIn("stock", " ".join(held["extraction"]["lines"][0]["issues"]).lower())
        for action in ("verify_match", "approve_clarification", "create_quote", "approve_quote"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                store.act(self.path, held["id"], action, {"revision": held["revision"], "sku": "ADP-NPT-14"})

    def test_clarification_cannot_silently_append_an_item_or_double_original_quantity(self):
        for amendment in ("1 x BRG-6205-2RS", "3 x CYL-32-100-DA"):
            with self.subTest(amendment=amendment), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "reply.sqlite"
                store.init(path)
                initial = store.detail(path, "ENQ-1042")
                awaiting = store.act(path, initial["id"], "approve_clarification", {"revision": initial["revision"]})
                result = store.act(path, initial["id"], "simulate_reply", {
                    "revision": awaiting["revision"], "body": initial["sample_reply"] + "\n" + amendment})
                self.assertEqual(result["status"], "needs_clarification")
                self.assertFalse(result["extraction"]["ready"])
                self.assertTrue(result["extraction"]["questions"])
                self.assertIn(amendment, result["thread"][-1]["body"])

    def test_approval_rejects_simultaneous_unsaved_edits(self):
        self.draft()
        with self.assertRaises(ValueError):
            self.act("approve_quote", quantity="5", notes="New delivery address")
        self.assertEqual(store.detail(self.path, self.item["id"]), self.item)

    def test_customer_amendment_requires_employee_rationale_and_new_technical_review(self):
        self.act("approve_clarification")
        self.act("simulate_reply", body="Revised request: 3 x BRG-6205-2RS.")
        self.assertEqual(self.item["status"], "needs_clarification")
        with self.assertRaises(ValueError):
            self.act("reconcile_requirements", reason="")
        self.act("reconcile_requirements", reason="Customer replaced the full original request.")
        self.assertEqual(self.item["status"], "needs_verification")
        self.assertEqual(self.item["extraction"]["lines"][0]["sku"], "BRG-6205-2RS")
        self.assertEqual(len(self.item["thread"]), 3)
        self.assertIn("two replacement pneumatic cylinders", self.item["thread"][0]["body"])
        with self.assertRaises(ValueError):
            self.act("create_quote")
        self.act("verify_match", sku="BRG-6205-2RS")
        self.act("create_quote")
        self.assertEqual(self.item["quotes"][0]["quantity"], 3)

    def test_reconciliation_does_not_grant_an_unverified_match_or_erase_safety_history(self):
        self.act("approve_clarification")
        self.act("simulate_reply", body="Revised request: 1 x CYL-UNKNOWN for oxygen service.")
        self.act("reconcile_requirements", reason="Documenting the revised customer order.")
        self.assertEqual(self.item["status"], "needs_clarification")
        self.act("approve_clarification")
        self.act("simulate_reply", body="Revised request: 1 x BRG-6205-2RS.")
        self.act("reconcile_requirements", reason="Recorded a new catalogue reference.")
        self.assertEqual(self.item["status"], "needs_clarification")
        with self.assertRaises(ValueError):
            self.act("verify_match", sku="BRG-6205-2RS")

    def test_technical_drift_requires_refresh_and_fresh_version(self):
        from dataclasses import replace
        from unittest.mock import patch

        from vee.catalogue import BY_SKU

        self.item = store.detail(self.path, "ENQ-1041")
        sku = "BRG-6205-2RS"
        self.act("verify_match", sku=sku)
        self.act("create_quote")
        old = self.item["quotes"][0].copy()
        part = BY_SKU[sku]
        changed = replace(part, specs={**part.specs, "closure": "metal shields"})
        with patch.dict(BY_SKU, {sku: changed}):
            for action in ("edit_quote", "approve_quote"):
                with self.subTest(action=action), self.assertRaises(ValueError):
                    self.act(action)
            self.act("refresh_evidence")
            self.assertEqual(self.item["selected_skus"], [])
            self.assertEqual(self.item["status"], "needs_verification")
            self.act("verify_match", sku=sku)
            self.act("create_quote")
            self.assertEqual(self.item["quotes"][0], old)
            self.assertEqual(old["technical_evidence"][0]["specs"]["closure"], "rubber seals")
            self.assertEqual(self.item["quotes"][-1]["technical_evidence"][0]["specs"]["closure"], "metal shields")
            self.assertEqual(self.item["quotes"][-1]["version"], 2)
            self.act("approve_quote")

    def test_employee_reconciliation_preserves_unsupported_service_condition(self):
        self.act("approve_clarification")
        self.act("simulate_reply", body="Revised request: 1 x BRG-6205-2RS for explosive atmospheres.")
        self.act("reconcile_requirements", reason="Capture the customer's new service requirement.")
        self.act("approve_clarification")
        self.act("simulate_reply", body="Revised request: 1 x BRG-6205-2RS.")
        self.act("reconcile_requirements", reason="The reference was confirmed.")
        self.assertEqual(self.item["status"], "needs_clarification")
        self.assertTrue(any("qualified" in issue for line in self.item["extraction"]["lines"] for issue in line["issues"]))

    def test_missing_old_part_number_does_not_block_explicit_verified_replacement(self):
        self.item = store.detail(self.path, "ENQ-1039")
        self.act("approve_clarification")
        self.act("simulate_reply", body="Revised request: 1 x CYL-32-100-DA.")
        self.act("reconcile_requirements", reason="Customer supplied the complete replacement order.")
        self.assertEqual(self.item["status"], "needs_verification")
