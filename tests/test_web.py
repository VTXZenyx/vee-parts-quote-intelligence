import tempfile
import unittest
from pathlib import Path

from vee.web import create_app


class WorkspaceRoutes(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "test.sqlite3"
        self.app = create_app(self.database)
        self.client = self.app.test_client()

    def test_dashboard_search_and_detail(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn(b"ENQ-1042", self.client.get("/").data)
        self.assertNotIn(b"ENQ-1042", self.client.get("/?q=zzzz-no-results").data)
        self.assertEqual(self.client.get("/enquiries/ENQ-1042").status_code, 200)
        self.assertEqual(self.client.get("/enquiries/UNKNOWN").status_code, 404)

    def test_cross_site_and_missing_tokens_denied(self):
        self.client.get("/")
        url = "/enquiries/ENQ-1042/actions"
        self.assertEqual(self.client.post(url).status_code, 403)
        with self.client.session_transaction() as session:
            csrf = session["csrf"]
        self.assertEqual(self.client.post(url, data={"csrf": csrf},
                         headers={"Origin": "https://elsewhere.example"}).status_code, 403)
        self.assertEqual(self.client.get("/", headers={"Host": "evil.example"}).status_code, 400)

    def test_out_of_sequence_and_stale_posts_show_errors_and_preserve_state(self):
        from vee import store

        database = self.database
        page = "/enquiries/ENQ-1042"
        self.client.get(page)
        with self.client.session_transaction() as session:
            csrf = session["csrf"]
        initial = store.detail(database, "ENQ-1042")

        def submit(action, **fields):
            return self.client.post(page + "/actions", follow_redirects=True, data={
                "action": action, "revision": initial["revision"], "csrf": csrf, **fields,
            })

        self.assertIn(b"unavailable", submit("approve_quote").data)
        self.assertEqual(initial, store.detail(database, "ENQ-1042"))
        self.assertIn(b"Changes saved", submit("save_clarification", body="Please confirm the mount.").data)
        self.assertIn(b"has changed", submit("approve_clarification").data)
        saved = store.detail(database, "ENQ-1042")
        self.assertEqual(saved["revision"], initial["revision"] + 1)
        self.assertEqual(saved["status"], "needs_clarification")

    def test_failed_database_write_explains_recovery_and_keeps_state(self):
        import sqlite3

        from vee import store

        key = "ENQ-1042"
        self.client.get("/")
        with self.client.session_transaction() as session:
            token = session["csrf"]
        original = store.detail(self.database, key)
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TRIGGER fail_write BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'audit failure'); END")
        result = self.client.post(f"/enquiries/{key}/actions", data={
            "csrf": token, "revision": original["revision"], "action": "approve_clarification",
        })
        self.assertEqual(result.status_code, 503)
        self.assertIn(b"Reload the enquiry", result.data)
        self.assertEqual(store.detail(self.database, key), original)

    def test_oversized_message_offers_recovery_and_preserves_enquiries(self):
        from vee import store

        self.client.get("/")
        with self.client.session_transaction() as session:
            token = session["csrf"]
        before = store.inbox(self.database)
        response = self.client.post("/enquiries/new", data={"csrf": token, "body": "a" * 33000})
        self.assertEqual(response.status_code, 413)
        self.assertIn(b"Shorten the message", response.data)
        self.assertEqual(store.inbox(self.database), before)
