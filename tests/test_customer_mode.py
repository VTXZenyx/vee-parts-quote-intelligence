import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import uuid4

from vee import store
from vee.web import create_app


class CustomerModeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "original.sqlite3"
        self.client = create_app(self.path).test_client()

    def listing(self, account):
        response = self.client.get("/customer-preview", query_string={"account": account})
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def example_links(self, html):
        return [unescape(url) for url in re.findall(r'href="(/customer-preview/examples/[^"]+)"', html)]

    def test_initial_examples_are_account_scoped_and_leave_original_intact(self):
        original = store.inbox(self.path)
        self.assertEqual({row["id"] for row in original}, {seed[0] for seed in store.SEEDS})
        self.assertFalse(any(row["quotes"] for row in original))
        for account in store.CUSTOMERS:
            with self.subTest(account=account):
                listing = self.listing(account)
                self.assertIn("Presenter-controlled local demonstration", listing)
                examples = self.example_links(listing)
                self.assertTrue(examples)
                for url in examples:
                    document = self.client.get(url)
                    self.assertEqual(document.status_code, 200)
                    self.assertIn(f"<dd>{account}</dd>".encode(), document.data)
                    self.assertIn(b"Stock is unreserved", document.data)
                    other = next(other for other in store.CUSTOMERS if other != account)
                    cross_account = url.split("?")[0] + "?" + urlencode({"account": other})
                    self.assertEqual(self.client.get(cross_account).status_code, 404)
        self.assertEqual(store.inbox(self.path), original)
        self.assertEqual(self.client.get("/customer-preview?account=Unknown").status_code, 404)

    def test_prepared_partial_and_contract_quotes_use_stored_net_tax_and_total(self):
        kauri = self.example_links(self.listing("Kauri Engineering"))
        documents = [self.client.get(url).get_data(as_text=True) for url in kauri]
        partial, = [doc for doc in documents if "BRG-6203-ZZ" in doc]
        for value in ("4 units outstanding", "9.80", "58.80", "8.82", "67.62", "GST (15%)"):
            self.assertIn(value, partial)
        harbour, = self.example_links(self.listing("Harbour Packaging"))
        document = self.client.get(harbour).get_data(as_text=True)
        for value in ("137.50", "275.00", "41.25", "316.25"):
            self.assertIn(value, document)
        self.assertIn("Prepared example", document)
        restarted = create_app(self.path).test_client()
        self.assertEqual(restarted.get(harbour).data, self.client.get(harbour).data)

    def test_workspace_preview_rechecks_approval_revision_and_account(self):
        account = "Harbour Packaging"
        key, _ = store.receive_demo_email(self.path, str(uuid4()), account, "buyer@harbour.example",
                                          store.DEMO_RECIPIENT, "Cylinder quotation", "2 x CYL-32-100-DA")
        def act(action, **fields):
            return store.act(self.path, key, action,
                             {"revision": store.detail(self.path, key)["revision"], **fields})

        def document(version):
            return f"/customer-preview/workspace-original/{key}/{version}?" + urlencode({"account": account})

        act("verify_match", sku="CYL-32-100-DA")
        act("create_quote")
        for decision in ("draft", "rejected"):
            if decision == "rejected":
                act("reject_quote", reason="Review the quantity.")
            self.assertEqual(self.client.get(document(1)).status_code, 409)
            self.assertNotIn(f"/workspace-original/{key}/1", self.listing(account))
        act("edit_quote", quantity="1")
        approved = act("approve_quote")
        unavailable = self.client.get(document(1))
        self.assertEqual(unavailable.status_code, 409)
        self.assertIn(b"Quotation superseded", unavailable.data)
        latest = self.client.get(document(2))
        self.assertEqual(latest.status_code, 200)
        self.assertIn(b"158.13", latest.data)
        self.assertIn(b"1 unit outstanding", latest.data)
        self.assertIn(f"/workspace-original/{key}/2", self.listing(account))
        self.assertEqual(self.client.get(document(2).replace("Harbour+Packaging", "Kauri+Engineering")).status_code, 404)
        self.assertNotIn(f"/workspace-original/{key}/2", self.listing("Kauri Engineering"))
        store.receive_demo_email(self.path, str(uuid4()), account, "buyer@harbour.example", store.DEMO_RECIPIENT,
                                 "Re: Cylinder quotation", "Revised request: 3 x CYL-32-100-DA.",
                                 enquiry_id=key, revision=approved["revision"])
        withdrawn = self.client.get(document(2))
        self.assertEqual(withdrawn.status_code, 409)
        self.assertIn(b"Approval withdrawn", withdrawn.data)
        self.assertNotIn(f"/workspace-original/{key}/2", self.listing(account))

    def test_employee_quantity_increase_is_disclosed_in_the_approved_document(self):
        key = "ENQ-1041"
        item = store.detail(self.path, key)
        for action, fields in [("verify_match", {"sku": "BRG-6205-2RS"}), ("create_quote", {}),
                               ("edit_quote", {"quantity": "5"}), ("approve_quote", {})]:
            item = store.act(self.path, key, action, {"revision": item["revision"], **fields})
        snapshot = item["quotes"][-1]
        self.assertEqual((snapshot["lines"][0]["requested_quantity"], snapshot["lines"][0]["quantity"]), (4, 5))
        notice = b"Employee increased the quoted quantity above the customer request"
        self.assertIn(notice, self.client.get(f"/enquiries/{key}").data)
        url = f"/customer-preview/workspace-original/{key}/2?account=Kauri+Engineering"
        doc = self.client.get(url)
        self.assertEqual(doc.status_code, 200)
        self.assertIn(notice, doc.data)
        self.assertIn(b"Customer confirmation is outstanding", doc.data)
        self.assertEqual(store.detail(self.path, key)["quotes"][-1], snapshot)

    def test_original_bookmark_cannot_resolve_against_another_workspace(self):
        key = "ENQ-1041"

        def approve(path):
            for action, fields in [("verify_match", {"sku": "BRG-6205-2RS"}), ("create_quote", {}),
                                   ("approve_quote", {})]:
                store.act(path, key, action, {"revision": store.detail(path, key)["revision"], **fields})

        approve(self.path)
        url = f"/customer-preview/workspace-original/{key}/1?account=Kauri+Engineering"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.get("/")
        with self.client.session_transaction() as session:
            token = session["csrf"]
        self.client.post("/demo-workspace/start", data={"csrf": token})
        workspace = self.client.get_cookie("vee_demo_workspace").value
        approve(self.path.parent / f"{self.path.name}.demos" / f"{workspace}.sqlite3")
        self.assertEqual(self.client.get(url).status_code, 404)
        isolated = url.replace("workspace-original", "workspace-" + workspace)
        self.assertEqual(self.client.get(isolated).status_code, 200)

    def test_interrupted_and_concurrent_sample_preparation_publishes_only_complete_examples(self):
        from vee.customer import prepare_examples

        dest = self.path.with_name("examples.sqlite3")
        with patch("vee.customer.store.act", side_effect=ValueError("interrupted")), self.assertRaises(ValueError):
            prepare_examples(dest)
        self.assertFalse(dest.exists())
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(prepare_examples, [dest, dest]))
        approved = [item for item in store.inbox(dest) if item["status"] == "approved"]
        self.assertEqual({item["customer"] for item in approved}, set(store.CUSTOMERS))
        for item in approved:
            actions = [row["action"] for row in item["history"]]
            self.assertIn(actions[-3], ("verify_match", "verify_partial"))
            self.assertEqual(actions[-2:], ["create_quote", "approve_quote"])
