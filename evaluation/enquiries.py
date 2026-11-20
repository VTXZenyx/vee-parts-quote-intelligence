"""Evaluate author-labelled message findings separately for each offline mode."""

import json
from collections import Counter
from pathlib import Path

from vee.extraction import extract


def evaluate(mode: str) -> dict:
    cases = json.loads(Path(__file__).with_suffix(".json").read_text())
    correct: Counter[str] = Counter()
    total: Counter[str] = Counter()
    failures = []
    for case in cases:
        result = extract(case["id"], case["text"], mode)
        rows = result["findings"]
        checks = [
            (
                "provenance",
                result["method"] == mode
                and result["source"] == case["id"]
                and all(row["evidence"] in case["text"] for row in rows),
            )
        ]
        for field, kind in [("references", "reference"), ("quantities", "quantity")]:
            if field in case:
                values = [
                    r["value"]
                    for r in rows
                    if r["kind"] == kind and r["status"] == "stated"
                ]
                checks.append((field, values == case[field]))
        labels = case.get("expected", []) + (
            case.get("mock_expected", []) if mode == "mock" else []
        )
        for kind, status, value in labels:
            checks.append(
                (
                    kind,
                    any(
                        r["kind"] == kind
                        and r["status"] == status
                        and value.casefold() in r["value"].casefold()
                        for r in rows
                    ),
                )
            )
        for category, passed in checks:
            total[category] += 1
            correct[category] += int(passed)
            if not passed:
                failures.append([case["id"], category])
    return {
        "mode": mode,
        "cases": len(cases),
        "passed": len(cases) - len({f[0] for f in failures}),
        "correct": dict(correct),
        "labelled": dict(total),
        "failures": failures,
    }


if __name__ == "__main__":
    results = [evaluate(mode) for mode in ("deterministic", "mock")]
    print(json.dumps(results, indent=2))
    raise SystemExit(any(result["failures"] for result in results))
