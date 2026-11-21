# Present VEE Industrial Supplies in five minutes

VEE helps a distributor turn an incomplete parts request into a quotation an employee can stand behind. This local demonstration uses a fictional Hamilton sales desk, quotes@vee.example, and a synthetic warehouse. Run the app with the local setup in [README.md](README.md).

| Time | Presenter action | What to point out |
| --- | --- | --- |
| 0–1 min | On **Enquiry workspace**, choose **Start a demonstration**, select **Missing product information**, then **Start scenario**. Read the Harbour Packaging email and select **Open enquiry**. | The customer needs two replacements for a packaging line. An unreadable label gives the employee too little to quote. The request, interpreted quantity and missing specifications are visible together. |
| 1–2 min | Read the question in **Employee review**. Select **Approve clarification**, then **Record prepared reply**. | The clarification was recorded in a mock mailbox. The customer supplies bore, stroke, action, standard, port and mount. Extraction runs locally by default. |
| 2–3 min | Compare 32 mm bore, 100 mm stroke, double acting, ISO 15552, G1/8 and foot mount. Tick **Confirm CYL-32-100-DA** and select **Verify match**. | Twelve are on hand. The Harbour agreement sets the net rate at NZD 137.50. Reviewers can expand the catalogue evidence. |
| 3–4 min | Choose **Create draft quotation**. Read the quantities and totals. Select **Approve version 1**. | Two at NZD 137.50 gives NZD 275.00 net, NZD 41.25 GST and NZD 316.25 total. Technical verification and commercial approval are separate decisions. |
| 4–5 min | Choose **Open customer preview**. Show the reference, availability, delivery condition and print control. Choose **View customer account** to see the customer perspective. Return to the enquiry, open audit history and select **Return to original workspace**. | The preview is the approved saved version. Stock is unreserved. Nothing has been mailed. Start another demonstration for a fresh isolated database. **Exit guide** keeps the current demo open. |

## Other discussions to demonstrate

| Dashboard scenario | Decision and expected result |
| --- | --- |
| Simple parts quotation | Kauri orders four BRG-6205-2RS at the NZD 12.75 list price. Verify, draft and approve NZD 58.65 including GST. |
| Not enough stock | Ten BRG-6203-ZZ requested, six on hand. Confirm the match and explicitly verify for a partial quotation. Six at NZD 9.80 total NZD 67.62 including GST. Four remain outstanding. |
| Incompatible product | Coastal asks for 350 bar on a 250-bar BSPP adapter. Show the conflict and the missing approval action. Leave it blocked or request a corrected requirement. |
| Customer changes an order | Approve two Harbour cylinders, then **Record revised order**. Read the revised message, explain why it replaces the earlier request, confirm the revised request, verify again, draft and approve version 2. NZD 474.38 replaces NZD 316.25. Version 1 stays in history. |

## What is simulated

All six accounts, 45 warehouse SKUs, agreements, inventory, inbound messages and employee roles are fictional. The warehouse provides no reservation, freight estimate or promised delivery date. Deterministic matching, Decimal arithmetic, SQLite history and PDF printing through the browser run locally. The mock extraction option runs offline. Live model access is optional and disabled by default. Mailbox sync, outbound dispatch, ERP, account authentication and live supplier imports are future work.

## Ask the distributor

1. Which parts of this enquiry resemble a recent job at your sales desk?
2. Where did your staff spend the most time on that job?
3. Would the clarification and quote review have saved work? Which problem mattered more?
4. Which catalogue, agreement and stock records would staff have needed, and who owns them?
5. What evidence, permissions or controls would you require before paying for a limited trial?

Record the answers and any observed difficulty. The script's time boxes are presentation targets. Customer savings and commercial accuracy have yet to be measured.
