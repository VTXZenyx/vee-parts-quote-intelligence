# Working on VEE

Read [README.md](README.md) for local setup, [ARCHITECTURE.md](ARCHITECTURE.md) for current boundaries and [BACKLOG.md](BACKLOG.md) for the next work item. Inspect the repository and branch before changing either. Work through development branches and pull requests.

## Engineering decisions

- Use synthetic industrial records and mock services during prototype development. Keep real emails, customer data, credentials and supplier records out of fixtures, logs and Git.
- Keep catalogue retrieval, technical verification, commercial inputs, money calculations and employee decisions distinguishable in code. A model suggestion or photograph cannot certify compatibility. Preserve uncertainty, evidence and the path to clarification.
- Enforce approval and state transitions on the server. Validate inputs even when a form limits available choices. Preserve history through retries and failures. Keep a decision and its audit event consistent.
- Calculate money with deterministic decimal or integer arithmetic. Declare currency, rounding point and tax treatment. Unknown prices, stock and lead times must retain their meaning.
- Research before adopting third-party code. Inspect source, dependencies, licence, maintenance and data terms. Record the evidence in [RESEARCH.md](RESEARCH.md). Review external code before installing or executing it. Keep credentials inaccessible to research tooling.
- Use the existing module boundaries where practical. Document important architecture changes and the reason. Prefer achievable, testable increments that advance an employee workflow.

## Verification for every meaningful feature

1. Inspect the whole diff and the normal entry points. Check validation, errors, state consistency and security. Run applicable syntax, lint and type checks.
2. Exercise the feature in the running app. Run automated tests and regression cases for real entry points, persistence, malformed and repeated input, approvals and commercial arithmetic. For UI work, include a browser interaction and visual inspection where available.
3. Perform a separate critical review, using an independent reviewer where available. Examine unsupported matches, stale evidence, approval bypass, incorrect totals, tenant access and untrusted inputs. Fix findings and rerun affected checks.

Record actual commands, outcomes, simulation boundaries, skipped checks and remaining limitations. Update the changelog, roadmap, backlog and relevant product or test documentation when behaviour changes. Each backlog item needs observable acceptance criteria.

## Handoff and authority

A pull request should describe what works, why it changed, tests passed, failures or checks that could not run, simulated components, security considerations, limitations and next priorities. Preserve the exact blocker when credentials, network, permission or an unavailable service prevents verification. Continue independent local work when possible. Obtain explicit approval for real communications, sensitive credential use, protected-branch merges and production deployment. Keep failing changes out of the main branch.
