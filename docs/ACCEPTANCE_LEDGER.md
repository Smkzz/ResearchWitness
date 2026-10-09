# ResearchWitness aggregate acceptance ledger

This public ledger contains only approved aggregate status. The detailed engineering handoff is kept separately; SHA-256 commitment: `df5bde9cd98abe63ec552aa18598807fc957619d37cdd2f62e9b1de6881c3edb`.

## Candidate identity and latest completed checks

- Repository: `Smkzz/ResearchWitness`.
- PR #12 is open, draft, unmerged and unreleased. It remains stacked on PR #11's count/percentage provenance contract v1.3.
- The latest completed pre-fix candidate was remote head `f22b721b0e6813995c433b75fbc31907ce760610`; tree: `c67c4aca678ec7d5ef7ddbc21d73b951e4a77743`.
- This update adds wrapping for long evidence-list values and a focused mobile regression for the source-hash row. Hosted checks for the updated candidate have not completed.
- Local qualification source revision for the package builds: `2e3e0c145ff599501ddb5d63b554f3bafce86eb8`; local tree: `fc587e2424b64aa469679673195514a4627940a7`. The code and test blobs in that build match the corresponding current PR files.
- Exact hosted results for `f22b721b0e6813995c433b75fbc31907ce760610`: CI run `37990561522` **failed** on the Ubuntu and Windows mobile-width assertion (document scroll width 674 px and 585 px at a 390 px viewport); CodeQL run `37990561443` **passed**. The Python matrix and release gate passed. The browser run stopped before its export/replay steps and Windows clean-wheel qualification.
- The browser and Python test modules skipped locally because this sandbox denies loopback binding; this is not browser qualification. Hosted real-browser evidence is the applicable test route.

## Engineering evidence

- Focused local UI tests: 13 run, 11 passed, 2 skipped because this sandbox denies loopback binding.
- Local browser module: 3 cases skipped because this sandbox denies loopback binding. These are not browser qualification results.
- JavaScript syntax check, Python bytecode compilation and `git diff --check`: passed on local revision `2e3e0c145ff599501ddb5d63b554f3bafce86eb8`. The pending responsive patch has passed the same syntax and diff checks; local UI and browser modules still skip because this sandbox denies loopback binding.
- Reproducible source archive: 4,901,198 bytes, SHA-256 `8cfde55b89fece68e108efc12657bea2066891cf59132ffd2f7303f56f146340`.
- Reproducible release wheel: 269,545 bytes, SHA-256 `74c141dce49206401c65357398e9907b07cd545607efaeb365ce788e6712092b`.
- Independently rebuilt wheel: two clean builds were byte-identical; wheel SHA-256 `f0d42921d25a76bd4fa8da3b63c121eaed6385fedeb9eebd36ca1919b1d3726f`; offline isolated installation and CLI/resource smoke test passed.
- The two release-output directories matched byte-for-byte: release manifest SHA-256 `fc021e28cd0066f0c3311a47e6f3644df2b441fb7e6bb9d403f8774039d02c10`, sums file SHA-256 `37971a37a9797ede9568799b74e63afa256ce590b47b1baf1b24edf586c89d44`.
- Synthetic offline custody-worker v5 artifact SHA-256 remains `62931b5e2999d8744bbcd9ca9b6e34b8add4f9d4a4ede56aa79ced6d4f08b72e`.
- These checks use synthetic data. They do not establish scientific detection performance, Windows custodian qualification, or enforced host egress isolation.

## Scientific gate

The inherited aggregate record reports zero confirmed untouched eligible correction-backed positives and 363 eligible correct negative relationships across five DOI document IDs. The frozen minimums are at least one untouched eligible positive and 50 eligible negatives across 15 independent works. The minimums remain unconfirmed. No Wave 3 run has occurred.

## Ten-category status

| Category | Evidence and current status | Remaining gate |
| --- | --- | --- |
| Product usefulness | Local upload, candidate review and source anchors ran in hosted Chromium; the mobile-width overflow stopped the journey before export/replay. **BLOCKED** | Re-run the complete browser journey after the responsive fix; normal-user usability has not been fully assessed. |
| Scientific correctness | Count/percentage provenance v1.3 and synthetic source-mapped regressions remain the declared narrow contract. **BLOCKED** | Frozen positive and 15-work negative minima, exact source eligibility and independent adjudication remain unconfirmed. |
| Security | Synthetic attack regressions are recorded; CodeQL passed on `f22b721`. **BLOCKED** | Run CodeQL on the patched head; shared-host boundary and custodian effective-access qualification remain open. |
| Privacy | Application exports and package selection have synthetic checks; no public source retrieval occurred in this work. **BLOCKED** | OS custody isolation, independent egress enforcement and owner-side access checks remain unverified. |
| UX and accessibility | Hosted browser QA found horizontal overflow at a 390 px viewport; a wrap fix and focused regression are pending hosted review. **BLOCKED** | Confirm responsive layout on Windows and Ubuntu; no human screen-reader assessment is claimed. |
| Reliability | Synthetic cancellation, restart, duplicate, retry and history-size regressions are present. **BLOCKED** | Re-run Windows and Ubuntu browser suites; the failed run did not reach later export/replay checks or Windows wheel qualification. |
| Performance and cost | Existing synthetic diagnostics are descriptive only. **NOT_CLAIMED** | Representative workload budgets, tails and full-job memory/disk measurements are not qualified. |
| Installation and portability | Two clean local builds and offline install smoke tests passed on local revision `2e3e0c1`; hosted Python/release jobs passed on `f22b721`. **BLOCKED** | Requalify the patched candidate; Windows app-wheel and custodian installation/rollback evidence remain outstanding. |
| Maintainability and reproducibility | Release allowlists, generated source checksums and byte-identical artifact rebuilds are recorded. **BLOCKED** | Current hosted release gate passed on `f22b721`; rerun it on the patched candidate. |
| Documentation and release quality | Scope limits, private-evidence exclusions and unmerged draft status are stated. **BLOCKED** | No public release is qualified; current hosted checks and required scientific/custodian gates remain open. |

The public result is an engineering candidate, not a qualified research-preview release. Do not merge, publish findings or run Wave 3 while the scientific and custody gates remain unmet.
