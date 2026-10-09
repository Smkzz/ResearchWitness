# ResearchWitness acceptance ledger

This public ledger contains approved aggregate engineering evidence only. The detailed engineering handoff remains private; its integrity commitment is SHA-256 `df5bde9cd98abe63ec552aa18598807fc957619d37cdd2f62e9b1de6881c3edb`. The commitment does not make that handoff public.

## Candidate and hosted evidence

- Repository: `Smkzz/ResearchWitness`; PR #12 is open, draft, unmerged and unreleased. It remains stacked on PR #11, which provides denominator-provenance contract v1.3.
- Latest completed candidate: `48b61d3f1a53de8c61bfb6788848aaeeef8ab83b`, tree `76c5db1b0a47cd99229729f00206a14ddf41c5ab`, parent `bbc46dc61fe6a7547821aecae437f3390cb84722`.
- CI run [37996043372](https://github.com/Smkzz/ResearchWitness/actions/runs/37996043372): Python 3.11, 3.12 and 3.13, synthetic conformance, historical MVP replay, offline release qualification, reproducible application wheel and synthetic custody-worker package all passed. Both real-browser jobs failed at the replay response assertion: the asynchronous replay endpoint returned HTTP 202 while the test expected 200. Upload, evidence, export, responsive viewport checks and the constant download filename checks ran before that assertion.
- CodeQL run [37996043382](https://github.com/Smkzz/ResearchWitness/actions/runs/37996043382) passed on the latest completed candidate. No Codex Security scan is claimed because a scan-start route is unavailable in the connected tools; a separate manual threat-model review was performed.
- Synthetic desktop and mobile screenshot artifacts from run 37996043372 were retained on GitHub Actions. The predecessor screenshots were inspected on Windows and Ubuntu. Browser viewport assertions passed at 390, 360 and 320 px before the later replay assertion failed.
- The current local follow-up changes the browser expectation to HTTP 202 and adds a Windows-only synthetic custody-worker qualification step. They have not yet been hosted or qualified. The checksum manifest has been regenerated for the current working source and `sha256sum -c CHECKSUMS.sha256` passes.
- Local explicit unittest modules ran 72 tests: 68 passed and four loopback-dependent UI tests were skipped because the sandbox denies local socket binding. Eight direct percentage-qualification functions passed. Python compilation, JavaScript syntax, `git diff --check` and checksum verification passed. Local `pytest` is unavailable and unittest discovery found no tests; hosted CI supplies the full pytest and browser runs.
- The local browser environment cannot launch Chromium. Hosted Windows and Ubuntu browser jobs are the browser evidence source.

## Scientific and custody qualification

- Historical public aggregates reported zero confirmed untouched eligible correction-backed positives and 363 eligible correct relationships across five DOI document IDs. These counts are historical and are not accepted as v1.3-qualified negatives: prior accounting did not require exact eligible operand joins and checked-match outcomes. DOI equality alone does not establish independent works.
- Corrected negative replay accounting requires source-confirmed labels, exact operands and an eligible checked match. Abstentions, mismatches and unmatched joins are reported separately. Synthetic counterexamples pass; no corpus replay was run.
- Frozen minima remain at least one untouched eligible positive and at least 50 eligible correct relationships across 15 independent works. Neither minimum is confirmed. No reserved paper was executed and no Wave 3 run occurred.
- Custodian OS identity, effective-access and descendant checks, Windows v5 private installation and rollback, and independent host egress enforcement remain unqualified. The local UI does not establish a custody security boundary. No paper source was retrieved in this work.

## Ten-category acceptance matrix

| Category | Evidence and status | Remaining gate |
| --- | --- | --- |
| Product usefulness | Hosted synthetic browser flow reaches upload, source evidence and export; retry response assertion currently fails. **BLOCKED** | Pass the complete browser flow on Windows and Ubuntu, including replay, deletion and recovery. |
| Scientific correctness | Narrow source-mapped contracts and synthetic source/denominator regressions exist. Historical negatives fail the exact-join accounting rule. **BLOCKED** | Independently establish frozen eligibility and adjudication minima without running Wave 3 or changing allocation rules. |
| Security | CodeQL passed on `48b61d3`; bounded upload and fail-closed PDF changes are included. Manual threat-model review was performed. **BLOCKED** | Pass CodeQL and browser tests on the final candidate; qualify custodian identity, effective access, egress and Windows worker behavior. |
| Privacy | UI and package checks use synthetic data; no source acquisition occurred. **BLOCKED** | Verify protected custody isolation, deletion and retention behavior, and enforced egress under the authorized custodian identity. |
| UX and accessibility | Responsive browser checks and keyboard smoke checks exist; predecessor screenshots were inspected. No human screen-reader audit is claimed. **BLOCKED** | Pass final responsive browser checks and complete human assistive-technology review. |
| Reliability | Synthetic cancellation, restart, duplicate, retry, deletion and bounded-upload cases exist. Browser replay assertion prevents completion of the full journey. **BLOCKED** | Pass complete browser and recovery workflows on the final source. |
| Performance and cost | No workload-budgeted representative measurements are qualified. No additional spend occurred. **NOT_CLAIMED** | Measure latency, CPU, memory, disk and malformed-input behavior against declared budgets. |
| Installation and portability | Hosted offline release qualification and application-wheel reproducibility passed on `48b61d3`. Windows v5 private installation is unqualified. **BLOCKED** | Pass the final hosted package gate and Windows custody installation, effective-access, egress and rollback checks. |
| Maintainability and reproducibility | Hosted package reproducibility passed on `48b61d3`; checksums verify for the current working source. **BLOCKED** | Regenerate checksums and pass reproducible package qualification on the final hosted source. |
| Documentation and release quality | Supported scope, private-evidence exclusions and draft status are documented. **BLOCKED** | Refresh this ledger and PR body against final hosted checks; keep the candidate unreleased until scientific and custody gates pass. |

PR #12 remains an engineering candidate, not a qualified research-preview release. Do not merge, publish findings, contact researchers or run Wave 3 while scientific and custody gates remain unmet.
