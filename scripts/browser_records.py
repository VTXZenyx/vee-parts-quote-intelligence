"""Reopen the databases written by the guided browser journeys and check the ledger."""

from pathlib import Path

from vee import demo, store

# Independent expected values for the exact customer emails driven by Chromium.
EXPECTED = {
    "bearings": [("51.00", "7.65", "58.65", 4, 4)],
    "cylinder": [("275.00", "41.25", "316.25", 2, 2)],
    "shortage": [("58.80", "8.82", "67.62", 10, 6)],
    "contract": [("275.00", "41.25", "316.25", 2, 2), ("412.50", "61.88", "474.38", 3, 3)],
    "conflict": [],
}


def verify_scenario_records(workspaces: set[Path]) -> None:
    found = set()
    for path in workspaces:
        enquiries = [item for item in store.inbox(path) if item.get("message_id")]
        if not enquiries:  # Restarting the guide creates a fresh workspace before intake.
            continue
        assert len(enquiries) == 1, path
        item = enquiries[0]
        scenario, = [name for name in EXPECTED if demo.SCENARIOS[name].body == item["body"]]
        found.add(scenario)
        assert item["customer"] == demo.SCENARIOS[scenario].customer
        events = [event["action"] for event in item["history"]]
        assert [event["revision"] for event in item["history"]] == list(range(1, item["revision"] + 1))
        if scenario == "conflict":
            assert item["status"] == "needs_clarification" and not item["selected_skus"] and not item["quotes"]
            continue
        assert item["status"] == "approved" and events[-1] == "approve_quote"
        assert len(item["quotes"]) == events.count("approve_quote") == len(EXPECTED[scenario])
        for version, (quote, expected) in enumerate(zip(item["quotes"], EXPECTED[scenario], strict=True), 1):
            line, = quote["lines"]
            assert (quote["subtotal"], quote["gst"], quote["total"], line["requested_quantity"], line["quantity"]) == expected
            assert quote["version"] == version and quote["currency"] == "NZD"
        if scenario == "contract":
            assert events.count("verify_match") == 2 and "reconcile_requirements" in events
        if scenario == "shortage":
            assert "verify_partial" in events and item["quotes"][0]["partial_offer"]["outstanding"] == 4
        if scenario == "cylinder":
            assert "approve_clarification" in events and "simulate_reply" in events
    assert found == set(EXPECTED), found
