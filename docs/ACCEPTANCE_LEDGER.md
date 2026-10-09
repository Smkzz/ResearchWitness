# ResearchWitness acceptance ledger

This public ledger records approved aggregate engineering status. The detailed engineering handoff remains private; its integrity commitment is SHA-256 `df5bde9cd98abe63ec552aa18598807fc957619d37cdd2f62e9b1de6881c3edb`. The commitment does not make that handoff public.

## Candidate and hosted evidence

- Repository: `Smkzz/ResearchWitness`; PR #12 is open, draft, unmerged and unreleased. It remains stacked on PR #11, which provides denominator provenance contract v1.3.
- Latest independently queried head: `47578bbf9238df4a10f04a3f2797ceb05138c45e`; tree `b5a384a19983b7699ac296ea2251fad8c98e0a83`; base `codex/paper-audit-denominator-provenance` at `6843593ff443d4a44c48d15a76949b323d0951ca`.
- CI run [37991542864](https://github.com/Smkzz/ResearchWitness/actions/runs/37991542864) completed with **failure**. Python 3.11, 3.12 and 3.13, historical MVP replay, synthetic conformance and the release gate passed. The Windows and Ubuntu browser jobs failed the 390 px page-width assertion: `scrollWidth` was 393 px on Windows and 449 px on Ubuntu. The run stopped before later export/replay browser steps and Windows clean-wheel qualification.
- CodeQL run [37991542856](https://github.com/Smkzz/ResearchWitness/actions/runs/37991542856) completed successfully on that head. CodeQL is not the complete threat-model review.
- The responsive CSS fix at this head wraps long list values and the source-hash row assertion passes, but page-wide overflow remains. A follow-up change adds overflow-element diagnostics and captures the mobile screenshot before that assertion.
- Prior local package builds came from `2e3e0c145ff599501ddb5d63b554f3bafce86eb8` (tree `fc587e2424b64aa469679673195514a4627940a7`). That source predates the responsive CSS/test update; its package hashes do not identify the current PR head. Those earlier builds were byte-identical and their offline install smoke test passed, but they are historical engineering evidence only.
- Local UI tests on `2e3e0c1` ran 13 tests: 11 passed and 2 skipped because that sandbox denied loopback binding. The browser module also skipped there. In this execution environment, Playwright/Chromium launch and loopback binding are denied, so hosted browser results remain the applicable evidence.

## Scientific and security qualification

- The inherited public aggregate records zero confirmed untouched eligible correction-backed positives and 363 eligible correct negative relationships across five DOI document IDs. These are not independently re-established here. A code review found that the v1.3 replay summary currently equates raw source-locator count with eligible correct relationships without requiring an exact eligible operand join; therefore the inherited negative count is **not accepted as a qualified v1.3 negative count** until the replay accounting is corrected and tested with synthetic counterexamples.
- The frozen minimums remain at least one untouched eligible positive and at least 50 eligible negatives over 15 independent works. Neither minimum is confirmed. DOI count alone does not prove independent-work count; no Wave 3 run has occurred.
- Read-only threat-model review found unresolved local upload-concurrency resource bounds and no Windows PDF-worker memory cap. Windows custodian access controls, descendant/effective-access checks and independent host egress enforcement also remain unqualified. The local screening UI explicitly is not a custodian security boundary.
- No paper source was retrieved, and no reserved evaluation paper was processed in this work.

## Ten-category acceptance matrix

| Category | Evidence and status | Remaining gate |
| --- | --- | --- |
| Product usefulness | Hosted synthetic browser flow reached source evidence; mobile overflow stopped the run before export/replay. **BLOCKED** | Fix responsive layout and pass the complete browser journey. |
| Scientific correctness | Narrow count/percentage contract v1.3 and synthetic source-mapping tests exist. Replay accounting can overstate eligible negatives; frozen positive and 15-work minimums are unconfirmed. **BLOCKED** | Correct replay metric joins; retain abstentions separately; establish source eligibility and independent adjudication without changing frozen rules. |
| Security | CodeQL passed on head `47578bb`; manual review identified local upload resource-exhaustion and Windows PDF memory-limit gaps. **BLOCKED** | Add exploit-focused bounds/regressions and complete custodian identity, effective-access and egress qualification. |
| Privacy | Local exports and package-selection checks use synthetic data; no public source retrieval occurred here. **BLOCKED** | Verify OS custody isolation, retention/deletion, private-store access and independently enforced egress. |
| UX and accessibility | Keyboard/upload/evidence smoke checks exist; browser page-width test failed on Windows and Ubuntu. No screen-reader assessment is claimed. **BLOCKED** | Pass desktop/mobile browser tests and complete human assistive-technology review. |
| Reliability | Synthetic cancellation, restart, duplicate, retry and history-size regressions exist. Browser failure prevented later export/replay checks in the current run. **BLOCKED** | Pass complete browser suite, including restart, export, replay, deletion and failure recovery. |
| Performance and cost | No workload budgeted representative end-to-end measurement is qualified. No additional spend is authorized. **NOT_CLAIMED** | Set budgets and record latency, CPU, memory, disk and malformed-input measurements at the exact source identity. |
| Installation and portability | Earlier Linux source/wheel builds and offline install smoke tests were reproducible on `2e3e0c1`; current hosted release gate passed on `47578bb`. Windows app-wheel job was skipped after browser failure; custody worker is not Windows-qualified. **BLOCKED** | Rebuild/rebind artifacts after final code changes and pass Windows application and owner-side custody install/rollback checks. |
| Maintainability and reproducibility | Allowlisted package selection, generated checksums and earlier byte-identical builds are recorded. Current candidate needs new package identities. **BLOCKED** | Regenerate checksums through the documented release generator; build twice from clean current sources and compare complete bytes/hashes. |
| Documentation and release quality | Public scope limits, private-evidence exclusions and unmerged draft status are stated. **BLOCKED** | Refresh this ledger and PR body against final engineering evidence; keep unreleased until the scientific and custody gates pass. |

The candidate is an engineering preview, not a qualified research-preview release. Do not merge, release, publish research findings or run Wave 3 while scientific, security, product and custody gates remain unmet.
