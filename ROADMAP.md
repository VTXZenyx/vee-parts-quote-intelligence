# Product roadmap

The initial release targets a local, single-workspace employee workflow on synthetic data. One incomplete request spans parts of phases 1–7. A phase can have a working demonstration while its broader capabilities remain open. Planned dependencies and measurable exit criteria follow.

| Phase | Foundation scope | Next exit criterion |
| --- | --- | --- |
| 1. Working foundation | Flask employee queue and detail workspace, local SQLite persistence and synthetic records. | Reproduce setup in CI and on a clean workstation, exercise the employee flow, and record independent review and unresolved issues. |
| 2. Enquiry intelligence | Inspect original synthetic requests, sample attachments and structured requirements. | Parse supported documents in isolation and handle duplicate mock mailbox events, multi-item requests and replies in the correct thread. |
| 3. Industrial product intelligence | Deterministic lookup of synthetic part references and structured attributes. | Benchmark exact, attribute, semantic and image retrieval against fixed, rights-cleared, reviewed fixtures. Document recall, errors, latency and cost. |
| 4. Technical verification | Surface catalogue evidence, missing requirements and conflicting specifications. | Demonstrate category-specific verification, safe abstention and qualified escalation across the listed part families. |
| 5. Customer communication | Review a clarification draft and use a simulated reply to continue the enquiry. | Version drafts, track outstanding questions and bind authorisation to exact recipient and content. Verify sandbox dispatch and retry handling. |
| 6. Commercial intelligence | Inspect synthetic inventory and customer pricing. | Exercise freshness, approved discounts, special orders, unknown availability and supplier estimates through a supported import or authorised sandbox. |
| 7. Quotations and approvals | Review multi-line drafts, edit quantities and notes, retain quote versions and audit decisions with deterministic NZD/GST calculations. | Support complete multi-line versioned documents, partial or alternative lines, approved terms and reapproval after material changes. |
| 8. Integration and reliability | Local request controls, automated checks and a verified offline SQLite backup and restore command. | Meet the real-data security criteria, prove backup and recovery, and demonstrate approved mailbox and ERP connections. Obtain explicit deployment approval. |
| 9. Continuous improvement | Fixed author-labelled synthetic regression cases exercise the baseline. | Record independent labels, employee feedback, measured regressions and decisions for each change to retrieval, verification or pricing. |

## Sequencing

First close defects found in the employee workflow. Expand category rules, independent evaluation fixtures and mock ingestion while using synthetic data. Security qualification is a dependency for real data, provider authorisation is a dependency for real integrations, and release approval is a dependency for production deployment. Use [BACKLOG.md](BACKLOG.md) for individual tasks and acceptance criteria.

V3 delivers local Gmail and Graph fixtures, transactional duplicate handling, explicit retry of held replies and source-bound employee review. A configurable SDK adapter supports optional live text extraction. The next commercial milestone is an independently labelled distributor evaluation measuring review time, errors and model cost. Authorised mailbox and ERP pilots depend on identity, tenant isolation and data rights.

V4 brings the guided demo, employee queues, source evidence and quote review into a consistent desktop and mobile interface. The next employee milestone is an observed synthetic trial with a distributor reviewer. Record completion time, errors and blocked cases before refining broader extraction coverage.

V5 supplies five repeatable distributor scenarios and an approved customer preview. The next milestone is an observed owner and estimator walkthrough, followed by agreement on the evidence, boundaries and price of one limited pilot.

V6 added staged warehouse imports and account-specific quotation previews. V7 adds searchable products, clearer clarification rounds and customer confirmation before approving extra units. The next milestone is a first-time employee walkthrough with synthetic enquiries, including a quantity increase and a blocked technical match.
