import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from vee import store
from vee.web import create_app


class Intake(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "intake.sqlite3"
        self.client = create_app(self.path).test_client()
        self.data = {"message_id": str(uuid4()), "customer": "Harbour Packaging",
                         "subject": "Cylinder needed", "body": "We need two pneumatic cylinders."}

    def test_idempotent_ingestion_and_conflicting_replay(self):
        first = store.receive(self.path, **self.data)
        self.assertEqual(first, store.receive(self.path, **self.data))
        with self.assertRaises(ValueError):
            store.receive(self.path, **{**self.data, "body": "Quote four bearings."})
        self.assertEqual(len(store.detail(self.path, first)["history"]), 1)

    def test_http_intake_and_validation(self):
        url = "/enquiries/new"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, data=self.data).status_code, 403)
        with self.client.session_transaction() as session:
            self.data["csrf"] = session["csrf"]
        for field, invalid in (("message_id", ""), ("body", " "), ("subject", "S" * 201), ("customer", "Unknown")):
            self.assertEqual(self.client.post(url, data={**self.data, field: invalid}).status_code, 422)
        result = self.client.post(url, data=self.data)
        self.assertEqual(result.status_code, 303)
        page = self.client.get(result.headers["Location"])
        self.assertIn(b"Clarification needed", page.data)
        self.assertIn(b"We need two pneumatic cylinders.", page.data)

    def test_unidentified_photo_has_no_verified_reference(self):
        item = store.detail(self.path, "ENQ-1037")
        self.assertEqual(item["status"], "needs_clarification")
        self.assertFalse(item["extraction"]["ready"])
        page = self.client.get("/enquiries/ENQ-1037")
        self.assertIn(b"inspection-fitting.webp", page.data)
        with self.client.get("/static/inspection-fitting.webp") as picture:
            self.assertEqual(picture.status_code, 200)
            self.assertEqual(picture.data[8:12], b"WEBP")

    def test_governing_subject_conditions_block_verification(self):
        for subject, body in [
            ("Personnel lifting", "2 x CYL-32-100-DA"),
            ("Hydraulic adapter, 350 bar working pressure", "2 x ADP-BSPP-14"),
            ("Qty 12 bearings", "2 x BRG-6205-2RS"),
            ("For continuous immersion", "2 x BRG-6205-2RS"),
            ("Bolt enquiry", "2 x BRG-6205-2RS"),
        ]:
            with self.subTest(subject=subject):
                key = store.receive(self.path, str(uuid4()), "Kauri Engineering", subject, body)
                item = store.detail(self.path, key)
                self.assertEqual(item["status"], "needs_clarification")
                with self.assertRaises(ValueError):
                    store.act(self.path, key, "verify_match", {"revision": 1, "sku": body.split()[-1]})

    def test_bearing_subject_and_explicit_reference_in_body(self):
        for subject in ("Bearing enquiry", "BRG-6205-2RS", "Request for quotation"):
            key = store.receive(self.path, str(uuid4()), "Kauri Engineering", subject, "2 x BRG-6205-2RS")
            self.assertEqual(store.detail(self.path, key)["status"], "needs_verification")

    def test_revised_reference_requires_resolution_of_prior_pressure(self):
        key = store.receive(self.path, str(uuid4()), "Kauri Engineering", "Quotation",
                            "2 x ADP-BSPP-14, working pressure 350 bar")
        item = store.detail(self.path, key)
        for body, expected in [
            ("Revised request: 2 x ADP-BSPP-14", "needs_clarification"),
            ("Revised request: 2 x ADP-BSPP-14, working pressure 200 bar", "needs_verification"),
        ]:
            for action, fields in [("approve_clarification", {}), ("simulate_reply", {"body": body}),
                                   ("reconcile_requirements", {"reason": "Checked customer revision."})]:
                item = store.act(self.path, key, action, {"revision": item["revision"], **fields})
            self.assertEqual(item["status"], expected)

    def test_reopening_existing_unsafe_approval_keeps_history_and_invalidates_forms(self):
        import sqlite3

        key = store.receive(self.path, str(uuid4()), "Kauri Engineering", "RFQ", "2 x ADP-BSPP-14")
        item = store.detail(self.path, key)
        for action, fields in [("verify_match", {"sku": "ADP-BSPP-14"}), ("create_quote", {}), ("approve_quote", {})]:
            item = store.act(self.path, key, action, {"revision": item["revision"], **fields})
        # Model an earlier application version which ignored the subject during verification.
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE enquiries SET state=json_set(state,'$.subject','For oxygen service') WHERE id=?", (key,))
            db.execute("PRAGMA user_version=0")
        store.init(self.path)
        saved = store.detail(self.path, key)
        self.assertEqual(saved["status"], "needs_clarification")
        self.assertEqual(saved["revision"], item["revision"] + 1)
        self.assertEqual(saved["history"][:-1], item["history"])
        self.assertEqual(saved["quotes"], item["quotes"])
        store.init(self.path)
        self.assertEqual(store.detail(self.path, key), saved)

    def test_pressure_from_previous_unlabelled_reply_survives_reconciliation(self):
        key = store.receive(self.path, str(uuid4()), "Kauri Engineering", "RFQ", "2 hydraulic adapters")
        item = store.detail(self.path, key)
        for action, fields in [
            ("approve_clarification", {}),
            ("simulate_reply", {"body": "Working pressure 350 bar."}),
            ("approve_clarification", {}),
            ("simulate_reply", {"body": "Revised request: 2 x ADP-BSPP-14"}),
            ("reconcile_requirements", {"reason": "Customer identified the reference."}),
        ]:
            item = store.act(self.path, key, action, {"revision": item["revision"], **fields})
        self.assertEqual(item["status"], "needs_clarification")
        self.assertIn("pressure", item["clarification"])
