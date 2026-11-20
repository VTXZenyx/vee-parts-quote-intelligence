import tempfile
import unittest
from pathlib import Path

from vee import store
from vee.backup import copy_workspace
from vee.web import create_app


class FindingsWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "workspace"
        self.client = create_app(self.db).test_client()
        self.client.get("/")
        with self.client.session_transaction() as s:
            self.csrf = s["csrf"]

    def post(self, url, **fields):
        return self.client.post(
            url, data={"csrf": self.csrf, **fields}, follow_redirects=True
        )

    def test_provider_ui_and_stale_source_review(self):
        page = self.post("/demo-email/providers", fixture="graph-bearing")
        self.assertIn(b"Accepted", page.data)
        key = store.inbox(self.db)[0]["id"]
        url = "/enquiries/" + key
        response = self.post(url + "/findings", revision=1, source="1", mode="mock")
        self.assertIn(b"Mock model", response.data)
        item = store.detail(self.db, key)
        self.assertEqual(item["status"], "needs_verification")
        self.assertEqual(item["revision"], 2)
        rows = item["advisories"]["1"]["findings"]
        self.assertEqual([r["item"] for r in rows if r["kind"] == "product"], [1])
        response = self.post(
            url + "/findings/review",
            revision=1,
            source="1",
            finding="0",
            decision="confirm",
            reason="Checked the customer message",
        )
        self.assertIn(b"has changed", response.data)
        self.assertEqual(item, store.detail(self.db, key))
        response = self.post(
            url + "/findings/review",
            revision=2,
            source="1",
            finding="0",
            decision="confirm",
            reason="Checked the customer message",
        )
        self.assertIn(b"Employee reviewed", response.data)
        self.assertEqual(store.detail(self.db, key)["status"], "needs_verification")

    def test_material_review_invalidates_approval_and_requires_new_customer_evidence(
        self,
    ):
        key = "ENQ-1041"
        url = "/enquiries/" + key
        for action, fields in [
            ("verify_match", {"sku": "BRG-6205-2RS"}),
            ("create_quote", {}),
            ("approve_quote", {}),
        ]:
            store.act(
                self.db,
                key,
                action,
                {"revision": store.detail(self.db, key)["revision"], **fields},
            )
        original = store.detail(self.db, key)
        self.post(
            url + "/findings/review",
            source="1",
            revision=original["revision"],
            finding="0",
            decision="correct",
            replacement="Possibly two bearings",
            reason="Verify the counted assemblies",
        )
        item = store.detail(self.db, key)
        self.assertEqual(item["status"], "needs_clarification")
        self.assertEqual(item["thread"], original["thread"])
        self.assertEqual(item["quotes"], original["quotes"])
        self.assertIn("Possibly two bearings", item["history"][-1]["detail"])
        self.assertTrue(item["correction_hold"])

        def act(action, **fields):
            return store.act(
                self.db,
                key,
                action,
                {"revision": store.detail(self.db, key)["revision"], **fields},
            )

        with self.assertRaises(ValueError):
            act("verify_match", sku="BRG-6205-2RS")
        act("approve_clarification")
        act("simulate_reply", body="Revised request: 2 x BRG-6205-2RS.")
        self.assertEqual(store.detail(self.db, key)["status"], "needs_clarification")
        ready = act("reconcile_requirements", reason="Customer confirmed revised total")
        self.assertEqual(ready["status"], "needs_verification")
        self.assertEqual(ready["extraction"]["lines"][0]["quantity"], 2)
        copy_workspace(self.db, self.db.with_name("backup"))

    def test_restore_rejects_broken_advisory_source(self):
        import sqlite3

        self.post("/enquiries/ENQ-1041/findings", revision=1, source="1", mode="mock")
        with sqlite3.connect(self.db) as db:
            db.execute("""UPDATE enquiries SET state=json_set(state,'$.advisories."1".findings[0].evidence','invented')
                          WHERE id='ENQ-1041'""")
        with self.assertRaises(ValueError):
            copy_workspace(self.db, self.db.with_name("broken"))
