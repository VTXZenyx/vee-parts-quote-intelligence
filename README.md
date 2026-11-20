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

## Start a guided demo

1. On **Enquiry workspace**, select **Start guided demo**. VEE creates a separate seeded workspace and prepares a Harbour Packaging email for two cylinders.
2. Select **Receive test email**. Read the original message, then find the missing specifications under **Technical investigation**. **VEE analysis** links findings to the customer’s words.
3. Review the question in **Employee review** and select **Approve clarification**. Choose **Load the cylinder reply**, then **Receive demo reply**.
4. Compare the measurements with the suggested cylinder. Confirm the part and select **Verify match**. Create a draft quotation.
5. Review two cylinders at NZD 137.50 each, NZD 41.25 GST and the NZD 316.25 total. Follow **Go to employee review** and approve the saved version.
6. Use the guide’s links to inspect message and audit history. **Exit guide** keeps you in the demo with the current enquiry. **Return to original workspace** switches back to the original records. Start again from the dashboard for a fresh run.

Guide instructions follow the prepared cylinder scenario and the enquiry's actual stage. The guide uses the same employee forms as regular work. Reopening the browser in the same session allows **Continue guided demo**. After a server restart the demo database is retained and the guide can be started again.

## Try the Demo Email Inbox

- **Fictional email** lets you load a prepared scenario or write your own. Use addresses ending in `.example`. Approved clarification threads appear under **Waiting for a customer reply**.
- **Provider fixtures** imports a simulated Gmail or Outlook delivery and shows accepted and held receipts. Expand **Delivery details** for identifiers and the original provider record.
- **Message history** shows fictional email deliveries. Expand a received email and select **Replay delivery** to verify that the conversation remains intact.
- **Start fresh demo** creates a separate workspace for free exploration. New demo databases are stored next to the original in its `.demos` directory.

Choose the unavailable adapter to see a commercial hold. Choose the pressure conflict to see a technical block, then use the corrected pressure reply and reconcile it before a part can be verified. The inbox also includes exact bearing references, multiple parts, ambiguous quantities, irrelevant messages and a request to skip approval.

Demo replies attach to a selected enquiry once an employee has approved a clarification. Enquiry IDs and message IDs apply within the current demo workspace. The application uses local synthetic addresses, catalogue evidence and commercial records. It supports a single local employee and uses the fixture photograph for manual inspection. Real mail, arbitrary attachment uploads, image inference, ERP stock reservations, and production authentication are outside the demo.

## Try intelligent enquiry processing

1. Open **Demo Email Inbox → Provider fixtures**. Select the Gmail fixture for Harbour’s missing cylinder dimensions first. Expand the held delivery to read the reason, original provider record and normalised envelope.
2. Import **Harbour · cylinder request**. On the held reply select **Retry association**, then open the linked enquiry. Outlook’s independent cylinder request has the same subject and opens a different enquiry. **Replay provider delivery** exercises the original stored payload.
3. Under **VEE analysis**, switch between customer messages and follow **Read source message** to inspect the quoted evidence. The default method is deterministic. Open **Change processing method** and select **Mock model** for the offline demonstration. The technical investigation shows candidate catalogue evidence and outstanding restrictions.
4. Open **Review or correct a finding**. Confirm a reading or flag a correction with a proposed value and reason. A correction reopens technical review and makes existing quote versions historical. Obtain a new customer reply beginning with `Revised request:` and reconcile the complete request before reverifying. The original messages remain available in the thread.
5. For the complete cylinder request, verify the match, draft the quote and review NZD 316.25 including GST. To see an approval become historical, approve the Outlook bearing quotation and then import **Kauri · corrected bearing quantity**.

### Optional live extraction

The base installation runs offline. An API key by itself enables no network processing. To make live extraction available, install `requirements-ai.txt`, supply `OPENAI_API_KEY` through the process environment, set `VEE_ENABLE_AI=1` and optionally set `VEE_AI_MODEL` (default `gpt-4.1-mini`). Restart VEE. Only an employee selecting **Send this synthetic message to OpenAI** and pressing **Process selected message** initiates an external request. Opening a page, importing a fixture and running the tests use no paid inference.

The adapter sends one selected subject and body. API usage may incur charges. A missing key or SDK, timeout, rate limit or invalid response leaves local findings and manual review available. The displayed method identifies the actual result. SDK request and response handling have been exercised offline. Live model quality, access to the configured model and service behaviour require a separately authorised live evaluation.

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
.venv/bin/ruff check vee tests scripts evaluation
.venv/bin/mypy --check-untyped-defs vee evaluation
.venv/bin/python -m unittest discover -v
```

The unit and integration tests use temporary databases. Refer to [the test plan](TEST_PLAN.md) for the safety scenarios, [architecture](ARCHITECTURE.md) for data and approval boundaries, and [the backlog](BACKLOG.md) for acceptance criteria for later releases.

Run `.venv/bin/python -m evaluation.run` for the synthetic catalogue benchmark and `.venv/bin/python -m evaluation.enquiries` for the offline findings evaluation. For the optional interactive smoke test, install `requirements-browser.txt` in the same environment and use a local Chromium installation (or run `.venv/bin/playwright install chromium`). Then run `.venv/bin/python -m scripts.browser_smoke`. The smoke test starts its own server and database.

**New enquiry** accepts a synthetic account, subject and original request. Replaying the same intake form records one enquiry and one receipt. Conflicting content for an existing message ID is rejected. **ENQ-1037** contains a generated inspection photograph. Employees can open the attachment and review the missing fitting specifications.

Subject requirements participate in technical review. Include the scope and quantity of each product in the request body. If a revised request changes an earlier measurement, include the confirmed value. For assembly orders, specify the total quantity of each part. Inspect the outstanding issues before approving a replacement. See [the full-system audit](TEST_PLAN.md#full-system-audit-of-the-first-synthetic-milestone) for the verification results.
