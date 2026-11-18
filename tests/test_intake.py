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
