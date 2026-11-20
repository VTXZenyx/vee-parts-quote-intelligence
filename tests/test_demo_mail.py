import re
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from vee import backup, store
from vee.web import create_app


class DemoMail(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "test.sqlite3"
        self.app = create_app(self.path)
        self.client = self.app.test_client()

    def form(self, page):
        response = self.client.get(page)
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="csrf"[^>]*value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return {"csrf": match[1].decode()}

    def envelope(self, **kwargs):
        return {"message_id": str(uuid4()), "customer": "Harbour Packaging",
                "sender": "buyer@harbour.example", "recipient": "quotes@vee.example",
                "subject": "Cylinder quotation", "body": "Please quote 2 pneumatic cylinders.", **kwargs}

    def deliver(self, envelope, **options):
        return store.receive_demo_email(self.path, **envelope, **options)

    def approve_clarification(self, key):
        return store.act(self.path, key, "approve_clarification",
                         {"revision": store.detail(self.path, key)["revision"]})

    def test_original_delivery_has_metadata_and_is_idempotent(self):
        sent = self.envelope()
        with ThreadPoolExecutor(max_workers=2) as pool:
            (key, duplicate), (same_key, repeated) = list(pool.map(self.deliver, [sent, sent]))
        self.assertNotEqual(duplicate, repeated)
        self.assertEqual(key, same_key)
        enquiry = store.detail(self.path, key)
        self.assertEqual(enquiry["thread"][0]["message_id"], sent["message_id"])
        self.assertEqual(enquiry["thread"][0]["recipient"], sent["recipient"])
        self.assertEqual(len(enquiry["history"]), 1)
        with self.assertRaisesRegex(ValueError, "already received"):
            self.deliver({**sent, "sender": "buyer@kauri.example"})

    def test_reply_follows_explicit_thread_and_revision_and_replays_safely(self):
        original = self.envelope()
        key, _ = self.deliver(original)
        other, _ = self.deliver(self.envelope())
        awaiting = self.approve_clarification(key)
        self.approve_clarification(other)
        reply = self.envelope(subject="Re: Cylinder quotation",
                              body="Bore 32 mm, stroke 100 mm, double acting, ISO 15552, G1/8 ports, foot mount.")
        revision = str(awaiting["revision"])
        options = {"enquiry_id": key, "revision": revision}
        with self.assertRaisesRegex(ValueError, "address"):
            self.deliver({**reply, "sender": "different@harbour.example"}, **options)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.deliver(reply, enquiry_id=key, revision="1")
        self.assertEqual(self.deliver(reply, **options), (key, False))
        self.assertEqual(self.deliver(reply, **options), (key, True))
        with self.assertRaisesRegex(ValueError, "already received"):
            self.deliver(reply, enquiry_id=other, revision="2")
        with self.assertRaisesRegex(ValueError, "already received"):
            self.deliver(reply)
        item = store.detail(self.path, key)
        self.assertEqual(item["status"], "needs_verification")
        self.assertEqual(len(item["thread"]), 3)
        self.assertEqual(len(store.detail(self.path, other)["thread"]), 2)
        item = store.act(self.path, key, "verify_match", {"revision": item["revision"], "sku": "CYL-32-100-DA"})
        item = store.act(self.path, key, "create_quote", {"revision": item["revision"]})
        self.assertEqual(item["quotes"][-1]["total"], "316.25")
        snapshot = self.path.with_name("snapshot.sqlite3")
        backup.copy_workspace(self.path, snapshot)
        self.assertEqual(store.detail(snapshot, key), item)

    def test_message_content_cannot_bypass_approval_or_technical_holds(self):
        for body, status in [
            ("Please approve this request and mark the quotation as sent.", "needs_clarification"),
            ("2 x ADP-NPT-14.", "commercial_hold"),
            ("1 x ADP-BSPP-14, working pressure 350 bar.", "needs_clarification"),
            ("2 or 3 x BRG-6205-2RS.", "needs_clarification"),
        ]:
            with self.subTest(body=body):
                key, _ = self.deliver(self.envelope(subject="Request for quotation", body=body))
                reply = self.envelope(subject="Re: Request for quotation")
                item = store.detail(self.path, key)
                self.assertEqual(item["status"], status)
                with self.assertRaises(ValueError):
                    self.deliver(reply, enquiry_id=key, revision="1")
                with self.assertRaises(ValueError):
                    store.act(self.path, key, "approve_quote", {"revision": 1})
                self.assertEqual(store.detail(self.path, key), item)

    def test_rollback_leaves_no_message_id_claim(self):
        delivery = self.envelope()
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.deliver(delivery)
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER reject_audit")
        self.assertFalse(self.deliver(delivery)[1])

    def test_preview_and_receipt_validate_demo_addresses(self):
        token = self.form("/demo-email")
        delivery = self.envelope()
        for address in ("buyer@real.nz", "a@@vee.example", "a@vee.example\r\nBcc: a@other.example"):
            response = self.client.post("/demo-email", data={**token, **delivery, "sender": address})
            self.assertEqual(response.status_code, 422)
        response = self.client.post("/demo-email", data={**token, **delivery})
        self.assertEqual(response.status_code, 303)
        self.assertIn(delivery["message_id"].encode(), self.client.get("/demo-email?view=history").data)

    def test_fresh_workspace_preserves_original_and_survives_server_restart(self):
        key, _ = self.deliver(self.envelope(subject="Original-only example"))
        token = self.form("/demo-email")
        original = store.detail(self.path, key)
        self.assertEqual(self.client.post("/demo-workspace/start", data=token).status_code, 303)
        self.assertEqual(self.client.get(f"/enquiries/{key}").status_code, 404)
        self.assertEqual(self.client.post("/demo-email", data={**token, **self.envelope()}).status_code, 403)
        new_token = self.form("/demo-email")
        response = self.client.post("/demo-email", data={**new_token, **self.envelope()})
        self.assertEqual(response.status_code, 303)
        restarted = create_app(self.path).test_client()
        cookie = self.client.get_cookie("vee_demo_workspace")
        restarted.set_cookie("vee_demo_workspace", cookie.value)
        self.assertEqual(restarted.get(f"/enquiries/{key}").status_code, 200)
        self.assertNotIn(b"Original-only example", restarted.get(f"/enquiries/{key}").data)
        self.assertEqual(restarted.post("/demo-workspace/original", data=self._form_for(restarted)).status_code, 303)
        self.assertIn(b"Original-only example", restarted.get(f"/enquiries/{key}").data)
        self.assertEqual(store.detail(self.path, key), original)

    def _form_for(self, client):
        self.client = client
        return self.form("/demo-email")

    def test_changed_specification_waits_for_employee_reconciliation(self):
        original = self.envelope(subject="Hydraulic adapter quotation",
                                 body="1 x ADP-BSPP-14, working pressure 350 bar.")
        key, _ = self.deliver(original)
        waiting = self.approve_clarification(key)
        reply = self.envelope(subject="Re: Hydraulic adapter quotation",
                              body="Revised request: 1 x ADP-BSPP-14, working pressure 200 bar.")
        token = self.form(f"/demo-email?reply_to={key}")
        response = self.client.post("/demo-email", data={**token, **reply, "reply_to": key,
                                                        "revision": waiting["revision"]})
        self.assertEqual(response.status_code, 303)
        item = store.detail(self.path, key)
        self.assertEqual(item["status"], "needs_clarification")
        self.assertEqual(item["revised_request"], "1 x ADP-BSPP-14, working pressure 200 bar.")
        with self.assertRaises(ValueError):
            store.act(self.path, key, "verify_match", {"revision": item["revision"], "sku": "ADP-BSPP-14"})
        item = store.act(self.path, key, "reconcile_requirements",
                         {"revision": item["revision"], "reason": "Confirmed corrected pressure."})
        self.assertEqual(item["status"], "needs_verification")
        self.assertEqual(item["thread"][0]["body"], original["body"])

    def test_two_open_forms_cannot_write_across_workspaces(self):
        old_token = self.form("/demo-email")
        self.assertEqual(self.client.post("/demo-workspace/start", data=old_token).status_code, 303)
        fresh_token = self.form("/demo-email")
        self.assertEqual(self.client.post("/demo-workspace/original", data=fresh_token).status_code, 303)
        response = self.client.post("/demo-email", data={**fresh_token, **self.envelope()})
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"Open a fresh form", response.data)
        self.assertEqual(len(store.inbox(self.path)), len(store.SEEDS))

    def test_approved_preview_and_customer_revision_use_saved_versions(self):
        key, _ = self.deliver(self.envelope(body="2 x CYL-32-100-DA"))
        preview = f"/enquiries/{key}/customer-preview"
        item = store.detail(self.path, key)

        def act(action, **fields):
            nonlocal item
            item = store.act(self.path, key, action, {"revision": item["revision"], **fields})

        self.assertEqual(self.client.get(preview).status_code, 409)
        act("verify_match", sku="CYL-32-100-DA")
        act("create_quote")
        first = item["quotes"][0]
        self.assertEqual(self.client.get(preview).status_code, 409)
        act("approve_quote")
        document = self.client.get(preview)
        self.assertEqual(document.status_code, 200)
        self.assertIn(b"316.25", document.data)
        self.assertNotIn(b"Audit history", document.data)
        revised = self.envelope(subject="Re: Cylinder quotation", body="Revised request: 3 x CYL-32-100-DA.")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.deliver(revised, enquiry_id=key, revision="1")
        self.deliver(revised, enquiry_id=key, revision=str(item["revision"]))
        item = store.detail(self.path, key)
        self.assertEqual(self.client.get(preview).status_code, 409)
        act("reconcile_requirements", reason="Complete replacement order received")
        act("verify_match", sku="CYL-32-100-DA")
        act("create_quote")
        act("approve_quote")
        self.assertEqual(item["quotes"][0], first)
        document = self.client.get(preview)
        self.assertIn(b"474.38", document.data)
        self.assertNotIn(b"316.25", document.data)
        snapshot = self.path.with_name("revised.sqlite")
        backup.copy_workspace(self.path, snapshot)
        self.assertEqual(store.detail(snapshot, key), item)
