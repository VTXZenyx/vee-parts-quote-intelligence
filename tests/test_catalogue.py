import json
import unittest
from pathlib import Path
from unittest.mock import patch

from vee import catalogue as service

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "evaluation/cases.json").read_text()
)


class CatalogueTests(unittest.TestCase):
    def test_labelled_scenarios(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                account = case.get("account", "")
                analysis = service.analyse(case["text"], account)
                self.assertEqual(
                    [line["status"] for line in analysis["lines"]], case["status"]
                )
                self.assertEqual(
                    [line["sku"] for line in analysis["lines"]], case["skus"]
                )
                self.assertEqual(analysis["ready"], case["ready"])
                for key, expected in case.get("attributes", {}).items():
                    self.assertEqual(
                        analysis["lines"][0]["attributes"].get(key), expected
                    )
                for field in case.get("missing", []):
                    self.assertIn(field, " ".join(analysis["questions"]).lower())
                if not case["ready"]:
                    with self.assertRaises(ValueError):
                        service.build_quote(analysis, account)
                elif "total" in case:
                    self.assertEqual(
                        service.build_quote(analysis, account)["total"], case["total"]
                    )

    def test_edited_quantity_uses_authorised_price_and_recalculates_tax(self):
        analysis = service.analyse("1 x BRG-6205-2RS")
        quote = service.build_quote(analysis, quantities={"BRG-6205-2RS": 3})
        self.assertEqual(quote["lines"][0]["requested_quantity"], 1)
        self.assertEqual(
            (quote["subtotal"], quote["gst"], quote["total"]),
            ("38.25", "5.74", "43.99"),
        )

    def test_invalid_edits_and_combined_stock(self):
        analysis = service.analyse("2 x BRG-6205-2RS")
        for quantities in [
            {"BRG-6205-2RS": v} for v in (True, 0, -1, 1.5, 10000000)
        ] + [{"other": 2}]:
            with self.subTest(quantities=quantities), self.assertRaises(ValueError):
                service.build_quote(analysis, quantities=quantities)
        stock = next(
            i["stock"] for i in service.catalogue() if i["sku"] == "BRG-6205-2RS"
        )
        result = service.analyse(f"{stock} x BRG-6205-2RS\n1 x BRG-6205-2RS")
        self.assertFalse(result["ready"])
        with self.assertRaises(ValueError):
            service.build_quote(result)

    def test_catalogue_cannot_be_mutated_by_display_clients(self):
        first = service.catalogue()[0]
        first["specs"].clear()
        self.assertTrue(service.catalogue()[0]["specs"])

    def test_catalogue_lookup_and_matching_read_current_revision(self):
        from dataclasses import replace

        sku = "CYL-32-100-DA"
        revised = replace(service.BY_SKU[sku], discontinued=True)
        with patch.dict(service.BY_SKU, {sku: revised}):
            self.assertTrue(service.current_record(sku)["discontinued"])
            self.assertTrue(
                next(p for p in service.catalogue() if p["sku"] == sku)["discontinued"]
            )
            self.assertFalse(service.analyse("1 x " + sku)["ready"])
            self.assertFalse(service.analyse(CASES[2]["text"])["ready"])
        self.assertIsNone(service.current_record("unknown"))
