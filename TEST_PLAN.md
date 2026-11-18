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
