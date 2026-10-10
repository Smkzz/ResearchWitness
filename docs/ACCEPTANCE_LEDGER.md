# ResearchWitness acceptance ledger

This public ledger contains only engineering evidence and permitted aggregate results. It contains no reserve identities, paper/source records, correction targets, evaluation labels, private configuration, or owner-only qualification notes. The earlier private-handoff commitment remains `df5bde9cd98abe63ec552aa18598807fc957619d37cdd2f62e9b1de6881c3edb`; the commitment does not reveal or publish that handoff.

## Candidate and hosted checks

- Repository: `Smkzz/ResearchWitness`. PR #12 is open, draft, unmerged, and unreleased, stacked on PR #11 (denominator-provenance contract v1.3).
- The mandate snapshot listed PR #12 at `92891ce0d343e6f9517b806efafa5da6d6552f21`. PR #11's base head is `6843593ff443d4a44c48d15a76949b323d0951ca`. The sanitized PR #12 code/test candidate is commit `065fcfa6c5bd57f65d13ba118df4215357a344b4`, tree `c26195093ce2efe9e7199246c17471d794cff07d`, parent `d8d08ca8b7c395d64dda8a2f8d0f01be466962f7`. The same code/test tree was qualified locally at commit `f785144ba865fd6374636b6aefcd3640a6994c28`; subsequent PR commits only update public qualification records.
- Hosted CI [run 38015056711](https://github.com/Smkzz/ResearchWitness/actions/runs/38015056711) and CodeQL [run 38015056745](https://github.com/Smkzz/ResearchWitness/actions/runs/38015056745) passed on the exact PR tree. CI passed Python 3.11–3.13, offline release qualification, reproducible wheel and synthetic custody package checks, synthetic Windows custody-worker tests, and the Linux and Windows Chromium jobs. An earlier browser run exposed that a test's string-based wait violated the app's Content Security Policy; the test now waits for the same DOM state through a locator, and both hosted browser suites pass.
- The hosted Windows and Ubuntu Chromium jobs cover synthetic upload, candidate and source display, export/replay/history, retry, deletion, cancellation/status races, keyboard smoke checks, responsive widths, stale-duplicate notice clearing, and display/export parity for source byte ranges after a multibyte prefix. Their screenshots were retained for review but were not visually previewed here.
- Baseline screenshot ZIP digests were `3b292b2c153fde425fbcd3756925efc16007013d4826d77f437f96b30f6f115d` (Windows) and `4e209f57fada3c7e231157ff77840917c467c84ac31196133f280fe89d0a3d2d` (Ubuntu), with one-day retention. The images were not visually previewed here. Browser DOM and keyboard checks do not establish screen-reader announcement, human accessibility, or WCAG conformance.

## Exact-source local checks

- On code/test tree `c26195093ce2efe9e7199246c17471d794cff07d`, `tools/quality_gate.py` passed: **833 tests passed, 11 skipped, 4 subtests passed**, 500/500 synthetic cases matched, 3/3 historical MVP cases matched, and static scan, schema checks, checksum checks, compile, and CLI smoke checks passed. Four loopback tests were denied by the managed sandbox, six Playwright tests were skipped locally and passed in the hosted Linux/Windows runs above, and one native-Windows PDF resource-limit test is skipped locally.
- `tools/qualify_app_wheel.py` built two identical wheels, then passed clean-target installation and CLI/resource smoke checks. Qualified wheel SHA-256: `551df5e32c54c0ebbb0e2b9d7d65abc5b19d551cd337aefec7cbe35c1285ac56`.
- `tools/make_release.py` produced byte-identical outputs in two clean runs. The deterministic source archive SHA-256 is `bb298797fd7c12b60ab75bbe1d5e5d7096fc7da7cb86a7823eb0733ebf968921` (4,946,838 bytes); release wheel SHA-256 is `436d7656b3883ed88bacaeea05c58a89bed57a72bc3753f63e8003af4c9e2d32` (279,462 bytes). The separately qualified wheel uses the source commit's build epoch; the release bundle uses the fixed release epoch.
- The offline custody zipapp was built twice from clean synthetic source copies. Bytes and member hashes matched; its synthetic CLI flow passed and below-threshold public export was refused. SHA-256: `25b4802c1636fdbe2bd2185eeb2179a38d7fc80b2c4cc56e82d3ca91d913c9d2`. It is not a production installer and was not installed into a protected environment.
- Synthetic JATS budgets were declared before measurement. Five process-isolated trials on Linux/Python 3.12.14 passed the declared bounds for small, medium, large, named-entity, and malformed-depth cases. Results are in `docs/qualification/jats-performance-results-20261010-offset-map.json`; script, budget, source-input and result hashes are recorded in the qualification record. These measurements do not establish real-paper or production performance.

## Scientific and custody readiness

- Historical public aggregates report zero confirmed untouched eligible correction-backed positives and 363 eligible negative relationships across five DOI document IDs. Five IDs do not establish 15 independent works. The frozen minimum of one untouched eligible positive and at least 50 eligible correct negatives across 15 independent works is not confirmed.
- No scientific source was acquired in this development environment, no reserved case was run, and Wave 3 was not executed.
- Regression coverage now treats NBSP/NNBSP-spaced count ranges/fractions as unsupported/incomplete, recognizes US/UK standardization morphology across the relevant detectors, and counts fullwidth-slash and ranged JATS ratio lookalikes as skipped relations. All supported numerical outputs remain review candidates and do not prove a paper error.
- The v5 worker is a reproducible offline development artifact. Its public aggregate is not independent-work qualification. No production installation, migration, activation, or rollback qualification occurred. Preserve the existing worker and records.
- No technically isolated custodian executor is available here. Effective access, separation of duties, retention/output paths, and independent egress enforcement remain unqualified. This public ledger does not disclose the owner’s private deployment configuration.
- The Codex Security scan-start operation is not exposed in this environment. CodeQL and scoped engineering reviews are not a complete security certification.
- No additional spending, merge, release, public research finding, researcher contact, or Wave 3 execution occurred.

## Ten-category acceptance matrix

| Category | Status | Evidence and remaining gate |
| --- | --- | --- |
| Product usefulness | **BLOCKED** | Local-first CLI and synthetic browser workflow exist. Current hosted browser checks and human first-launch review remain. |
| Scientific correctness | **BLOCKED** | Synthetic source-span/arithmetic regressions pass. Untouched-positive and 15-independent-work negative minima are unmet; no Wave 3. |
| Security | **BLOCKED** | Baseline CodeQL passed; changed-code reviews drove fixes. Fresh CodeQL and broader authorization, persistence, export and deployment review remain. |
| Privacy | **BLOCKED** | No research source entered this environment. Custodian separation, effective access, retention/output controls and enforced egress are unqualified. |
| UX/accessibility | **BLOCKED** | Updated Windows/Ubuntu browser CI passes. Screenshots were not visually previewed; no human screen-reader/AT or WCAG review. |
| Reliability | **BLOCKED** | Local regression suite and updated hosted retry/replay/recovery flows pass. Protected-store recovery remains unqualified. |
| Performance and cost | **NOT_CLAIMED** | Declared synthetic Linux budgets passed with limited scope. No broader performance claim; no additional spending. |
| Installation and portability | **BLOCKED** | Current Python 3.11–3.13 CI and Windows app-wheel check pass. Protected installation remains unqualified. |
| Maintainability and reproducibility | **BLOCKED** | The sanitized source snapshot passed the full offline gate and reproducible app/release/zipapp builds. Fresh hosted checks and a verified forward remote identity remain. |
| Documentation and release quality | **BLOCKED** | Scope, exact candidate identity, artifact hashes, and hosted results are recorded. Human review and protected deployment qualification remain. Keep PR draft and unreleased. |

PR #12 remains an engineering candidate, not a qualified research-preview release. Keep it draft and unmerged until the scientific, security, privacy, product, and custody gates pass.
