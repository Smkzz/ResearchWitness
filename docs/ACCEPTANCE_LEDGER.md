# ResearchWitness acceptance ledger

This public ledger contains approved aggregate engineering evidence only. The detailed engineering handoff remains private; its integrity commitment is SHA-256 `df5bde9cd98abe63ec552aa18598807fc957619d37cdd2f62e9b1de6881c3edb`. The commitment does not make that handoff public.

## Candidate and hosted evidence

- Repository: `Smkzz/ResearchWitness`; PR #12 is open, draft, unmerged and unreleased. It remains stacked on PR #11, which provides denominator-provenance contract v1.3.
- Current remotely tested head: `fae5e69c81ace2cd4fa696ca7b2ad012f3d80c39`, tree `63f3267128d0c8bf96c5c1a93552ed0916db13ea`; base `codex/paper-audit-denominator-provenance` at `6843593ff443d4a44c48d15a76949b323d0951ca`.
- CI run [37994973698](https://github.com/Smkzz/ResearchWitness/actions/runs/37994973698) **failed**. The Python matrix reported 687 passed, 1 failed, 4 skipped; the new table-identity test referenced an out-of-scope local. The release gate stopped at that same test failure.
- Both browser jobs in that CI run **failed** the 390 px page-width assertion: 393 px on Windows and 449 px on Ubuntu. The hosted diagnostics identified long generated finding titles and coverage-reason strings that overflowed their boxes. A local patch adds wrapping and 320/360 px checks; its hosted result is pending.
- CodeQL run [37994973709](https://github.com/Smkzz/ResearchWitness/actions/runs/37994973709) passed on `fae5e69`. No Codex Security scan is claimed because a scan-start route was unavailable in the connected tools.
- Synthetic desktop and mobile screenshots from this run were inspected. The current local environment denies loopback binding and Chromium launch, so local browser skips are not qualification evidence.
- On the unpushed working copy, Python compilation, JavaScript syntax, and diff checks pass; the focused UI suite ran 16 tests (12 passed, 4 loopback-dependent tests skipped), two custody-lineage tests passed, and isolated source-accounting assertions passed. Local pytest is unavailable. A temporary clean verification worktree regenerated and verified `CHECKSUMS.sha256`; two source-archive builds, two app-wheel builds, and two custody-zipapp builds were byte-identical. Hosted package qualification of the next candidate is pending.

## Scientific and custody qualification

- Historical public aggregates reported zero confirmed untouched eligible correction-backed positives and 363 eligible correct relationships across five DOI document IDs. They are not freshly verified here and are not accepted as qualifying v1.3 negatives: the prior helper did not require exact operand joins and eligible checked-match outcomes.
- The candidate fixes replay accounting to require source-confirmed labels, exact operands, and `ELIGIBLE_CHECKED_MATCH`; abstentions, mismatches, and unmatched joins are separate. It reports source records and distinct normalized DOI values separately. Synthetic counterexamples pass; no corpus replay was run. DOI values alone do not prove independent works.
- Frozen minima remain at least one untouched eligible positive and at least 50 eligible correct relationships across 15 independent works. Neither is confirmed. No reserved paper was executed and no Wave 3 run occurred.
- Custodian OS identity, effective-access/descendant checks, Windows v5 installation/rollback, and independent host egress enforcement remain unqualified. The local UI is not a custody security boundary. No paper source was retrieved in this work.

## Ten-category acceptance matrix

| Category | Evidence and status | Remaining gate |
| --- | --- | --- |
| Product usefulness | Hosted synthetic browser flow reaches source evidence, but mobile overflow prevents the complete journey. **BLOCKED** | Pass the complete browser flow on Windows and Ubuntu, including export, replay, deletion and recovery. |
| Scientific correctness | Narrow source-mapped contracts and synthetic source/denominator regressions exist. The inherited negative aggregate is not accepted after the exact-join accounting defect. **BLOCKED** | Independently establish frozen eligibility and adjudication minima without running Wave 3 or changing allocation rules. |
| Security | CodeQL passed on `fae5e69`; bounded upload and fail-closed PDF changes are in the candidate. **BLOCKED** | Pass CodeQL and browser tests on the final candidate; qualify custodian identity, effective access, egress and Windows worker behavior. |
| Privacy | UI and package checks use synthetic data; no source acquisition occurred. **BLOCKED** | Verify protected custody isolation, deletion/retention behavior and enforced egress through the authorized custodian identity. |
| UX and accessibility | Keyboard, labels, focus and live-status smoke checks exist; mobile layout fails. No human screen-reader audit is claimed. **BLOCKED** | Pass responsive browser checks and complete human assistive-technology review. |
| Reliability | Synthetic cancellation, restart, duplicate, retry, deletion and bounded-upload cases exist. Browser failure prevented later journey steps. **BLOCKED** | Pass complete browser and recovery workflows on the final source. |
| Performance and cost | No workload-budgeted representative measurements are qualified. No additional spend occurred. **NOT_CLAIMED** | Measure latency, CPU, memory, disk and malformed-input behavior against declared budgets. |
| Installation and portability | Local clean package checks passed on a verification snapshot; hosted release gate stopped at pytest. Windows wheel qualification and custody v5 installation are unqualified. **BLOCKED** | Pass the hosted exact-source package gate and Windows application/custody install and rollback checks. |
| Maintainability and reproducibility | Generated checksums and repeated clean local builds passed on the verification snapshot. **BLOCKED** | Regenerate checksums and pass reproducible package qualification on the final hosted source. |
| Documentation and release quality | Supported scope, private-evidence exclusions and draft status are documented. **BLOCKED** | Refresh this ledger and the PR body against the completed hosted checks; keep unreleased until scientific and custody gates pass. |

PR #12 remains an engineering candidate, not a qualified research-preview release. Do not merge, publish findings, or run Wave 3 while the scientific and custody gates remain unmet.
