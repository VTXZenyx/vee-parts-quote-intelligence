# Changelog

## 2026-11-20 · Industrial distributor showcase

Added the 45-SKU Hamilton warehouse, five isolated guided scenarios and a printable approved customer preview. Stock-limited single-line quotations require explicit employee acceptance and preserve the balance outstanding. Complete revised customer orders retire the old approval and require reconciliation and a new technical and commercial decision. The enquiry now shows the request and blockers before optional evidence and histories. See [the presenter script](SHOWCASE.md).

## 2026-11-20 · Professional employee workspace

- Added compact queue filters, stage counts, a keyboard skip link and active navigation.
- Added a guided Harbour Packaging demo that runs in an isolated workspace and follows actual employee decisions.
- Separated fictional email, provider fixtures and delivery history. Added source links, findings provenance, visible uncertainty and separate controls for processing and review.
- Split requested and quoted quantities, clarified the total and GST, and improved narrow-screen and A4 quotation layout. Rejected drafts display the recorded reason.
- Fixed the disabled approval button after reverting an edit by hand. Added recovery links for missing enquiry and delivery pages.

## 2026-11-20 · Intelligent enquiry processing

Added offline Gmail and Outlook receipts, source-bound findings, optional model extraction and auditable employee corrections. Recovered replies follow accepted conversation order even when their receipt numbers differ. Backup checks validate provider ownership and saved findings. The employee can recover an early reply, inspect its evidence, verify two cylinders and approve the NZD 316.25 sample quotation.

## 2026-11-18 · Synthetic employee workflow

Recovered the uncommitted Flask and SQLite application from the interrupted development session. The branch includes candidate evidence across four industrial families, mock commercial records, technical and clarification review, a printable versioned NZD quotation and a transactional audit trail.

- Fixed a restore check that accepted corrupted JSON or incomplete audit history in a structurally valid SQLite database.
- Added a synthetic intake form with idempotent receipt, collision detection, server-side account validation and atomic creation of enquiry and audit records.
- Added an unidentified fitting photograph fixture. Opening the photograph leaves specification and pricing decisions under the existing evidence and approval rules.
- Independent review of the initial implementation identified stale technical evidence, silently discarded same-family items and approval with unsaved edits. The recovered code blocks those cases. Browser testing also found an origin-policy conflict and a narrow-screen overflow, both corrected.
- The recovery baseline ran 30 tests with two failing backup subtests. After corrections and intake coverage, 33 tests passed and all 51 author-labelled industrial regression cases passed. Chromium exercised intake, photograph display, confirmation, rejection, revision, print layout and approval. Lint and type checks passed locally. Real connectors and authenticated multi-business operation remain open.

### Full-system audit

The audit reproduced the original 33-test and 51-case baseline, then added coverage for unsafe product allocation, uncertain subject requirements, pressure limits across replies and recovery of historical approvals. Technical decisions retain the reviewed specifications and provenance. A one-time upgrade reopens unsafe cached decisions with an audit event and keeps their quote history. Database write failures now explain how to recover. Long subjects wrap on small screens. The verified audit totals and commands are in [TEST_PLAN.md](TEST_PLAN.md).

## V2 offline demonstration

- Added a Demo Email Inbox with editable fictional envelopes, eight inbound scenarios, two reply examples and replay controls.
- Linked replies to the selected enquiry and its current revision. Delivery, verification and approval history use the original SQLite workflow.
- Added a separate seeded demo workspace, dashboard review queues, enquiry progress and action guidance, plus explicit requested and quoted quantities.
- Added regression coverage for concurrent duplicates, conflicting IDs, unrelated threads, technical and commercial holds, stale forms, audit rollback, recovery and workspace preservation.
