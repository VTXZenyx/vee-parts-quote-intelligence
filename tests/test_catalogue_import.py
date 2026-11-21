import csv
import io
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from vee import backup, store
from vee.provider_mail import FIXTURES, ingest

HEADER = ("sku", "family", "name", "specs", "status", "stock", "price_nzd")
SPECS = "bore=25 mm;outside diameter=52 mm;width=15 mm;closure=rubber seals"


def bearing(sku="BRG-IMPORT-TEST", **changes):
    return {
        "sku": sku,
        "family": "Bearing",
        "name": "Synthetic test bearing",
        "specs": SPECS,
        "status": "active",
        "stock": "7",
        "price_nzd": "3.25",
    } | changes


def csv_file(*rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, HEADER)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


class CatalogueImportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "workspace.sqlite3"
        store.init(self.path)
        from vee import catalogue_import

        self.service = catalogue_import

    def receive(self, text, path=None, customer="Kauri Engineering"):
        path = path or self.path
        key = store.receive(path, str(uuid4()), customer, "RFQ", text)
        return store.detail(path, key)

    def act(self, item, action, **fields):
        return store.act(
            self.path, item["id"], action, {"revision": item["revision"], **fields}
        )

    def publish(self, *rows):
        stage = self.service.stage(self.path, csv_file(*rows))
        return self.service.activate(self.path, stage["id"], confirmed=True)

    def test_preview_is_nonpublishing_and_shows_explicit_patch_changes(self):
        raw = csv_file(
            bearing(),
            bearing("BRG-6205-2RS", price_nzd="8.50"),
            bearing("BRG-6205-ZZ", status="discontinued"),
        )
        plan = self.service.stage(self.path, raw)
        self.assertEqual(
            plan["counts"], {"added": 1, "updated": 1, "retired": 1, "unchanged": 0}
        )
        self.assertEqual(plan["changes"][1]["before"]["price_nzd"], "12.75")
        self.assertEqual(plan["changes"][1]["after"]["price_nzd"], "8.50")
        self.assertEqual(self.service.stage(self.path, raw)["id"], plan["id"])
        self.assertEqual(self.service.preview(self.path, plan["id"]), plan)
        for value in (False, "yes", 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.service.activate(self.path, plan["id"], confirmed=value)
        self.assertEqual(
            self.receive("1 x BRG-IMPORT-TEST")["status"], "needs_clarification"
        )
        self.assertEqual(
            self.service.activate(self.path, plan["id"], confirmed=True), 1
        )
        with self.assertRaises(ValueError):
            self.service.stage(self.path, raw)
        with self.assertRaises(ValueError):
            self.service.activate(self.path, plan["id"], confirmed=True)
        store.init(self.path)
        item = self.receive("2 x BRG-IMPORT-TEST")
        self.assertEqual(item["status"], "needs_verification")
        draft = self.act(
            self.act(item, "verify_match", sku="BRG-IMPORT-TEST"), "create_quote"
        )
        self.assertEqual(draft["quotes"][0]["total"], "7.48")
        self.assertEqual(
            self.receive("1 x BRG-6205-ZZ")["status"], "needs_clarification"
        )
        self.assertEqual(self.receive("1 x BLT-M12-80")["status"], "needs_verification")

    def test_invalid_files_never_change_state_or_publish_partial_records(self):
        raw = csv_file(bearing())
        for case in (
            b"",
            b"\xff",
            raw * 1000,
            raw.replace(b"sku,", b"sku,sku,"),
            raw.replace(b"active", b"active,extra"),
            raw.replace(b"active", b'"unfinished'),
            raw.replace(b"active", b"ac\x00tive"),
            csv_file(bearing(), bearing()),
            csv_file(*(bearing(f"BRG-TEST-{i}") for i in range(101))),
            *(
                csv_file(bearing(), bearing("BRG-NEXT", **bad))
                for bad in (
                    {"family": "Fastener"},
                    {"name": "=HYPERLINK(1)"},
                    {"stock": "-1"},
                    {"stock": "1.5"},
                    {"price_nzd": "NaN"},
                    {"price_nzd": "1e2"},
                    {"price_nzd": "12.123"},
                    {"status": "retired"},
                    {"status": "discontinued"},
                    {"specs": SPECS.replace("25 mm", "-1 mm")},
                    {"specs": SPECS + ";bore=20 mm"},
                    {"specs": SPECS.replace("52 mm", "12 mm")},
                    {"specs": "bore=25 mm"},
                )
            ),
            csv_file(bearing("brg-unknown")),
        ):
            with self.subTest(case=case[:180]), self.assertRaises(ValueError):
                self.service.stage(self.path, case)
        self.assertEqual(self.service.active_revision(self.path), 0)

    def test_unknowns_and_account_agreements_are_preserved(self):
        self.publish(
            bearing(stock="", price_nzd=""), bearing("BRG-6205-2RS", price_nzd="20")
        )
        missing = self.receive("1 x BRG-IMPORT-TEST")
        self.assertEqual(missing["status"], "commercial_hold")
        candidate = missing["candidates"][0]
        self.assertIsNone(candidate["stock"])
        self.assertIsNone(candidate["unit_price"])
        for sku, price in [("BRG-IMPORT-TEST", None), ("BRG-6205-2RS", "10.00")]:
            item = self.receive("1 x " + sku, customer="Contract Only Engineering")
            self.assertEqual(item["candidates"][0]["unit_price"], price)

    def test_activation_preserves_approved_snapshots_and_blocks_stale_drafts_and_verification(
        self,
    ):
        untouched = self.receive("2 x BRG-6205-ZZ")
        confirmed = self.act(
            self.act(
                self.act(
                    self.receive("4 x BRG-6205-2RS"), "verify_match", sku="BRG-6205-2RS"
                ),
                "create_quote",
            ),
            "approve_quote",
        )
        pending = self.receive("2 x BRG-6205-2RS")
        draft = self.act(
            self.act(pending, "verify_match", sku="BRG-6205-2RS"), "create_quote"
        )
        other = self.receive("2 x BRG-6205-2RS")
        self.publish(bearing("BRG-6205-2RS", price_nzd="2.00"))
        with self.assertRaises(ValueError):
            self.act(draft, "approve_quote")
        with self.assertRaises(ValueError):
            self.act(other, "verify_match", sku="BRG-6205-2RS")
        self.assertEqual(store.detail(self.path, confirmed["id"]), confirmed)
        fresh = self.act(
            self.act(
                self.act(draft, "refresh_evidence"), "verify_match", sku="BRG-6205-2RS"
            ),
            "create_quote",
        )
        self.assertEqual([q["total"] for q in fresh["quotes"]], ["29.33", "4.60"])
        self.assertEqual(
            self.act(untouched, "verify_match", sku="BRG-6205-ZZ")["status"], "verified"
        )

    def test_previously_unique_dimension_match_cannot_survive_added_equivalent(self):
        item = self.receive(
            "1 bearing, bore 25 mm, outside diameter 52 mm, width 15 mm, rubber seals"
        )
        self.assertEqual(item["status"], "needs_verification")
        self.publish(bearing())
        with self.assertRaises(ValueError):
            self.act(item, "verify_match", sku="BRG-6205-2RS")
        self.assertEqual(
            self.act(item, "refresh_evidence")["status"], "needs_clarification"
        )

    def test_stale_stage_concurrent_activation_and_workspace_isolation(self):
        other = self.path.with_name("other.sqlite3")
        store.init(other)
        plans = [
            self.service.stage(self.path, csv_file(bearing(sku)))
            for sku in ("BRG-TEST-A", "BRG-TEST-B")
        ]
        with self.assertRaises(KeyError):
            self.service.activate(other, plans[0]["id"], confirmed=True)

        def activate(plan):
            try:
                return self.service.activate(self.path, plan["id"], confirmed=True)
            except ValueError:
                return "stale"

        with ThreadPoolExecutor(2) as pool:
            self.assertCountEqual(pool.map(activate, plans), [1, "stale"])
        self.assertEqual(self.service.active_revision(other), 0)
        for sku in ("BRG-TEST-A", "BRG-TEST-B"):
            self.assertEqual(
                self.receive("1 x " + sku, other)["status"], "needs_clarification"
            )
        self.assertEqual(
            sum(
                self.receive("1 x BRG-TEST-" + s)["status"] == "needs_verification"
                for s in "AB"
            ),
            1,
        )

    def test_activation_database_failure_rolls_back_and_staged_copy_can_be_restored(
        self,
    ):
        self.publish(bearing())
        plan = self.service.stage(self.path, csv_file(bearing("BRG-RETRY")))
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TRIGGER fail BEFORE UPDATE ON catalogue_imports BEGIN SELECT RAISE(ABORT,'fixture'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.activate(self.path, plan["id"], confirmed=True)
        self.assertEqual(self.service.active_revision(self.path), 1)
        self.assertEqual(self.receive("1 x BRG-RETRY")["status"], "needs_clarification")
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER fail")
        restored = self.path.with_suffix(".restored")
        backup.copy_workspace(self.path, restored)
        self.assertEqual(self.service.preview(restored, plan["id"]), plan)
        self.assertEqual(self.service.activate(restored, plan["id"], confirmed=True), 2)
        self.assertEqual(
            self.receive("1 x BRG-RETRY", restored)["status"], "needs_verification"
        )
        with sqlite3.connect(restored) as db:
            db.execute(
                "UPDATE catalogue_imports SET payload=x'00' WHERE activated_revision=1"
            )
        with self.assertRaises(ValueError):
            backup.copy_workspace(restored, self.path.with_suffix(".invalid"))

    def test_provider_ingestion_reads_published_workspace_revision(self):
        self.publish(bearing("BRG-6205-2RS", status="discontinued"))
        fixture = FIXTURES["graph-bearing"]
        receipt = ingest(self.path, fixture["provider"], fixture["message"])
        item = store.detail(self.path, receipt["enquiry_id"])
        self.assertEqual(item["status"], "needs_clarification")
        self.assertTrue(item["candidates"][0]["discontinued"])

    def test_findings_use_enquirys_saved_catalogue_and_account_evidence(self):
        from vee import findings

        self.publish(bearing())
        item = self.receive("1 x BRG-IMPORT-TEST", customer="Contract Only Engineering")
        # A later retirement must not change the finding selected on the old enquiry form.
        self.publish(bearing(status="discontinued"))
        for mode in ("mock", "deterministic"):
            findings.process(
                self.path,
                item["id"],
                {"revision": str(item["revision"]), "source": "1", "mode": mode},
            )
            item = store.detail(self.path, item["id"])
            _, saved = findings.displayed(self.path, item, "1")
            values = [row["value"] for row in saved["findings"]]
            self.assertIn("No authorised price is available for this account.", values)
            self.assertFalse(any("Discontinued catalogue" in value for value in values))

    def test_missing_reference_can_refresh_after_import_without_fabricated_customer_reply(
        self,
    ):
        item = self.receive("1 x BRG-IMPORT-TEST")
        rejected = self.act(
            self.receive("1 x BRG-6205-ZZ"), "reject_match", reason="Check nameplate."
        )
        self.publish(bearing())
        self.assertTrue(
            store.detail(self.path, item["id"]).get("catalogue_refresh_available")
        )
        ready = self.act(item, "refresh_evidence")
        self.assertEqual(ready["status"], "needs_verification")
        self.assertEqual(ready["thread"], item["thread"])
        self.assertFalse(
            store.detail(self.path, rejected["id"]).get("catalogue_refresh_available")
        )
        with self.assertRaises(ValueError):
            self.act(rejected, "refresh_evidence")

    def test_recovery_rejects_catalogue_evidence_with_missing_published_history(self):
        self.publish(bearing())
        item = self.receive("1 x BRG-IMPORT-TEST")
        quote = self.act(
            self.act(item, "verify_match", sku="BRG-IMPORT-TEST"), "create_quote"
        )
        for statement in (
            "DELETE FROM catalogue_imports",
            "UPDATE quotes SET snapshot=json_set(snapshot,'$.catalogue_revision',19)",
        ):
            with self.subTest(statement=statement):
                copy = self.path.with_suffix(".damaged" + statement.split()[0])
                backup.copy_workspace(self.path, copy)
                with sqlite3.connect(copy) as db:
                    db.execute(statement)
                with self.assertRaisesRegex(ValueError, "catalogue revision"):
                    backup.copy_workspace(copy, copy.with_suffix(".restore"))
        self.assertEqual(quote["quotes"][0]["catalogue_revision"], 1)
