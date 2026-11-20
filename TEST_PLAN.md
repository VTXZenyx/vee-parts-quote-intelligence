# Verification and industrial evaluation plan

The foundation uses local synthetic fixtures. Production acceptance requires independently reviewed examples and authorised integration tests. Record commands, environment, dataset version, actual outcomes, failures and limitations for each verification run. The README contains runnable project commands.

## Executable foundation coverage

Run `python -m unittest discover -v` from the repository root in the configured Python environment. The test suite reads [the fixed synthetic cases](evaluation/cases.json). Catalogue checks compare expected status, SKU and quote eligibility per case and, when specified, extracted attributes, clarification fields and total. The store tests cover revision conflicts between simultaneous edits, transaction rollback on audit failure, multi-line verification, rejection and resubmission. The route tests exercise queue search and HTTP request protections. The offline backup tests compare restored quotes, audit events and revisions to the point-in-time record, including a committed write-ahead-log change. They also exercise corrupt input, foreign-key failures and competing writes to the same destination. See the project verification record for actual run outcomes.

The ENQ-1042 scenario gives a commercial cross-check. The synthetic reply supplies a 32 mm bore, 100 mm stroke, double acting operation, ISO 15552, G1/8 ports and a foot mount. At the seeded Harbour Packaging price, two units total NZD 316.25 including GST. A regression case also checks three bearings at NZD 12.75 each, for NZD 38.25 net, NZD 5.74 GST and NZD 43.99 gross. These expected outcomes describe the synthetic fixture.

## Three verification stages

| Stage | Work | Required evidence |
| --- | --- | --- |
| Implementation review | Inspect the entire change and all normal entry points. Check dependency changes, syntax, types, lint, validation, transaction boundaries, data provenance and error paths. | Commands and results, review findings and disposition. |
| Functional and integration tests | Run unit and workflow tests against an isolated database. Run the app and exercise the main flow in a browser. Include malformed inputs, missing data, stale or repeated requests and persistence after restart. | Command output, observed states, regenerable fixtures, browser result and any unavailable checks. |
| Independent critical review | Have a separate reviewer trace unsafe matches, pricing mistakes, stale stock, unauthorised approval or sending, prompt injection and cross-business access. Examine whether the workflow solves the distributor’s actual problem. | Findings with severity, remediation, retest evidence and outstanding limitations. |

## End-to-end acceptance checks

1. Open a fresh synthetic workspace. Find the incomplete enquiry, open its original message and attachment, and inspect each requested product, candidate, missing attribute and warning.
2. Attempt technical or commercial approval while required information is missing. Verify the server keeps the same state and presents the unresolved condition. Repeat by directly exercising the normal request handler.
3. Review and reject a clarification or recommendation. Capture the reason and audit history. Edit or review a new draft, approve it, and observe the mock communication result. No network delivery should occur.
4. Supply the synthetic customer reply. Confirm the correct enquiry receives it and the employee can inspect the additional requirements and corresponding candidate evidence. A conflicting reply should block technical verification.
5. Review the match, stock, customer price and draft. Change editable terms, recompute the expected subtotal, GST and total independently, then approve. Confirm every displayed amount agrees with the persisted version.
6. Reopen the enquiry after restart. Verify status, decisions and event order. Replay an old action and submit two competing changes. Neither may silently overwrite an approved decision or duplicate an irreversible effect.
7. Check queue search, empty results, form errors, keyboard operability, focus indicators, narrow-screen layout and long reference numbers. Account for every visible control and simulated feature.
8. Before enabling business data, test two tenants and multiple roles across all storage and exports. Verify document access, secrets handling, logging and restore. Before enabling external dispatch, test approval binding and idempotency with a provider sandbox.

## Fixed industrial evaluation cases

Use stable identifiers for each fixture and freeze source records with a dated version. Separate retrieval from verification and quote eligibility. The expected outcome for a near-match may include plausible candidates while still requiring escalation.

| Case family | Expected outcome examples |
| --- | --- |
| Exact, incomplete or incorrect part number | Retrieve an exact supported reference with evidence. For partial, transposed or conflicting references return candidates and identify uncertainty. |
| Photograph, worn marking or damaged label | Recognise supported attributes where possible. Request a legible view or measurement for remaining requirements. Do not infer an unreadable part number. |
| Similar appearances, incompatible fittings | Distinguish visually alike variants using verified attributes. Check metric, BSP and NPT thread forms, diameters, pitches and pressure ratings as applicable. Escalate an unsupported substitution. |
| Missing and conflicting specifications | Surface missing dimensions, incompatible materials, load or tolerance conflicts, including disagreements between a message and an attachment. Require clarification or a qualified reviewer. |
| Discontinued reference | Preserve the original request and discontinued status. Treat a proposed successor as a candidate until required evidence and approval exist. |
| Multiple lines, quantity changes or ambiguity | Preserve distinct items and units. Reject zero, negative, fractional counts for indivisible units and excessive inputs. Clarify conflicting quantities or ambiguous descriptions. |
| Commercial uncertainty | Test insufficient and unknown stock, unknown supplier availability, stale prices and absent customer-specific pricing. The quote must not fabricate a value, delivery promise or substitute item. |
| Customer reply | Associate the reply with the right thread, retain original evidence and reconsider approvals affected by a changed requirement. Replayed deliveries must not duplicate work. |
| Malicious email or attachment content | Treat embedded instructions as customer-supplied text. They cannot change access, approve a part, modify pricing, retrieve secrets or trigger dispatch. |
| Arithmetic | Independently compute known net, GST and gross values, including rounding boundaries, multiple lines, supported discounts, missing inputs and currency restrictions. |
| Human escalation | A high-risk or ambiguous application remains open with the blocking reason. A customer assertion or unreviewed model output cannot substitute for employee authority. |

## Labelling and measurement

A qualified reviewer establishes expected product IDs, allowed alternatives, technical blockers, missing fields, acceptable questions and required escalation using dated catalogue evidence. A second reviewer adjudicates disputed labels. Keep a held-out set, prevent evidence leakage, and record reviewer, changes and reasons. Fixture-author labels can support deterministic regression checks while independent validation is pending.

Report numerator, denominator and failures per component family. Track identification accuracy and top-k retrieval recall, attribute extraction accuracy including units, false exact-match recommendations, unsupported compatibility claims, missing-field detection precision/recall, deterministic quotation accuracy, workflow completion reliability, response time (median and p95), provider cost per enquiry and newly failing regressions. Include abstention and escalation rates so silence cannot inflate apparent accuracy. Report unavailable metrics explicitly. Any unsupported approval, incorrect golden total, unauthorised dispatch or tenant leak fails the release gate for the affected capability.

## Recovery verification on 18 November 2026

From the repository root with the documented environment installed, the following commands passed locally.

```sh
.venv/bin/ruff check vee tests scripts evaluation
.venv/bin/mypy --check-untyped-defs vee evaluation
.venv/bin/python -m unittest discover -v
.venv/bin/python -m evaluation.run
.venv/bin/python -m scripts.browser_smoke
```

The suite ran 33 tests. The fixed catalogue evaluation passed 51 cases and matched 7 independently specified expected totals. These are synthetic, author-labelled cases. In Chromium the incomplete cylinder order reached NZD 316.25, was rejected, revised to three cylinders at NZD 474.38 and approved. The smoke test also checks a new enquiry, an actual viewable synthetic photograph, saved status, edit guards, print rendering and narrow-screen width. The backup CLI tests exercise both corrupted and valid snapshots.

## Full-system audit of the first synthetic milestone

The audit started from the clean GitHub feature branch at `b9520a0`. All 33 existing unittest methods, all 51 original author-labelled cases and their seven price totals passed. The original Chromium workflow, lint and type checks also passed. An independent review then reproduced acceptance errors outside that coverage.

| Check after fixes | Command from the repository root | Observed result |
| --- | --- | --- |
| Backend, HTTP, database and recovery | `.venv/bin/python -m unittest discover -v` | 45 tests passed, including 12 backup tests. |
| Fixed catalogue benchmark | `.venv/bin/python -m evaluation.run` | 61/61 cases and 9/9 golden totals. All 77 line identities or abstentions matched expectations. Zero unsafe ready decisions in these fixtures. |
| Employee journeys using a disposable live server | `.venv/bin/python -m scripts.browser_smoke` | Chromium exercised intake, the static attachment, customer and employee revisions, stale tabs, required confirmations, evidence refresh, rejection, unsaved changes, approval, A4 quote generation and commercial holds. Long subjects were checked at five viewport sizes. |
| Code and installed dependencies | `.venv/bin/ruff check vee tests evaluation scripts`, `.venv/bin/mypy --check-untyped-defs vee evaluation`, `.venv/bin/python -m pip check` | Passed. PyPI’s version-specific metadata returned zero non-withdrawn advisory IDs for the 17 pinned Python packages on the audit date. |

The cylinder journey produced NZD 316.25 for two units and NZD 474.38 for the approved three-unit revision. A separate arithmetic cross-check used integer cents for quantities 1–3 across every ordered pair of five synthetic SKUs on the Harbour Packaging account. All 225 subtotals, GST values and gross totals matched.

Review reproduced incorrect eligibility when technical conditions appeared only in a subject, when a revised request omitted the earlier pressure requirement and when assembly counts were ambiguous. Backup review found that consistent SQLite pages could still contain inconsistent financial or approval records. Browser inspection found overflow on valid long subjects. Regression tests cover these failures and database write rollback. The suite uses real local HTTP and SQLite and simulated business records. Production identity, external dispatch, arbitrary file intake, live technical data and business continuity remain separate acceptance gates.

### Audit closeout

The last independent review found that subject matching could accept `500 bar` inside `0.500 bar`. The matcher now requires a complete measurement. Startup also rechecks earlier approvals and records a new review event where necessary. The original quote and approval history remain available.

The focused command `.venv/bin/python -m unittest tests.test_intake tests.test_store tests.test_backup -q` passed 37 tests after the fix. Ruff, mypy and `git diff --check` passed. A separate upgrade drill created an incorrect approval with commit `6334db9`, then confirmed that the updated code reopened the enquiry and preserved its audit and quote history through backup, restore and restart. The existing full-suite, evaluation and Chromium results above were recorded before this narrow fix.

## V2 offline email and employee workflow

Run the existing checks from the repository root:

```sh
.venv/bin/ruff check vee tests evaluation scripts
.venv/bin/mypy --check-untyped-defs vee evaluation
.venv/bin/python -m unittest discover -v
.venv/bin/python -m evaluation.run
.venv/bin/python -m scripts.browser_smoke
```

`tests/test_demo_mail.py` checks envelope validation, concurrent idempotent delivery, thread and address binding, stale revisions, replay after a state change, clarification and approval gates, revised pressure, ambiguous quantities, unavailable stock, database rollback, backup, restart and workspace isolation. `scripts/browser_demo.py` drives the cylinder email through clarification, a reply, employee review and NZD 316.25 quote approval. It checks duplicate replay, the unavailable adapter hold, isolated workspace return, and narrow-screen interactions. The V1 browser cases still cover direct intake, quotation versions, responsive overflow and A4 printing.

The V2 local run passed 54 automated tests, all 61 synthetic evaluation cases and all nine labelled quotation totals. Ruff, mypy, dependency consistency and the live Chromium smoke test passed. Desktop dashboard and inbox layouts and the mobile enquiry view were visually inspected.

## V3 intelligent enquiries

Final local verification used Python 3.12 and Chromium with fresh temporary SQLite databases. Commands are relative to the repository, using executables in `.venv/bin`.

| Command | Observed result |
| --- | --- |
| `ruff check vee tests evaluation scripts` | Passed |
| `mypy --check-untyped-defs vee evaluation` | Passed for 11 source files |
| `python -m unittest discover -v` | 76 passed |
| `python -m unittest tests.test_backup tests.test_provider_mail -q` | 24 passed, also included in discovery |
| `python -m evaluation.run` | 61/61 cases, 77/77 SKU decisions or abstentions, 9/9 quoted totals, 0 unsafe-ready outcomes |
| `python -m evaluation.enquiries` | 16/16 author-labelled message cases in deterministic mode and 16/16 in mock mode. Each matched all 16 expected reference lists and all 13 labelled whole-message quantity lists, including abstentions. |
| `python -m scripts.browser_smoke` | Passed V1, V2 and provider workflows, duplicate replay, quote history, printing and mobile layout assertions |
| `python -m pip check` | Dependency consistency passed |

The provider tests cover concurrent delivery, equal subjects, changed subjects, forwards, unknown or conflicting identifiers, new requests inside existing conversations, database failure rollback, late parents, successive replies and invalidation after approval. A V2 snapshot was restored, upgraded, imported into and copied again. Replaying the delivery on the recovered database preserved the enquiry. Chromium recovered an early Gmail reply while an independent Outlook request shared its subject, recorded a mock extraction and employee review, and approved the NZD 316.25 quote. The desktop provider inbox and narrow-screen evidence view were also inspected visually.

Regressions caught while implementing V3 included counting a subject as a second product, linking a third email by receipt order after recovering its parent, accepting a partial numeric source as evidence for a pressure, and restoring a receipt or finding with the wrong source. The SDK tests use the installed client and an in-memory HTTP transport, including a valid structured response, rate limiting and timeout. No live inference, provider credentials, mail delivery or real business records were used for verification. The 16 message cases are reused across local modes. Neither that comparison nor the 61 catalogue fixtures measure industrial field accuracy.
