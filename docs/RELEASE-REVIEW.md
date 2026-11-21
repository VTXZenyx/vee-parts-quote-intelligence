# V7 public repository review

Reviewed merged V7 at `25782d1f188543b29f1f1a9bc4f0e58090e407e9` (PR #8). The readiness changes cover documentation, screenshots, ignored local files and one invalid-address test fixture. Application behavior and database schema are unchanged.

## Publication decision

**Keep private pending owner review.** A personal contributor address is present in Git author/committer metadata. Publishing the repository would disclose it, including from old commits. The owner needs consent from the affected contributor or a separately authorised plan to address the historical metadata. Changing the current files or future Git configuration cannot remove it.

The owner also needs to confirm redistribution rights for the visual assets and choose a licensing position. Check the final main-branch Actions job, including its Chromium step, in GitHub before signing off. The GitHub API denied access to the run result during this review.

| Criterion | Score | Basis |
| --- | ---: | --- |
| Secret and personal-data exposure | 25/35 | No confirmed credentials found. Historical contributor email requires a decision. |
| Asset and code rights | 10/20 | Dependency terms identified. Project grant and visual provenance need owner review. |
| Installation and local defaults | 15/15 | Clean Python 3.12 install, first startup, loopback binding, seed records and offline gates checked. |
| Regression verification | 17/20 | Local suite, evaluations and Chromium passed. Hosted result unavailable. |
| Visitor documentation | 10/10 | Illustrated overview, five scenarios, runnable commands, limitations and rights status. |
| **Total** | **77/100** | The privacy and rights decisions are publication gates regardless of score. |

## Security and privacy evidence

Fetched all advertised branch heads and tags into a full clone, including the separate mock-mailbox branch. Inspected 47 reachable commits, 362 unique blobs and 100 historical paths before the readiness changes. Checked commit messages and identities, filenames, text and credential-like literals. Patterns covered private keys, common provider tokens, bearer and connection strings, password assignments, emails, phone numbers and machine-specific paths. Checked binary types and compared both existing raster assets to their generated source images. This scope covers Git objects reachable from the available refs. GitHub issues, Actions logs, deleted remote refs and third-party forks are outside that evidence.

- The credential-like SDK literals are test doubles. Other long fixture values represent encoded mock messages, a namespace UUID and evaluation IDs. No usable key, credential file, tracked database, log, cache or confirmed customer record was identified.
- A historical email validation test uses a non-reserved domain. Its purpose is evident from the rejection assertion. The current test now uses reserved example.org. The old spelling survives in Git. The local-path detector's research-document hit was part of a Google documentation URL.
- The intended local server bound only to 127.0.0.1:5050, debug off. A foreign Host header returned HTTP 400. Flask uses a runtime-generated session key and state changes use form tokens. The local SQLite database and backups contain the entire workspace and have no application-level encryption.
- A fresh install ran with no configuration. With no settings, and separately with only a dummy API key, the live extractor stayed disabled. Live mode requires an explicit flag, key, optional SDK and employee submission. SDK tests use offline transports. No paid API call was made.
- Dotenv files, SQLite databases and sidecars, demo directories, logs and common private-key formats are now ignored. Ignore rules only affect untracked files. Keep synthetic data on a trusted machine.

## Assets and software rights

| Material | Evidence and release implication |
| --- | --- |
| Machined-parts banner and fitting photograph | The two tracked WebP files correspond visually and numerically to the generated source PNGs in the working environment after resizing (normalised pixel RMSE below 0.016). The repository supplies no rights record for those originals. Confirm the generating account's applicable commercial terms and authority to publish. |
| SVG icons and branding | The local sprite contains simple path shapes. Its introduction is traceable in Git. No external source, attribution or licence declaration was located. Obtain the creator's provenance confirmation or secure a documented replacement before public redistribution. |
| V7 screenshots | Captured from Chromium against a disposable seeded SQLite database, using one synthetic bearing request for the draft and approved document. Five metadata-stripped WebPs show actual V7 pages. The screenshots inherit the rights considerations of visible branding and artwork. |
| Synthetic catalogue, conversations and research | The fixtures describe fictional accounts and stock. Research links cite other projects. The research record states that external datasets, model weights and implementations were not incorporated. Owner confirmation of project ownership remains appropriate. |

The locks reference packages installed from the index. The repository does not vendor their wheels, browsers or source trees. Installed distribution metadata for the pinned application, optional and verification sets reported these terms:

| Licence family | Distributions |
| --- | --- |
| BSD | Flask, Werkzeug, Jinja2, MarkupSafe, itsdangerous, click, httpcore2, httpx2, idna |
| MIT | blinker, annotated-types, anyio, ast-serialize, h11, jiter, librt, mypy, mypy-extensions, pydantic, pydantic-core, pyee, ruff, truststore, typing-inspection |
| Apache-2.0 | openai, playwright |
| PSF-2.0 or combined | typing-extensions (PSF-2.0), greenlet (MIT and PSF-2.0) |
| Other | pathspec (MPL-2.0), sniffio (MIT or Apache-2.0) |

These are package-level declarations. If distributing a bundled installer, browser, binary or modified library, review its included third-party notices, retain required notices and satisfy applicable source obligations. The runtime has one direct application dependency, Flask. The SDK is optional, Ruff and mypy support development checks, and Playwright supports browser tests.

No project-wide software licence was present or added. The owner can choose a permissive open-source grant (others may use the code commercially under its terms), a source-available grant with explicit restrictions, or a proprietary showcase with no general reuse grant. Public visibility permits viewing and GitHub platform uses such as forking under its terms. Decide what users may do before changing visibility.

## Verification

A clean local clone and fresh Python 3.12.14 virtual environment installed the documented runtime, development and browser dependencies. The dashboard returned HTTP 200 with six seeded enquiries. Opening the default database, making a verified backup and restoring it worked. This exercise found an incorrect database path in the old README and backup example. Both now use the location observed with the documented module command.

Ruff and mypy passed (15 source files). All 116 unit/integration tests passed. Catalogue evaluation passed 117/117 cases and 24/24 quote totals, with zero false verified references or unsafe-ready cases. Extraction passed 32/32 cases in each offline mode. Chromium passed all five scenarios, quantity safeguards, catalogue import and customer-preview workflows. The five expected outcomes are listed in the README. These are local synthetic results.
