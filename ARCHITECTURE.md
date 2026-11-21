# Architecture

## Local deployment boundary

The foundation runs as one Flask application serving an employee queue and enquiry workspace. The application opens a local SQLite database for a single synthetic distribution business. A browser on the same machine can change that workspace. There is no authenticated employee identity or tenant boundary. Use the local application only with synthetic data.

| Component | Responsibility |
| --- | --- |
| Flask application factory in `vee/web.py` | Initialise the database, serve the searchable queue and enquiry detail, validate request origin and CSRF token on action forms, and return form errors to the employee. |
| Jinja templates and static assets in `vee/` | Render the employee workflow, original request, requirements, commercial evidence and approval controls in the browser. |
| Catalogue and quotation logic in `vee/catalogue.py` | Analyse inbound text against a synthetic catalogue, identify blockers and calculate quotations from the customer’s commercial records. |
| Local store in `vee/store.py` | Load and update the synthetic enquiry workflow. The server owns state transitions and persists reviewed decisions and audit records. |
| SQLite | Keep the local record across process restarts. Set `VEE_DATABASE` to select a location. The default is `workspace.sqlite3` in Flask’s instance directory. |
| Verification | Unit and request-level tests exercise isolated databases. GitHub Actions runs lint, type checking and the automated suite. See TEST_PLAN.md for broader release requirements. |

The browser reads an enquiry, then submits an explicit action to the selected enquiry’s POST endpoint. The store checks whether the action is allowed in the current state. Successful mutations change the persistent workflow and record the action. The browser follows a redirect to read the resulting state. Search operates over the synthetic queue and retains the enquiry ID as the stable workspace link.

## Persistence and decisions

The `enquiries` table stores an enquiry ID, its revision number and a JSON state document with the thread, attachments, requirements, candidate evidence and current selection. The `events` table records timestamp, actor, action and detail under a unique enquiry/revision pair. The `quotes` table stores each quotation snapshot under a unique enquiry/version pair. Startup creates the schema and missing seed records. It preserves existing decisions.

Every submitted action carries the revision displayed to the employee. A SQLite write transaction takes a lock, compares that revision, checks the permitted transition and writes the state change, any quote snapshot and audit event together. A stale form or failed audit insert cannot partially apply a decision. Old quote versions remain available. “Demo employee” and “Mock mailbox” are synthetic actors.

The demonstration begins with ENQ-1042. Approving a clarification adds a local outbound thread entry. A simulated inbound reply triggers analysis of the customer’s messages. The employee must confirm every resolved product before preparing a quote. A rejection captures a reason. Editing a rejected or draft quote writes a new version. Approval checks the latest saved quote against the current commercial calculation and closes the local workflow. It makes no external stock reservation or delivery commitment.

## Back up and restore a synthetic workspace

From the repository root, stop the local application and use a private local directory for the snapshot and recovered database. Both destination paths must be new, in existing directories on a filesystem supporting hard links. Substitute the actual source path if you set `VEE_DATABASE`.

```bash
.venv/bin/python -m vee.backup backup vee/instance/workspace.sqlite3 vee/instance/backup-001.sqlite3
.venv/bin/python -m vee.backup restore vee/instance/backup-001.sqlite3 vee/instance/recovered-001.sqlite3
VEE_DATABASE=vee/instance/recovered-001.sqlite3 .venv/bin/python -m vee.web
```

Open the recovered workspace and check the last expected audit decision, quote version and total. Both operations open the source read-only and use SQLite’s backup API to capture committed state, including data in a write-ahead log. Before publishing the file, the CLI compares the schema with this code version and checks SQLite integrity and foreign keys. It verifies essential enquiry and quote record shapes, reconciles audit revisions and quote versions, matches each saved quote version and total to its audit event, binds approved status to the recorded version and amount, and recomputes historical totals from saved line prices, quantities and the saved GST rate. A private staging file and an exclusive hard link keep an existing destination intact. A failed check exits nonzero. Choose a different destination when repeating the drill.

The snapshot contains the entire synthetic database, including customer text and audit history. It is an unencrypted local file. The drill covers recovery into the same application schema. It does not supply off-machine retention, tenant-specific recovery or production disaster recovery. Tests exercise the round trip and rejection of invalid input via `python -m unittest tests.test_backup -v`.

## Matching and quotation policy

The local catalogue covers pneumatic cylinders, bearings, hex bolts and hydraulic adapters. Text patterns recognise part references, whole-unit quantities and a limited vocabulary of technical attributes. An exact reference or a unique candidate satisfying the supported requirements can be presented for employee verification. Conflicts, missing attributes, unsupported language, discontinued references and certain high-risk terms trigger review or clarification. The analysis uses inbound message text. Sample attachment contents are available for employee inspection. Free-form interpretation and visual matching remain development work.

A quote aggregates quantities per verified SKU and checks them against the synthetic on-hand quantity. The commercial rules look for an account agreement and use the synthetic list price where the account permits it. The quote multiplies each whole-unit quantity by its decimal net unit price, sums the net lines in NZD, then calculates 15% GST on the subtotal and rounds to cents using half-up rounding. The total is the subtotal plus rounded GST. Supply beyond on-hand stock, unknown contract pricing and discontinued parts require resolution. Dates of delivery remain unconfirmed.

## Technology decisions

| Decision | Reason for the foundation | When to revisit |
| --- | --- | --- |
| Server-rendered Flask and Jinja | Most interactions are reads and reviewed form submissions. One language, one process and one deployment keep the first end-to-end workflow easy to run and test. | Evaluate a typed JSON API with FastAPI and a React/Next.js client when complex document review, simultaneous users or external clients justify the additional boundaries. |
| SQLite on local disk | Transactions and disk persistence are sufficient for a single synthetic workspace and isolated repeatable tests. The prototype requires no database service. | Adopt managed PostgreSQL, migrations, backup drills and tenant-aware constraints before multi-business use. Evaluate pgvector against a measured retrieval baseline before adding an embedding index. |
| Catalogue evidence and deterministic commercial logic | A fixture, known catalogue record and explicit rule provide a reproducible baseline for an employee decision and a quote. Unknown or conflicting specifications must stay visible. | Add versioned catalogues, provenance and model adapters after data rights and evaluation labels exist. Keep engineering checks and arithmetic independent of model output. |
| Explicit human decisions | A service accepting a model or customer message as an approval would cross an authority boundary. A reviewed draft and the authority to transmit are separate decisions. | Add authenticated, role-bound approvals tied to immutable revisions and an idempotent dispatch mechanism before enabling real communications. |

## Threat model and pilot design

The local web layer binds its normal launcher to loopback, limits accepted hostnames and request size, verifies a per-session form token and checks an explicit Origin header when supplied. It sets a restrictive content security policy, disables response caching and sets a same-origin referrer policy and browser content-type protections. Its signing key is generated at start-up, so a restart invalidates existing session forms. Local process or filesystem access still grants access to the synthetic workspace. Email transport, vision processing and ERP remain simulated or absent. The optional text extraction adapter reads its credential from the process environment.

Before any real business data enters the system, implement and verify the following design.

- Authenticate employees through an approved identity provider. Bind requests, background jobs and audit events to the correct business and actor. Apply role checks for sales, technical qualification, pricing authority and administration. Scope every query, object key, export and search index to its business. Test a minimum of two tenants.
- Keep mailbox and supplier credentials in a managed secret store. Use least-privilege scopes, per-business credentials, rotation, revocation and source-specific consent. Encrypt transport and stored data. Set retention and deletion rules with each business.
- Store attachments privately, validate type and size, scan before parsing and isolate parsers with resource limits. Treat all customer, supplier and model content as untrusted data. Restrict retrieval to approved sources. Validate model output against a typed schema with evidence references. Keep tools that can send, approve or change prices outside the model’s authority.
- Version requirements, catalogue records, rules, commercial snapshots and quote terms. Bind employee approvals to exact inputs and invalidate approvals when inputs change. Persist workflow transitions, audit events and outbound work atomically. Use provider message IDs, idempotency keys, bounded retries and reconciliation for uncertain delivery.
- Keep business records and operational logs separate, redact sensitive content, restrict audit access and maintain tamper-resistant history. Test safe migrations, backups and restoration. Record incident handling, processing failures, stale sources and operator recovery before a pilot.

## Planned integration boundaries

A mailbox adapter accepts authorised provider events and normalises messages into immutable thread and attachment records. A worker extracts structured requirements with source locations. A retrieval adapter searches approved catalogue revisions, while category rules compare required and observed values and supply blocking reasons. A commercial adapter provides dated customer-specific price, stock and delivery evidence. The quotation engine consumes verified inputs, versions and rounds them deterministically, and submits a reviewable document. Only an authorised dispatch worker can transmit a reviewed document. Start with modular components in one codebase and introduce queues, model providers and separate services as their workloads justify them.

## Synthetic intake

GET and POST at `/enquiries/new` support local receipt of new requests. The form supplies a UUID per envelope. A SQLite write transaction checks for a matching receipt, compares the unchanged original content, allocates the enquiry number and records the first audit event. The server accepts accounts drawn from its synthetic fixtures. The shared origin and CSRF checks protect intake and review actions. The fixed fitting photograph in ENQ-1037 is a generated inspection fixture. No image-derived measurement enters the verifier.

The backup check also compares the stored enquiry identity and revision with the state document, checks audit revision continuity and verifies quote versions against creation and edit events. These checks establish structural consistency within this application schema. They do not authenticate the authors of historical records.

Intake treats the subject as customer evidence. A family or quantity in a new subject must agree with the applicable request line. Unresolved subject wording creates a clarification issue. The fixed seed captions are authored with their synthetic scenarios. Revised requests retain prior service hazards and require explicit resolution of earlier technical attributes for the relevant family. This conservative rule can send benign free-text subjects or ambiguous multi-line requests to review.

On the first startup of a pre-audit database, the store re-evaluates previously eligible decisions within a transaction. If the revised checks change the resolved items or block eligibility, the store records a new revision and audit event, clears the selection and retains earlier quote snapshots as history. New employee technical decisions record the source and specifications in the audit event, including decisions made before a quote was created.

## Offline demo email

The demo inbox records a fictional envelope within the enquiry’s existing message history. Message IDs are UUIDs. One SQLite write transaction checks the ID and content, validates any selected reply thread and revision, runs the existing intake or reply transition, and records its audit event. A matching replay returns the saved enquiry without writing again. A reused ID with different content or thread is rejected. Shared subjects and addresses do not merge independent emails. Approved clarifications are local outbound records and have no transport.

A fresh demo seeds a separate SQLite file under the primary database’s sibling `.demos` directory. The cookie selects an existing demo file, and mutation tokens are bound to that selection so a form from another workspace cannot change a record with the same enquiry number. Each SQLite file can be backed up separately with the existing CLI. This mechanism supports demonstration isolation on a trusted machine. Production identity and access controls are separate work.

## V3 message evidence and ingestion

The provider importer accepts fixtures for one fictional local mailbox. Gmail messages use payload headers, UTF-8 base64url plain text and internal timestamps. Graph messages use the sender, recipient list, internet message headers, conversation ID, text body, received time and optional attachment metadata. The supported subset is narrower than either provider API. The UI exposes prepared fixtures only. Threads and raw envelopes are local, unencrypted records.

A SQLite write transaction claims the provider/message ID and records the raw and normalised envelope, its disposition, the enquiry and its audit revision. Accepted replies require consistent customer, recipient, conversation and parent references. The last accepted inbound source in the enquiry determines sequence. A changed subject can attach through identifiers and still block technical approval. A second delivery of the same normalised message has no workflow effect. A changed payload under an accepted ID is rejected when its normalised fields differ. Unresolved receipts can be retried after a missing parent arrives. Forwards, stale branches, conflicting identities and unrecognised accounts require manual investigation. The simulator has no forced-link or mailbox dispatch action.

The advisory service handles one inbound message at a time. Local modes extract line items from its body. OpenAI receives subject and body as an untrusted user message under a separate task instruction. The adapter exposes no tools, requests a strict schema, sets a 15-second SDK timeout, zero SDK retries and a 4,096-token output cap. Server validation bounds finding count and size, requires source excerpts and checks stated quantities and measurements against their source. An excerpt establishes textual provenance. Semantic correctness still requires review. Customer-provided attachment metadata stays outside model input.

Findings are advisory and cannot select a SKU, authorise a price or advance approval. Explicit processing saves a source-bound result against the displayed revision, with a second revision check after the optional network call. Employee reviews retain the prior value, evidence and reason in audit history. A proposed correction clears the active verification, preserves historical quotations and requires newer complete customer evidence and reconciliation. Current evidence is kept per message. Rerunning extraction replaces that message’s displayed advisory. Prior review decisions remain in the audit trail.

Startup extends V2 workspaces in place. Existing V2 demo cookies upgrade their associated workspace on access. Recovery accepts a V2 schema and verifies V3 receipt-to-source links, advisory evidence, corrections, revisions and quote decisions in a V3 snapshot.

## Guided workspace

The guide stores its workspace and enquiry selection in the signed browser session. It creates an isolated demo using the existing workspace action, then links the received example to the guide only when the selected scenario and original message fields agree. The enquiry's saved status drives the guidance. Employee decisions use the same revision-bound routes and quotation rules as regular work. Exiting the guide clears the selection and preserves the demo database. Switching to the original workspace clears both the guide and the demo cookie.


## Distributor showcase

The source-controlled warehouse has 14 bearings, 12 cylinders, 11 fasteners and eight adapters. The V5 catalogue edition retains the source identifiers of unchanged V4 records so an existing verified match can still be checked. No catalogue edit is applied to saved quote snapshots. Zero stock and unknown stock produce distinct holds. Harbour Packaging has a net cylinder rate of NZD 137.50. Contract Only Engineering has a sealed-bearing rate and requires an agreement on every other SKU. The other four accounts use the list price.

A single technically resolved SKU can qualify for partial supply when its sole issue is a positive stock shortfall and pricing is authorised. The employee accepts a specific quantity and reference before drafting. Approval rechecks the current evidence, stock and price against the saved decision. The snapshot records the original request, partial offer, quoted quantity, net basis and tax. A short line in a multi-product request holds the whole draft. An employee can still explicitly revise quantities on an otherwise eligible draft. The customer preview derives outstanding units from saved requested and quoted quantities.

The local demo mailbox accepts a complete revised order on an approved demo-email thread. The same transaction checks its address, subject, message identity and enquiry revision, records the inbound message and reopens technical review. It preserves historical quotes. A human reconciles the replacement request and verifies the new draft before approval. The read-only customer-preview route serves the latest approved snapshot in the active workspace. A missing approval or superseded version returns HTTP 409. The local print view has no send action or public sharing.

The schema remains compatible with existing workspaces. Recovery validates partial quotation decisions and quantities alongside the existing immutable quote, revision and receipt checks.

## V6 catalogue and customer views

Schema version 4 stores staged CSV patches and their activation lineage in the workspace SQLite file. Validation, explicit confirmation and a current base revision precede publication. Matching and pricing read the active parts inside the workflow transaction. Employee approval rechecks evidence. Previously saved quotations retain their original snapshot. Upgrade rechecks older technical decisions and records an audit event when a formerly eligible match becomes unsafe.

Customer mode reads current approved quotations for the selected fictional account. Versioned links bind the source workspace, account and quote version. A separate prepared-examples database is built through the ordinary verification and quotation transitions and published atomically. This presenter-controlled mode provides no real authentication or outbound communication.

## V7 customer quantity confirmation

The approval transaction compares quote lines against quantities in the current customer requirements. A saved draft, approval form or employee note cannot raise those limits. The confirmation action records an outbound question and retains the existing quote version. The customer must provide a complete revised request, which is reconciled and verified before a new draft can be approved. Schema version 5 rechecks existing decisions, retains the historical snapshots and records reopened approvals. The workspace-scoped warehouse directory reads only published catalogue data.
