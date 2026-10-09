# ResearchWitness acceptance ledger

This public ledger contains approved aggregate engineering evidence only. The detailed engineering handoff remains private; its integrity commitment is SHA-256 `df5bde9cd98abe63ec552aa18598807fc957619d37cdd2f62e9b1de6881c3edb`. The commitment does not make that handoff public.

## Candidate and hosted evidence

- Repository: `Smkzz/ResearchWitness`; PR #12 is open, draft, unmerged and unreleased. It remains stacked on PR #11, which provides denominator-provenance contract v1.3.
- Latest completed candidate: `aeb07cc23c6b2b6fc0e3b1f61353c4c21e79ca14`, tree `26f8bcad44382f45c78170b6397b3cbe733ef9b8`, parent `ffa4444ebce253274dc5d4f8b922e6945b820548`.
- CI run [37997632313](https://github.com/Smkzz/ResearchWitness/actions/runs/37997632313): Python 3.11, 3.12 and 3.13, synthetic conformance, historical MVP replay, offline qualification, reproducible application wheel, both real-browser jobs and Windows application-wheel qualification passed. The Windows synthetic custody-worker test and zipapp smoke check failed because Windows text-mode fixture writes changed the exact synthetic marker LF to CRLF; the strict marker check rejected it. The Linux synthetic custody-worker package passed.
- CodeQL run [37997632335](https://github.com/Smkzz/ResearchWitness/actions/runs/37997632335) passed on `aeb07cc`.
- Browser artifacts from run 37997632313 were retained and inspected. Both desktop screenshots show the report. The full-page 390 px captures still show a blank iframe even though the browser test now waits for the iframe's report heading and both browser jobs pass that visible-heading assertion. The current follow-up captures the iframe element separately to establish whether this is a full-page screenshot limitation or a visual rendering problem.
- The current local follow-up writes synthetic marker files as exact bytes in the Windows unittest fixtures and zipapp smoke setup, and adds a dedicated mobile iframe screenshot. These changes have not yet been hosted. Local custody-worker tests now pass after the byte-write correction.
- Local explicit UI and custody-worker modules ran 72 tests: 68 passed and four loopback-dependent UI tests were skipped because the sandbox denies local socket binding. The custody-worker's 56 tests and zipapp qualification passed after the marker correction. Eight direct percentage-qualification functions passed. Python compilation, JavaScript syntax, diff checks and checksum verification passed. Local `pytest` is unavailable and unittest discovery found no tests; hosted CI supplies the full test-suite run.
- The local browser environment cannot bind loopback or launch Chromium. Hosted Windows and Ubuntu jobs provide the real-browser evidence.

## Scientific and custody qualification

- Historical public aggregates reported zero confirmed untouched eligible correction-backed positives and 363 eligible correct relationships across five DOI document IDs. These counts are historical and are not accepted as v1.3-qualified negatives: prior accounting did not require exact eligible operand joins and checked-match outcomes. DOI equality alone does not establish independent works.
- Corrected negative replay accounting requires source-confirmed labels, exact operands and an eligible checked match. Abstentions, mismatches and unmatched joins are reported separately. Synthetic counterexamples pass; no corpus replay was run.
- Frozen minima remain at least one untouched eligible positive and at least 50 eligible correct relationships across 15 independent works. Neither minimum is confirmed. No reserved paper was executed and no Wave 3 run occurred.
- Custodian OS identity, effective-access and descendant checks, Windows v5 private installation and rollback, and independent host egress enforcement remain unqualified. The local UI does not establish a custody security boundary. No paper source was retrieved in this work.

## Ten-category acceptance matrix

| Category | Evidence and status | Remaining gate |
| --- | --- | --- |
| Product usefulness | Hosted synthetic browser flow including replay, failed-run retry, deletion and recovery passed on Windows and Ubuntu. **BLOCKED** | Resolve whether the blank full-page mobile iframe capture reflects a visible product issue; inspect the separate iframe screenshot. |
| Scientific correctness | Narrow source-mapped contracts and synthetic source/denominator regressions exist. Historical negatives fail the exact-join accounting rule. **BLOCKED** | Independently establish frozen eligibility and adjudication minima without running Wave 3 or changing allocation rules. |
| Security | CodeQL passed on `aeb07cc`; bounded upload and fail-closed PDF changes are included. Manual threat-model review was performed. **BLOCKED** | Pass CodeQL on the final candidate; qualify custodian identity, effective access, egress and Windows worker behavior. |
| Privacy | UI and package checks use synthetic data; no source acquisition occurred. **BLOCKED** | Verify protected custody isolation, deletion and retention behavior, and enforced egress under the authorized custodian identity. |
| UX and accessibility | Responsive checks, keyboard smoke tests and report-heading visibility passed in real browsers; mobile iframe screenshot is ambiguous. No human screen-reader audit is claimed. **BLOCKED** | Inspect the dedicated mobile iframe screenshot, then complete human assistive-technology review. |
| Reliability | Synthetic cancellation, restart, duplicate, retry, deletion and bounded-upload cases exist. The complete browser flow passed on both platforms. **BLOCKED** | Pass Windows synthetic custody qualification and complete remaining custody recovery checks. |
| Performance and cost | No workload-budgeted representative measurements are qualified. No additional spend occurred. **NOT_CLAIMED** | Measure latency, CPU, memory, disk and malformed-input behavior against declared budgets. |
| Installation and portability | Hosted offline qualification, application-wheel reproducibility and Linux synthetic custody package passed on `aeb07cc`; Windows application wheel passed. The Windows synthetic worker check exposed a CRLF-sensitive fixture and is fixed locally. **BLOCKED** | Pass the Windows synthetic worker test, plus private custody installation, effective-access, egress and rollback checks. |
| Maintainability and reproducibility | Hosted package reproducibility passed on `aeb07cc`; checksum verification passes locally. **BLOCKED** | Pass reproducible package qualification on the final hosted source. |
| Documentation and release quality | Supported scope, private-evidence exclusions and draft status are documented. **BLOCKED** | Refresh this ledger and the PR body against final hosted checks; keep the candidate unreleased until scientific and custody gates pass. |

PR #12 remains an engineering candidate, not a qualified research-preview release. Do not merge, publish findings, contact researchers or run Wave 3 while scientific and custody gates remain unmet.
