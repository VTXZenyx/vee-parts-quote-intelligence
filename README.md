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

## Try the Demo Email Inbox

1. From the dashboard, select **Try sample workflow** to load a cylinder email, or **Create test email** to choose another scenario or write your own. Use addresses ending in `.example`.
2. Select **Receive test email**. Open the original message, check the next step, and read the missing specifications and catalogue evidence.
3. Select **Approve clarification** to add the reviewed question to the local conversation. Choose **Compose demo reply**, open **Try a reply example**, and load **Supply the missing cylinder measurements**. Select **Receive demo reply**.
4. Review the cylinder evidence and confirm the proposed part. Prepare the quote for two cylinders and review the NZD 316.25 total, including NZD 41.25 GST. You can save changes as a new quote version before approving it.
5. Open **Demo Email Inbox**, expand a received email in **Demo message history**, and select **Replay delivery**. VEE recognises the message ID and keeps the existing conversation.
6. Select **Start fresh demo** to open a separate, seeded SQLite workspace. **Return to original workspace** restores the original selection. New demos are stored beside the original database in its `.demos` directory. A browser keeps its current selection across an app restart and must reload forms to continue.

Choose the unavailable adapter to see a commercial hold. Choose the pressure conflict to see a technical block, then use the corrected pressure reply and reconcile it before a part can be verified. The inbox also includes exact bearing references, multiple parts, ambiguous quantities, irrelevant messages and a request to skip approval.

Demo replies attach to a selected enquiry once an employee has approved a clarification. Enquiry IDs and message IDs apply within the current demo workspace. The application uses local synthetic addresses, catalogue evidence and commercial records. It supports a single local employee and uses the fixture photograph for manual inspection. Real mail, arbitrary attachment uploads, image inference, ERP stock reservations, and production authentication are outside the demo.

## Try intelligent enquiry processing

1. Open **Demo Email Inbox → Import a provider email**. Select the Gmail fixture for Harbour’s missing cylinder dimensions first. Expand the held delivery to read the reason, original provider record and normalised envelope.
2. Import **Harbour · cylinder request**. On the held reply select **Retry association**, then open the linked enquiry. Outlook’s independent cylinder request has the same subject and opens a different enquiry. **Replay provider delivery** exercises the original stored payload.
3. Under **Customer requirements**, switch between customer messages to inspect findings and the quoted evidence. The default method is deterministic. Under **Process or review this message**, select **Mock model** for the offline demonstration. The technical investigation shows candidate catalogue evidence and outstanding restrictions.
4. Confirm a reading or flag a correction with a proposed value and reason. A correction reopens technical review and makes existing quote versions historical. Obtain a new customer reply beginning with `Revised request:` and reconcile the complete request before reverifying. The original messages remain available in the thread.
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
.venv/bin/ruff check vee tests
.venv/bin/mypy --check-untyped-defs vee
.venv/bin/python -m unittest discover -v
```

The unit and integration tests use temporary databases. Refer to [the test plan](TEST_PLAN.md) for the safety scenarios, [architecture](ARCHITECTURE.md) for data and approval boundaries, and [the backlog](BACKLOG.md) for acceptance criteria for later releases.

Run `.venv/bin/python -m evaluation.run` for the fixed synthetic catalogue benchmark. For the optional interactive smoke test, install `requirements-browser.txt` in the same environment and use a local Chromium installation (or run `.venv/bin/playwright install chromium`). Then run `.venv/bin/python -m scripts.browser_smoke`. The smoke test starts its own server and database.

**New enquiry** accepts a synthetic account, subject and original request. Replaying the same intake form records one enquiry and one receipt. Conflicting content for an existing message ID is rejected. **ENQ-1037** contains a generated inspection photograph. Employees can open the attachment and review the missing fitting specifications.

Subject requirements participate in technical review. Include the scope and quantity of each product in the request body. If a revised request changes an earlier measurement, include the confirmed value. For assembly orders, specify the total quantity of each part. Inspect the outstanding issues before approving a replacement. See [the full-system audit](TEST_PLAN.md#full-system-audit-of-the-first-synthetic-milestone) for the verification results.
