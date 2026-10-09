# ResearchWitness acceptance ledger

This public ledger contains approved aggregate engineering evidence only. The detailed engineering handoff remains private; its integrity commitment is SHA-256 `df5bde9cd98abe63ec552aa18598807fc957619d37cdd2f62e9b1de6881c3edb`. The commitment does not make that handoff public.

## Candidate and hosted evidence

- Repository: `Smkzz/ResearchWitness`; PR #12 is open, draft, unmerged and unreleased. It remains stacked on PR #11, which provides denominator-provenance contract v1.3.
- Fresh remote query: pre-patch PR head `a9711cb0e7dcf205add81a1094e1f0ba28b97170`, tree `72a08ea519d8e078bb8c00ecab0ed004bb1ae2e0`; base `codex/paper-audit-denominator-provenance` at `6843593ff443d4a44c48d15a76949b323d0951ca`. The mandate's recorded head `92891ce0…` is an ancestor of this head; the remote is seven commits ahead.
- CI run [37993142798](https://github.com/Smkzz/ResearchWitness/actions/runs/37993142798) completed with **failure** on the pre-patch head. Python 3.11–3.13 and the release gate passed. Both browser jobs failed the 390 px page-width assertion (`scrollWidth` 393 px on Windows and 449 px on Ubuntu); the run stopped before later export/replay steps and Windows clean-wheel qualification.
- CodeQL run [37993142792](https://github.com/Smkzz/ResearchWitness/actions/runs/37993142792) passed on that pre-patch head. No Codex Security scan is claimed: a scan-start route was not available in the connected tools. CodeQL does not replace manual threat-model review.
- The synthetic desktop and mobile screenshots were downloaded and inspected. The earlier test's element-rectangle diagnostic returned no offender; a pending test change now records internal scroll widths, pseudo-elements and root/body metrics. The local environment denies loopback binding and Chromium launch, so local browser skips are not browser qualification.
- The current unpushed patch adds bounded HTTP/upload concurrency, fail-closed PDF extraction when both OS limits are unavailable, PDF cache-policy versioning, stricter source-relationship accounting and locator identity, cross-version source-row lineage checks, and expanded mobile diagnostics. Static compilation, JavaScript syntax, and diff checks pass on the working copy. The focused local UI suite ran 16 tests (12 passed, 4 skipped because loopback binding is denied); two custody-lineage tests passed; isolated synthetic accounting and locator assertions passed. Full pytest, hosted checks for this patch, and the updated package checksums are pending.

## Scientific and custody qualification

- Historical public aggregates reported zero confirmed untouched eligible correction-backed positives and 363 eligible correct relationships across five DOI document IDs. Those records are not freshly verified here and are not accepted as qualifying v1.3 negatives: source-locator counts were not required to have exact operand joins and eligible checked-match outcomes.
- The local v1.3 replay patch now counts only source-confirmed labels with exact operands and `ELIGIBLE_CHECKED_MATCH`, classifies abstentions/mismatches/unmatched joins separately, and reports source-record and distinct normalized DOI counts separately. This has synthetic counterexample coverage but the corpus replay has not been run. DOI values alone do not prove independent works.
- Frozen minima remain at least one untouched eligible positive and at least 50 eligible correct relationships across 15 independent works. Neither is confirmed. No reserved paper was executed and no Wave 3 run occurred.
- Custodian OS identity, effective-access/descendant checks, Windows v5 installation/rollback and independent host egress enforcement remain unqualified. The local UI is not a custody security boundary. No paper source was retrieved in this work.

## Ten-category acceptance matrix

| Category | Evidence and status | Remaining gate |
| --- | --- | --- |
| Product usefulness | Hosted synthetic browser flow reached source evidence; page-width failure prevented the remaining export/replay journey. **BLOCKED** | Fix responsive overflow, then pass the full browser journey on Windows and Ubuntu. |
| Scientific correctness | Narrow source-mapped contracts and new synthetic source/denominator regressions exist. Historical negative aggregate is not accepted after the exact-join accounting defect. **BLOCKED** | Independently establish frozen eligibility and adjudication minima without running Wave 3 or changing allocation rules. |
| Security | CodeQL passed on the pre-patch head. Thread/upload bounds and PDF fail-closed changes are implemented locally; their hosted checks are pending. **BLOCKED** | Pass CodeQL on the final candidate and complete OS custody, effective-access, egress and Windows worker qualification. |
| Privacy | UI and package checks use synthetic data; no source acquisition occurred. **BLOCKED** | Verify protected custody isolation, deletion/retention behavior and enforced egress through the authorized custodian identity. |
| UX and accessibility | Keyboard, labels, focus, live-status and responsive smoke tests exist; mobile layout still fails. No human screen-reader audit is claimed. **BLOCKED** | Pass browser tests and complete human assistive-technology review. |
| Reliability | Synthetic cancellation, restart, duplicate, retry, deletion and bounded-upload cases exist. The failing browser run did not reach later journey steps. **BLOCKED** | Pass the complete browser workflow and restart/replay recovery on the final source. |
| Performance and cost | No workload-budgeted representative measurements are qualified. No additional spend occurred. **NOT_CLAIMED** | Measure latency, CPU, memory, disk and malformed-input behavior against declared budgets. |
| Installation and portability | Release gate passed on the pre-patch head; Windows wheel qualification was skipped after the browser failure. Custody v5 Windows installation remains unqualified. **BLOCKED** | Rebuild and inspect final artifacts; complete Windows application and owner-side custody install/rollback checks. |
| Maintainability and reproducibility | Allowlisted package selection and deterministic-build checks exist. Current code changes need generated checksums and fresh clean builds. **BLOCKED** | Run the documented checksum generator and final exact-source reproducibility gate. |
| Documentation and release quality | Supported scope, private-evidence exclusions, and draft status are documented. **BLOCKED** | Refresh this ledger and the PR body with final source/run identities; keep unreleased until scientific and custody gates pass. |

PR #12 remains an engineering candidate, not a qualified research-preview release. Do not merge, publish findings, or run Wave 3 while the scientific and custody gates remain unmet.
