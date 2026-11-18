import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from vee import store


class SnapshotCLI(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.workspace = self.root / "local workspace.sqlite3"
        self.snapshot = self.root / "backup.sqlite3"
        self.restored = self.root / "recovered.sqlite3"
        store.init(self.workspace)

    def cli(self, verb, source, destination):
        return subprocess.run(
            [sys.executable, "-m", "vee.backup", verb, str(source), str(destination)],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_restores_quote_versions_audit_and_point_in_time_state(self):
        enquiry = "ENQ-1041"
        item = store.detail(self.workspace, enquiry)
        for action, fields in [
            ("verify_match", {"sku": "BRG-6205-2RS"}),
            ("create_quote", {}),
            ("edit_quote", {"quantity": "3", "notes": "Three requested."}),
        ]:
            item = store.act(
                self.workspace,
                enquiry,
                action,
                {"revision": item["revision"], **fields},
            )
        saved = self.cli("backup", self.workspace, self.snapshot)
        self.assertEqual(saved.returncode, 0, saved.stderr)
        store.act(
            self.workspace, enquiry, "approve_quote", {"revision": item["revision"]}
        )
        restored = self.cli("restore", self.snapshot, self.restored)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        recovered = store.detail(self.restored, enquiry)
        self.assertEqual(recovered, item)
        self.assertEqual(recovered["quotes"][-1]["total"], "43.99")
        self.assertEqual(recovered["history"][-1]["action"], "edit_quote")
        self.assertEqual(self.snapshot.stat().st_mode & 0o077, 0)

    def test_refuses_existing_destinations_and_orphan_sidecars(self):
        self.restored.write_bytes(b"existing destination")
        for verb in ("backup", "restore"):
            with self.subTest(verb=verb):
                self.assertNotEqual(
                    self.cli(verb, self.workspace, self.restored).returncode, 0
                )
                self.assertEqual(self.restored.read_bytes(), b"existing destination")
        dangling = self.root / "dangling.sqlite3"
        dangling.symlink_to(self.root / "unrelated")
        self.assertNotEqual(self.cli("restore", self.workspace, dangling).returncode, 0)
        self.assertTrue(dangling.is_symlink())
        sidecar = self.root / "backup.sqlite3-wal"
        sidecar.write_bytes(b"stale sidecar")
        self.assertNotEqual(
            self.cli("backup", self.workspace, self.snapshot).returncode, 0
        )
        self.assertFalse(self.snapshot.exists())

    def test_invalid_snapshot_is_never_published(self):
        missing = self.root / "missing.sqlite3"
        self.assertNotEqual(self.cli("backup", missing, self.restored).returncode, 0)
        self.assertFalse(missing.exists())
        self.assertFalse(self.restored.exists())
        self.snapshot.write_bytes(b"incomplete SQLite file")
        self.assertNotEqual(
            self.cli("restore", self.snapshot, self.restored).returncode, 0
        )
        self.assertFalse(self.restored.exists())
        with closing(sqlite3.connect(self.workspace)) as db:
            db.execute("DROP TABLE quotes")
            db.commit()
        self.assertNotEqual(
            self.cli("restore", self.workspace, self.restored).returncode, 0
        )
        self.assertFalse(self.restored.exists())

    def test_rejects_broken_audit_foreign_keys(self):
        with closing(sqlite3.connect(self.workspace)) as db:
            db.execute(
                "UPDATE events SET enquiry_id = 'missing' WHERE enquiry_id = 'ENQ-1041'"
            )
            db.commit()
        result = self.cli("backup", self.workspace, self.snapshot)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.snapshot.exists())

    def test_competing_backups_publish_one_complete_file(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [
                pool.submit(self.cli, "backup", self.workspace, self.snapshot)
                for _ in range(2)
            ]
            self.assertCountEqual(
                [attempt.result().returncode for attempt in attempts], [0, 1]
            )
        self.assertEqual(store.inbox(self.snapshot), store.inbox(self.workspace))

    def test_snapshot_includes_committed_wal_data(self):
        with closing(sqlite3.connect(self.workspace)) as keeper:
            self.assertEqual(
                keeper.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",)
            )
            keeper.execute("BEGIN")
            keeper.execute("SELECT count(*) FROM events").fetchone()
            item = store.detail(self.workspace, "ENQ-1041")
            saved = store.act(
                self.workspace,
                item["id"],
                "verify_match",
                {"revision": item["revision"], "sku": "BRG-6205-2RS"},
            )
            self.assertTrue(Path(str(self.workspace) + "-wal").exists())
            result = self.cli("backup", self.workspace, self.snapshot)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(store.detail(self.snapshot, saved["id"]), saved)

    def test_rejects_unreadable_workflow_state_and_incomplete_history(self):
        for damage in (
            "UPDATE enquiries SET state='invalid'",
            "DELETE FROM events WHERE enquiry_id='ENQ-1041'",
        ):
            with self.subTest(damage=damage):
                source = self.root / ("broken-" + damage.split()[0] + ".sqlite3")
                store.init(source)
                with closing(sqlite3.connect(source)) as db:
                    db.execute(damage)
                    db.commit()
                destination = source.with_suffix(".restore")
                self.assertNotEqual(
                    self.cli("restore", source, destination).returncode, 0
                )
                self.assertFalse(destination.exists())

    def test_rejects_false_approval_wrong_identity_and_corrupted_quote_values(self):
        enquiry = "ENQ-1041"
        item = store.detail(self.workspace, enquiry)
        for action, fields in (
            ("verify_match", {"sku": "BRG-6205-2RS"}),
            ("create_quote", {}),
        ):
            item = store.act(
                self.workspace,
                enquiry,
                action,
                {"revision": item["revision"], **fields},
            )
        for table, path, value in [
            ("enquiries", "$.status", "approved"),
            ("enquiries", "$.id", "ENQ-1000"),
            ("enquiries", "$.revision", 99),
            ("enquiries", "$.thread", 0),
            ("enquiries", "$.extraction.lines[0].attributes", 0),
            ("quotes", "$.version", 2),
            ("quotes", "$.lines[0]", "damaged"),
            ("quotes", "$.lines[0].quantity", 0),
            ("quotes", "$.lines[0].unit_price", "1.00"),
            ("quotes", "$.lines[0].line_total", "0.00"),
            ("quotes", "$.subtotal", "0.00"),
            ("quotes", "$.gst", "0.00"),
            ("quotes", "$.total", "0.00"),
        ]:
            with self.subTest(table=table, path=path):
                column, key = (
                    ("state", "id")
                    if table == "enquiries"
                    else ("snapshot", "enquiry_id")
                )
                with closing(sqlite3.connect(self.workspace)) as db:
                    original = db.execute(
                        f"SELECT {column} FROM {table} WHERE {key}=?", (enquiry,)
                    ).fetchone()[0]
                    db.execute(
                        f"UPDATE {table} SET {column}=json_set({column},?,?) WHERE {key}=?",
                        (path, value, enquiry),
                    )
                    db.commit()
                    dest = self.root / (table + "-" + path + ".sqlite3")
                    self.assertNotEqual(
                        self.cli("restore", self.workspace, dest).returncode, 0
                    )
                    self.assertFalse(dest.exists())
                    db.execute(
                        f"UPDATE {table} SET {column}=? WHERE {key}=?",
                        (original, enquiry),
                    )
                    db.commit()

    def test_can_restore_historic_rate_independently_of_current_price_book(self):
        item = store.detail(self.workspace, "ENQ-1041")
        for action, fields in (
            ("verify_match", {"sku": "BRG-6205-2RS"}),
            ("create_quote", {}),
        ):
            item = store.act(
                self.workspace,
                item["id"],
                action,
                {"revision": item["revision"], **fields},
            )
        quote = item["quotes"][0]
        quote["lines"][0].update(unit_price="8.75", line_total="35.00")
        quote.update(unit_price="8.75", subtotal="35.00", gst="5.25", total="40.25")
        with closing(sqlite3.connect(self.workspace)) as db:
            db.execute(
                "UPDATE quotes SET snapshot=? WHERE enquiry_id=?",
                (json.dumps(quote), item["id"]),
            )
            db.execute(
                "UPDATE events SET detail=replace(detail,'58.65','40.25') WHERE enquiry_id=?",
                (item["id"],),
            )
            db.commit()
        result = self.cli("restore", self.workspace, self.restored)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            store.detail(self.restored, item["id"])["quotes"][0]["total"], "40.25"
        )

    def test_rejects_missing_decision_fields_before_the_employee_opens_restored_work(
        self,
    ):
        for path in (
            "$.extraction.lines[0].sku",
            "$.extraction.lines[0].quantity",
            "$.extraction.lines[0].reference",
            "$.sample_reply",
        ):
            with (
                self.subTest(path=path),
                closing(sqlite3.connect(self.workspace)) as db,
            ):
                raw = db.execute(
                    "SELECT state FROM enquiries WHERE id='ENQ-1041'"
                ).fetchone()[0]
                db.execute(
                    "UPDATE enquiries SET state=json_remove(state,?) WHERE id='ENQ-1041'",
                    (path,),
                )
                db.commit()
                result = self.cli("restore", self.workspace, self.root / path)
                db.execute("UPDATE enquiries SET state=? WHERE id='ENQ-1041'", (raw,))
                db.commit()
                self.assertNotEqual(result.returncode, 0)
        item = store.detail(self.workspace, "ENQ-1041")
        fields = {"revision": item["revision"], "sku": "BRG-6205-2RS"}
        store.act(self.workspace, item["id"], "verify_match", fields)
        with closing(sqlite3.connect(self.workspace)) as db:
            db.execute(
                "UPDATE enquiries SET state=json_set(state,'$.selected_skus[0]','OTHER') WHERE id='ENQ-1041'"
            )
            db.commit()
        self.assertNotEqual(
            self.cli("backup", self.workspace, self.snapshot).returncode, 0
        )

    def test_approved_snapshot_must_match_historical_save_and_approval_amounts(self):
        item = store.detail(self.workspace, "ENQ-1041")
        for action, fields in (
            ("verify_match", {"sku": "BRG-6205-2RS"}),
            ("create_quote", {}),
            ("approve_quote", {}),
        ):
            item = store.act(
                self.workspace,
                item["id"],
                action,
                {"revision": item["revision"], **fields},
            )
        quote = item["quotes"][0]
        quote["lines"][0].update(quantity=2, line_total="25.50")
        quote.update(quantity=2, subtotal="25.50", gst="3.83", total="29.33")
        with closing(sqlite3.connect(self.workspace)) as db:
            db.execute(
                "UPDATE quotes SET snapshot=? WHERE enquiry_id=?",
                (json.dumps(quote), item["id"]),
            )
            db.commit()
            self.assertNotEqual(
                self.cli(
                    "restore", self.workspace, self.root / "conflicting-save"
                ).returncode,
                0,
            )
            db.execute(
                "UPDATE events SET detail=replace(detail,'58.65','29.33') WHERE enquiry_id=? AND action='create_quote'",
                (item["id"],),
            )
            db.commit()
            self.assertNotEqual(
                self.cli(
                    "restore", self.workspace, self.root / "conflicting-approval"
                ).returncode,
                0,
            )

    def test_recheck_after_approval_preserves_historical_quote_and_decision(self):
        item = store.detail(self.workspace, "ENQ-1041")
        for action, fields in (
            ("verify_match", {"sku": "BRG-6205-2RS"}),
            ("create_quote", {}),
            ("approve_quote", {}),
        ):
            item = store.act(
                self.workspace,
                item["id"],
                action,
                {"revision": item["revision"], **fields},
            )
        with closing(sqlite3.connect(self.workspace)) as db:
            state = json.loads(
                db.execute(
                    "SELECT state FROM enquiries WHERE id=?", (item["id"],)
                ).fetchone()[0]
            )
            state.update(
                revision=state["revision"] + 1,
                status="needs_verification",
                selected_skus=[],
                selected_sku=None,
            )
            db.execute(
                "UPDATE enquiries SET revision=?, state=? WHERE id=?",
                (state["revision"], json.dumps(state), item["id"]),
            )
            db.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?)",
                (
                    item["id"],
                    state["revision"],
                    item["history"][-1]["at"],
                    "System",
                    "recheck_requirements",
                    "Reopened for evidence review.",
                ),
            )
            db.commit()
        result = self.cli("restore", self.workspace, self.snapshot)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            store.detail(self.snapshot, item["id"])["status"], "needs_verification"
        )
