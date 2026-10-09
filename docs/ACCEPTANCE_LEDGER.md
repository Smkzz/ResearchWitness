# ResearchWitness acceptance ledger

This public ledger contains approved aggregate engineering evidence only. The detailed engineering handoff remains private; its integrity commitment is SHA-256 `df5bde9cd98abe63ec552aa18598807fc957619d37cdd2f62e9b1de6881c3edb`. The commitment does not make that handoff public.

## Candidate and hosted evidence

- Repository: `Smkzz/ResearchWitness`; PR #12 is open, draft, unmerged and unreleased. It remains stacked on PR #11, which provides denominator-provenance contract v1.3.
- Latest completed candidate: `ffa4444ebce253274dc5d4f8b922e6945b820548`, tree `b798d00a0aeacf018c6ee3c2d7c9243359fb0032`, parent `48b61d3f1a53de8c61bfb6788848aaeeef8ab83b`.
- CI run [37997002016](https://github.com/Smkzz/ResearchWitness/actions/runs/37997002016): Python 3.11, 3.12 and 3.13, synthetic conformance, historical MVP replay, offline qualification, reproducible application wheel and Linux synthetic custody-worker package passed. Both real-browser jobs failed on the failed-run retry assertion: the retry endpoint correctly returned HTTP 202 while the test expected 200. The preceding asynchronous replay assertion expected 202 and passed. Browser checks reached upload, source evidence, export, replay and the error/retry flow. The Windows synthetic custody-worker step did not run because the browser test step failed first.
- CodeQL run [37997002035](https://github.com/Smkzz/ResearchWitness/actions/runs/37997002035) passed on `ffa4444`.
- Synthetic browser screenshots from run 37997002016 were retained and inspected. Desktop screenshots show the complete report. In both 390 px mobile captures the embedded full-report iframe appears blank; the next browser run adds an assertion that its report heading is visible after the viewport change to distinguish a rendering defect from capture timing.
- The current local follow-up updates the retry expectation to HTTP 202, confirms the response identifies a new retry job, and checks the embedded report heading at mobile width. This follow-up has not yet been hosted. The Windows synthetic custody-worker check remains pending.
- Local explicit UI and custody-worker modules ran 72 tests: 68 passed and four loopback-dependent UI tests were skipped because the sandbox denies local socket binding. Eight direct percentage-qualification functions passed. Python compilation, JavaScript syntax, diff checks and regenerated checksum verification passed. Local `pytest` is unavailable and unittest discovery found no tests; hosted CI supplies the full test-suite run.
- The local browser environment cannot bind loopback or launch Chromium. Hosted Windows and Ubuntu jobs provide the real-browser evidence.

## Scientific and custody qualification

- Historical public aggregates reported zero confirmed untouched eligible correction-backed positives and 363 eligible correct relationships across five DOI document IDs. These counts are historical and are not accepted as v1.3-qualified negatives: prior accounting did not require exact eligible operand joins and checked-match outcomes. DOI equality alone does not establish independent works.
- Corrected negative replay accounting requires source-confirmed labels, exact operands and an eligible checked match. Abstentions, mismatches and unmatched joins are reported separately. Synthetic counterexamples pass; no corpus replay was run.
- Frozen minima remain at least one untouched eligible positive and at least 50 eligible correct relationships across 15 independent works. Neither minimum is confirmed. No reserved paper was executed and no Wave 3 run occurred.
- Custodian OS identity, effective-access and descendant checks, Windows v5 private installation and rollback, and independent host egress enforcement remain unqualified. The local UI does not establish a custody security boundary. No paper source was retrieved in this work.

## Ten-category acceptance matrix

| Category | Evidence and status | Remaining gate |
| --- | --- | --- |
| Product usefulness | Hosted synthetic browser flow reaches source evidence, export and replay; retry qualification currently fails. **BLOCKED** | Pass the complete browser flow on Windows and Ubuntu, including retry completion, deletion and recovery. |
| Scientific correctness | Narrow source-mapped contracts and synthetic source/denominator regressions exist. Historical negatives fail the exact-join accounting rule. **BLOCKED** | Independently establish frozen eligibility and adjudication minima without running Wave 3 or changing allocation rules. |
| Security | CodeQL passed on `ffa4444`; bounded upload and fail-closed PDF changes are included. Manual threat-model review was performed. **BLOCKED** | Pass CodeQL and browser tests on the final candidate; qualify custodian identity, effective access, egress and Windows worker behavior. |
| Privacy | UI and package checks use synthetic data; no source acquisition occurred. **BLOCKED** | Verify protected custody isolation, deletion and retention behavior, and enforced egress under the authorized custodian identity. |
| UX and accessibility | Responsive checks and keyboard smoke tests exist; desktop screenshots were inspected. Mobile full-report rendering needs confirmation. No human screen-reader audit is claimed. **BLOCKED** | Pass final responsive browser checks, verify full-report readability at mobile widths, and complete human assistive-technology review. |
| Reliability | Synthetic cancellation, restart, duplicate, retry, deletion and bounded-upload cases exist. The browser retry flow is still under qualification. **BLOCKED** | Pass complete browser and recovery workflows on the final source. |
| Performance and cost | No workload-budgeted representative measurements are qualified. No additional spend occurred. **NOT_CLAIMED** | Measure latency, CPU, memory, disk and malformed-input behavior against declared budgets. |
| Installation and portability | Hosted offline qualification, application-wheel reproducibility and Linux synthetic custody package passed on `ffa4444`. Windows v5 private installation is unqualified; its new synthetic hosted step was skipped after the browser failure. **BLOCKED** | Pass the final hosted package gate and Windows synthetic worker test, plus custody installation, effective-access, egress and rollback checks. |
| Maintainability and reproducibility | Hosted package reproducibility passed on `ffa4444`; checksums verify for the current working source. **BLOCKED** | Regenerate checksums and pass reproducible package qualification on the final hosted source. |
| Documentation and release quality | Supported scope, private-evidence exclusions and draft status are documented. **BLOCKED** | Refresh this ledger and the PR body against final hosted checks; keep the candidate unreleased until scientific and custody gates pass. |

PR #12 remains an engineering candidate, not a qualified research-preview release. Do not merge, publish findings, contact researchers or run Wave 3 while scientific and custody gates remain unmet.
