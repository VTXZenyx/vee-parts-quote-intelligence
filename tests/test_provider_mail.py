import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from vee import store
from vee.backup import copy_workspace
from vee.provider_mail import FIXTURES, deliveries, ingest, retry


class ProviderMailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "db"
        store.init(self.path)

    def receive(self, key):
        fixture = FIXTURES[key]
        return ingest(self.path, fixture["provider"], fixture["message"])

    def test_out_of_order_recovery_duplicate_and_restore(self):
        held = self.receive("gmail-details")
        self.assertEqual(held["status"], "held")
        root = self.receive("gmail-cylinder")
        self.assertEqual(self.receive("gmail-details")["status"], "duplicate")
        accepted = retry(self.path, held["id"])
        self.assertEqual(
            (accepted["status"], accepted["enquiry_id"]),
            ("accepted", root["enquiry_id"]),
        )
        before = store.detail(self.path, root["enquiry_id"])
        self.assertEqual(before["status"], "needs_verification")
        self.assertEqual(self.receive("gmail-details")["status"], "duplicate")
        self.assertEqual(before, store.detail(self.path, root["enquiry_id"]))
        self.assertEqual(len(deliveries(self.path)), 2)
        backup = self.path.with_name("backup")
        copy_workspace(self.path, backup)
        self.assertEqual(deliveries(self.path), deliveries(backup))

    def test_graph_same_subject_is_independent_conflicts_and_forward_held(self):
        first = self.receive("gmail-cylinder")
        second = self.receive("graph-cylinder")
        self.assertNotEqual(first["enquiry_id"], second["enquiry_id"])
        for key in ("graph-forward", "gmail-collision", "gmail-new-in-thread"):
            with self.subTest(key=key):
                self.assertEqual(self.receive(key)["status"], "held")
        self.assertEqual(len(store.inbox(self.path)), 8)

    def test_changed_request_reopens_approved_quote(self):
        key = self.receive("graph-bearing")["enquiry_id"]

        def act(action, **fields):
            item = store.detail(self.path, key)
            return store.act(
                self.path, key, action, {"revision": item["revision"], **fields}
            )

        act("verify_match", sku="BRG-6205-2RS")
        act("create_quote")
        original = act("approve_quote")
        changed = self.receive("graph-revision")
        self.assertEqual(changed["enquiry_id"], key)
        item = store.detail(self.path, key)
        self.assertEqual(item["status"], "needs_clarification")
        self.assertEqual(item["selected_skus"], [])
        self.assertEqual(original["quotes"], item["quotes"])
        with self.assertRaises(ValueError):
            act("approve_quote")
        copy_workspace(self.path, self.path.with_name("snapshot"))

    def test_changed_content_and_missing_id_rejected(self):
        fixture = FIXTURES["graph-bearing"]
        self.receive("graph-bearing")
        changed = copy.deepcopy(fixture["message"])
        changed["body"]["content"] = "Different"
        with self.assertRaisesRegex(ValueError, "different content"):
            ingest(self.path, "outlook", changed)
        del changed["id"]
        with self.assertRaises(ValueError):
            ingest(self.path, "outlook", changed)
        self.assertEqual(len(deliveries(self.path)), 1)

    def test_failed_receipt_insert_rolls_back_enquiry(self):
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TRIGGER fail BEFORE INSERT ON provider_mail BEGIN SELECT RAISE(ABORT,'fixture'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.receive("graph-bearing")
        self.assertEqual(len(store.inbox(self.path)), 6)
        self.assertEqual(deliveries(self.path), [])

    def test_backup_rejects_receipt_disagreeing_with_thread(self):
        self.receive("graph-bearing")
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE provider_mail SET enquiry_id='ENQ-1042'")
        with self.assertRaisesRegex(ValueError, "source history"):
            copy_workspace(self.path, self.path.with_name("broken"))

    def test_replies_in_sequence_and_stale_branch(self):
        key = self.receive("gmail-cylinder")["enquiry_id"]
        second = self.receive("gmail-second-reply")
        self.assertEqual(second["status"], "held")
        self.receive("gmail-details")
        self.assertEqual(retry(self.path, second["id"])["enquiry_id"], key)
        stale = copy.deepcopy(FIXTURES["gmail-details"]["message"])
        stale["id"] += "-branch"
        next(h for h in stale["payload"]["headers"] if h["name"] == "Message-ID")[
            "value"
        ] = "<branch@mail.example>"
        self.assertEqual(ingest(self.path, "gmail", stale)["status"], "held")
        self.assertEqual(len(store.detail(self.path, key)["thread"]), 3)

    def test_duplicate_in_parallel_has_one_workflow_effect(self):
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.receive, ["graph-bearing", "graph-bearing"]))
        self.assertCountEqual([r["status"] for r in results], ["duplicate", "accepted"])
        item = store.detail(self.path, results[0]["enquiry_id"])
        self.assertEqual((len(item["thread"]), len(item["history"])), (1, 1))

    def test_early_child_is_parent_of_next_reply_even_when_receipt_ids_sort_differently(
        self,
    ):
        child = self.receive("gmail-details")
        root = self.receive("gmail-cylinder")
        self.assertEqual(retry(self.path, child["id"])["status"], "accepted")
        grandchild = self.receive("gmail-second-reply")
        self.assertEqual(
            (grandchild["status"], grandchild["enquiry_id"]),
            ("accepted", root["enquiry_id"]),
        )

    def test_explicit_separate_request_with_valid_reply_headers_held(self):
        self.receive("graph-bearing")
        changed = copy.deepcopy(FIXTURES["graph-revision"]["message"])
        changed["body"]["content"] = (
            "Separate enquiry: please quote 3 pneumatic cylinders."
        )
        self.assertEqual(ingest(self.path, "outlook", changed)["status"], "held")

    def test_restore_v2_schema_and_upgrade_before_new_receipt(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE catalogue_imports")
            db.execute("DROP TABLE provider_mail")
            db.execute("PRAGMA user_version=2")
        restored = self.path.with_name("v2-restored")
        copy_workspace(self.path, restored)
        before = store.inbox(restored)
        store.init(restored)
        self.assertEqual(before, store.inbox(restored))
        fixture = FIXTURES["gmail-cylinder"]
        key = ingest(restored, fixture["provider"], fixture["message"])["enquiry_id"]
        after = self.path.with_name("v3-restored")
        copy_workspace(restored, after)
        preserved = store.detail(after, key)
        self.assertEqual(
            ingest(after, fixture["provider"], fixture["message"])["status"],
            "duplicate",
        )
        self.assertEqual(store.detail(after, key), preserved)

    def test_matched_provider_reply_cannot_drop_a_subject_only_pressure_requirement(
        self,
    ):
        fixture = copy.deepcopy(FIXTURES["graph-bearing"]["message"])
        fixture.update(subject="Adapter quotation")
        fixture["body"]["content"] = "1 x ADP-BSPP-14."
        root = ingest(self.path, "outlook", fixture)
        self.assertEqual(
            store.detail(self.path, root["enquiry_id"])["status"], "needs_verification"
        )
        child = copy.deepcopy(FIXTURES["graph-revision"]["message"])
        child["subject"] = "Working pressure 350 bar"
        child["body"]["content"] = "Thanks."
        self.assertEqual(ingest(self.path, "outlook", child)["status"], "accepted")
        item = store.detail(self.path, root["enquiry_id"])
        self.assertEqual(item["status"], "needs_clarification")
        self.assertTrue(
            any(
                "changed email subject" in issue
                for line in item["extraction"]["lines"]
                for issue in line["issues"]
            )
        )
