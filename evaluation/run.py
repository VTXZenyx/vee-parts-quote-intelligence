"""Run from the repository root with python -m evaluation.run."""

import json
from collections import Counter, defaultdict
from itertools import zip_longest
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from vee.catalogue import VERSION, analyse, build_quote


def evaluate() -> dict:
    cases = json.loads(Path(__file__).with_name("cases.json").read_text())
    counts: Counter[str] = Counter(false_verified_sku=0, unsafe_ready=0, incorrect_quantity=0, incorrect_eligibility=0)
    categories: Counter[str] = Counter()
    outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    timings = []
    failures = []
    for case in cases:
        account = case.get("account", "")
        start = perf_counter_ns()
        result = analyse(case["text"], account)
        reasons = []
        if result["ready"] != case["ready"]:
            counts["incorrect_eligibility"] += 1
            reasons.append("eligibility")
        counts["unsafe_ready"] += result["ready"] and not case["ready"]
        expected_status = case["status"]
        if [item["status"] for item in result["lines"]] != expected_status:
            reasons.append("disposition")
        for expected, item in zip_longest(case["skus"], result["lines"]):
            sku = item["sku"] if item else None
            counts["lines_evaluated"] += 1
            if expected == sku and item:
                counts["correct_sku_or_abstention"] += 1
            else:
                reasons.append("identity")
            if sku is None:
                counts["abstained"] += 1
            elif sku != expected:
                counts["false_verified_sku"] += 1
            if expected is not None:
                counts["labelled_skus"] += 1
                counts["retrieved_in_top_3"] += bool(
                    item and expected in [p["sku"] for p in item["candidates"][:3]]
                )

        if "quantities" in case:
            actual_quantities = [line["quantity"] for line in result["lines"]]
            counts["labelled_quantities"] += len(case["quantities"])
            missing = object()
            mismatches = sum(a != b for a, b in zip_longest(actual_quantities, case["quantities"], fillvalue=missing))
            counts["incorrect_quantity"] += mismatches
            if mismatches:
                reasons.append("quantity")
        if "candidate" in case:
            counts["labelled_suggestions"] += 1
            if not result["lines"] or case["candidate"] not in [
                candidate["sku"] for candidate in result["lines"][0]["candidates"][:3]
            ]:
                reasons.append("candidate")
            else:
                counts["correct_suggestions"] += 1
        for field, value in case.get("attributes", {}).items():
            counts["labelled_attributes"] += 1
            if result["lines"][0]["attributes"].get(field) == value:
                counts["correct_attributes"] += 1
            else:
                reasons.append("attribute")
        questions = " ".join(result["questions"]).lower()
        for field in case.get("missing", []):
            counts["labelled_missing_fields"] += 1
            if field in questions:
                counts["missing_fields_requested"] += 1
            else:
                reasons.append("clarification")
        try:
            actual = build_quote(result, account)["total"]
        except ValueError:
            actual = None
        if actual != case.get("total"):
            reasons.append("quote")
        if "total" in case:
            counts["labelled_totals"] += 1
            counts["correct_totals"] += actual == case["total"]
        if "category" in case:
            categories[case["category"]] += 1
            tally = outcomes[case["outcome"]]
            tally["cases"] += 1
            tally["passed"] += not reasons
        if reasons:
            failures.append({"case": case["id"], "fields": sorted(set(reasons))})
        timings.append((perf_counter_ns() - start) / 1e6)
    return {
        "catalogue_version": VERSION,
        "scope": "Author-labelled synthetic regression cases, deterministic local engine.",
        "cases": len(cases),
        "passed": len(cases) - len(failures),
        **counts,
        "natural_cases_by_category": categories,
        "natural_cases_by_outcome": outcomes,
        "median_ms": round(median(timings), 3),
        "p95_ms": round(sorted(timings)[(95 * len(timings) + 99) // 100 - 1], 3),
        "external_provider_calls": 0,
        "provider_cost_nzd": "0.00",
        "failures": failures,
    }


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, indent=2))
    raise SystemExit(bool(report["failures"]))
