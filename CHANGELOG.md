# Changelog

## 2026-11-18 · Synthetic employee workflow

Recovered the uncommitted Flask and SQLite application from the interrupted development session. The branch includes candidate evidence across four industrial families, mock commercial records, technical and clarification review, a printable versioned NZD quotation and a transactional audit trail.

- Fixed a restore check that accepted corrupted JSON or incomplete audit history in a structurally valid SQLite database.
- Added a synthetic intake form with idempotent receipt, collision detection, server-side account validation and atomic creation of enquiry and audit records.
- Added an unidentified fitting photograph fixture. Opening the photograph leaves specification and pricing decisions under the existing evidence and approval rules.
- Independent review of the initial implementation identified stale technical evidence, silently discarded same-family items and approval with unsaved edits. The recovered code blocks those cases. Browser testing also found an origin-policy conflict and a narrow-screen overflow, both corrected.
- The recovery baseline ran 30 tests with two failing backup subtests. After corrections and intake coverage, 33 tests passed and all 51 author-labelled industrial regression cases passed. Chromium exercised intake, photograph display, confirmation, rejection, revision, print layout and approval. Lint and type checks passed locally. Real connectors and authenticated multi-business operation remain open.
