# VEE Parts & Quote Intelligence

A local employee workspace for investigating industrial parts enquiries and reviewing quotations in New Zealand dollars. This development release uses a synthetic mailbox, a small fixture catalogue and account-specific commercial records. Employees can inspect the original request, review evidence, approve questions, record a simulated reply and issue a decision on a versioned quotation.

## Run locally

Use Python 3.12. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m vee.web
```

Open the loopback address on port 5050 printed by Flask. On first run the server seeds the local SQLite database at `instance/workspace.sqlite3`. Subsequent starts preserve enquiry history and decisions. Set `VEE_DATABASE` to a different filesystem path for a separate synthetic workspace. The local development server represents one demo employee. Use only on a trusted machine with synthetic records.

## Exercise an enquiry

1. Open **ENQ-1042**, the Harbour Packaging cylinder request. Inspect the attached inspection note, catalogue candidates and missing specifications.
2. Review or edit the clarification, approve it for the mock mailbox, then record the supplied synthetic reply.
3. Inspect the bore, stroke, port and mounting evidence. Confirm the catalogue reference to record the employee's technical decision.
4. Create a draft for two cylinders. The account price is NZD 137.50 each. The draft totals NZD 316.25 including NZD 41.25 GST.
5. Reject with a reason or approve the displayed version. To revise a rejected quote, edit it and submit a fresh approval. Reopen the enquiry to inspect its history.

ENQ-1040 exercises a multi-product order. Technical comparisons use deterministic catalogue rules. Uploaded photos, live mailbox delivery, ERP access, company authentication and tenant isolation are future milestones. A quotation approval is a local decision only.

## Developer checks

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/ruff check vee tests
.venv/bin/mypy --check-untyped-defs vee
.venv/bin/python -m unittest discover -v
```

The unit and integration tests use temporary databases. Refer to [the test plan](TEST_PLAN.md) for the safety scenarios, [architecture](ARCHITECTURE.md) for data and approval boundaries, and [the backlog](BACKLOG.md) for acceptance criteria for later releases.

Run `.venv/bin/python -m evaluation.run` for the fixed synthetic catalogue benchmark. For the optional interactive smoke test, install `requirements-browser.txt` in the same environment and use a local Chromium installation (or run `.venv/bin/playwright install chromium`). Then run `.venv/bin/python -m scripts.browser_smoke`. The smoke test starts its own server and database.

**New enquiry** accepts a synthetic account, subject and original request. Replaying the same intake form records one enquiry and one receipt. Conflicting content for an existing message ID is rejected. **ENQ-1037** contains a generated inspection photograph. Employees can open the attachment and review the missing fitting specifications.
