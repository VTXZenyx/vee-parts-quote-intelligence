# VEE Parts & Quote Intelligence

VEE helps an industrial distributor turn an incoming technical enquiry into a traceable, employee-approved quotation. The initial market is small and medium New Zealand distributors of bearings, threaded fasteners, hydraulics, pneumatics and mechanical replacement parts. A sales employee owns the enquiry. A qualified employee resolves technical questions outside the sales employee’s authority.

## The employee’s job

A packaging plant needs two replacement cylinders. The customer supplies a photograph and a description, but the cylinder marking has worn off. The employee must be able to inspect the original message, see which catalogue records fit, identify the measurements that distinguish them, approve a clarification draft, and resume work when the customer replies. The quote should account for every requested item, show how the selling price was obtained, and preserve the employee’s technical and commercial decisions.

## Required product capabilities

These requirements describe the complete product. The current local implementation and its limits are recorded in [ARCHITECTURE.md](ARCHITECTURE.md).

| Module | Required behaviour | Evidence an employee should see |
| --- | --- | --- |
| 1. Enquiry processing | Connect authorised Gmail and Microsoft 365 mailboxes. Detect and deduplicate enquiries and replies, preserve message threads, and handle multiple items. Read PDFs, spreadsheets, photographs and supported technical documents. Extract customer, quantities, references, dimensions, purpose and urgency. | Original message and attachments, intake time, customer, extracted line items, message provenance and processing status. |
| 2. Product identification | Combine exact part references, structured filters, semantic retrieval and visual similarity over approved catalogues and legally accessible manufacturer records. Use replaceable models to interpret photographs, markings, descriptions and drawings. Find exact, alternative and discontinued-part candidates. Ask for better photographs or measurements when needed. | Candidate identifiers, reasons for retrieval, revision or source, and uncertain or unreadable attributes. |
| 3. Technical verification | Compare category-specific dimensions, materials, threads, pressure, load, tolerances and other governing specifications. Detect conflicts, gaps and unsupported claims. Escalate safety-critical cases to a qualified reviewer. Preserve the evidence and decision behind an approved replacement. | Required and observed value, units, source, discrepancy, and human decision. An image resemblance alone cannot establish interchangeability. |
| 4. Customer communication | Draft focused clarification questions. Employees can edit, approve or reject the draft. Associate the reply with the original request and update outstanding questions. Only a separately authorised send operation may transmit an explicitly approved version. | Exact draft under review, outstanding questions, conversation history and approval record. |
| 5. Commercial evidence | Use authorised imports or ERP, inventory and supplier APIs for product records, on-hand quantity, customer-specific pricing, approved discounts, special orders and delivery. Distinguish confirmed availability, estimates and unknowns. | Source, customer, currency, timestamp, quantity, price basis, discount authority and delivery status. Unknown values stay unknown. |
| 6. Quotations | Create editable multi-line drafts from verified items and quantities. Apply authorised commercial terms, discounts, currency, rounding and GST deterministically. Support alternatives, unavailable items and incomplete requests. Generate a professional quotation document and track versions and approvals. | Each quoted item, price basis, subtotal, GST, total, delivery terms, unresolved lines and the exact approved revision. |
| 7. Employee workspace | List, search and track enquiries. Open originals and attachments, inspect extracted requirements, candidates, technical evidence, stock and pricing. Correct errors, review questions, reject recommendations and approve drafts. Show outstanding actions and audit history. | Status, evidence, responsible reviewer, feedback and dated history for the selected enquiry. |

## Release boundaries

- **Local foundation.** Use synthetic records, sample attachments and mock commercial data. An employee can progress an incomplete request through clarification, technical review and draft quote approval. Label simulated actions at their point of use. Keep decisions and history across reloads.
- **Pilot with business data.** Require authenticated identity, tenant isolation, role checks, secure attachment handling, secret management, audit and recoverability. Obtain authorisation for each business, data source and external integration before enabling it.
- **Customer delivery.** Bind approval to the exact recipient, content and revision. Recheck authority and version at dispatch, and make retries idempotent. Sending and production deployment require explicit approval.

## Product acceptance

1. An ambiguous description, unreadable marking or conflicting measurement leaves the item unresolved. A qualified reviewer can see why the system requested clarification or escalated.
2. Source records support each compatibility claim. Changes to the requirements, selected product or governing evidence require technical reconsideration.
3. Unknown stock, delivery or customer price cannot silently become a promise or a default price. Any partial quote identifies outstanding items.
4. Quantity, unit price, authorised discount, tax treatment and currency determine reproducible line and document totals. Pricing changes require a new review.
5. An employee can reject a recommendation, correct a draft and trace each decision to its inputs. A customer reply cannot itself grant an approval.
6. An employee can use the queue and workspace with a keyboard and at practical screen sizes. States, uncertainty and next actions have text labels. Visible controls work or explain their unavailability.
7. Pilot decisions require measured results against a fixed, independently labelled industrial evaluation set, including ambiguous and unsafe-to-quote cases. The evaluation contract is in [TEST_PLAN.md](TEST_PLAN.md).
