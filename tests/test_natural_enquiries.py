import unittest

from evaluation import enquiries, run


class NaturalEnquiryEvaluation(unittest.TestCase):
    def test_catalogue_cases_score_candidates_quantities_and_holds(self):
        report = run.evaluate()
        self.assertEqual(report["failures"], [])
        self.assertGreater(report.get("labelled_quantities", 0), 0)
        self.assertGreater(report.get("labelled_suggestions", 0), 0)
        self.assertEqual(report["incorrect_quantity"], 0)
        self.assertEqual(report["incorrect_eligibility"], 0)
        self.assertEqual(
            set(report["natural_cases_by_category"]),
            {"bearings", "cylinders", "fasteners", "adapters", "mixed"},
        )
        for outcome in (
            "exact match", "exact attribute match", "candidate suggestion", "clarification",
            "technical block", "technical review", "commercial hold",
        ):
            with self.subTest(outcome=outcome):
                tally = report["natural_cases_by_outcome"][outcome]
                self.assertGreater(tally["cases"], 0)
                self.assertEqual(tally["passed"], tally["cases"])

    def test_message_findings_match_labels_in_both_offline_modes(self):
        for mode in ("deterministic", "mock"):
            with self.subTest(mode=mode):
                self.assertEqual(enquiries.evaluate(mode)["failures"], [])
