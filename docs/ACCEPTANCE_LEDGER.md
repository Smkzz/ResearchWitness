# ResearchWitness acceptance ledger

This public ledger contains approved aggregate engineering evidence only. It contains no reserve identities, source files, correction labels, or owner-only qualification notes. The private engineering handoff retains its prior SHA-256 commitment `df5bde9cd98abe63ec552aa18598807fc957619d37cdd2f62e9b1de6881c3edb`; the commitment does not make that handoff public.

## Candidate identity and live hosted evidence

- Repository: `Smkzz/ResearchWitness`. PR #12 is open, draft, unmerged, and unreleased. It is stacked on PR #11, which provides denominator-provenance contract v1.3.
- Current PR head: `c6bc61826a128bb9238b8a9814649e0d75614e4b`; tree `d91709edd802f0263695d875f8826d6a9bc6c6b0`; parent `aeb07cc23c6b2b6fc0e3b1f61353c4c21e79ca14`; base `6843593ff443d4a44c48d15a76949b323d0951ca`.
- Hosted CI run [37998298462](https://github.com/Smkzz/ResearchWitness/actions/runs/37998298462) failed in the Windows synthetic custody-worker job: 55 of 56 tests passed, and `test_checked_in_synthetic_bundle_is_source_consistent_end_to_end` reported `SOURCE_HASH_OR_SIZE_MISMATCH`; the Windows zipapp step was skipped. Python 3.11/3.12/3.13, the offline release gate, reproducible application wheel, Windows application wheel, and Ubuntu/Windows browser jobs passed on c6.
- CodeQL run [37998298415](https://github.com/Smkzz/ResearchWitness/actions/runs/37998298415) passed on c6. CodeQL is not a complete security audit. No Codex Security scan-start route is available in this environment.
- On c6, the hosted Chromium journey passed three browser tests on Windows and Ubuntu. It covers the synthetic Markdown upload, source-anchored results, report view, export/replay/history, retry, deletion, cancellation/status races, keyboard smoke checks, and mobile widths. It does not qualify the current uncommitted UI changes or JATS/XML and PDF user flows. No human screen-reader or WCAG audit is claimed. Screenshot artifact hashes and the known iframe capture discrepancy are retained in the hosted run; they are not evidence of candidate UI after the pending changes.

## Current local candidate evidence

- The local integration checkout is based on c6. Intended changes are staged locally but not committed or hosted; therefore the local tree has no new candidate commit identity and none of its results should be attributed to the live PR head.
- Full pytest on this exact staged-source working tree: **744 passed, 8 skipped, 4 subtests passed**. Four skips are local loopback tests denied by this sandbox; three require the hosted Playwright job; one is a native Windows-only PDF fail-closed integration check. The full offline quality gate passed on the same working tree: 500/500 synthetic cases, 3/3 historical MVP cases, frozen-screen review, generated schemas, static trusted-core scan, compilation, source checksums, two reproducible application-wheel builds, and installed CLI smoke checks all passed. The wheel SHA-256 was `dc6f93d1ddd5af4b05708fd8b610edce1967cc2ec4a25edc1a7f1a989ff743a8`.
- `tools/qualify_custody_zipapp.py` passed on the staged source: two clean Linux synthetic builds were byte-identical (SHA-256 `4498bf391e635040d314661bae8732ff2273dd3fb563b7e36938475c0b03ac48`), manifest/member checks passed, and the isolated synthetic CLI refused below-threshold public export. This is not Windows or private-custodian installation qualification.
- The new synthetic header regressions cover mixed named/blank children under a shared denominator, named children with and without subgroup bases, explicit child denominators, same-span headings, and adjacent row groups with distinct bases. Independent synthetic review confirmed the parent/child interval indexing is bounded by the 256-column limit and abstains on unresolved child scope.
- Synthetic JATS parse-plus-arithmetic budget was declared before measurement in [`jats-performance-budget-20261009.json`](qualification/jats-performance-budget-20261009.json), SHA-256 `b02b834b98299f1d37c6fbd9027fe2391e934343e85ddccd5f08274a675f603e`. Five process-isolated trials per case on Linux, Python 3.12.14 produced [`jats-performance-results-20261010.json`](qualification/jats-performance-results-20261010.json), SHA-256 `3c7ab58a77b1929e7c87e8bafb35040128e1e80dfac8f69d542ccb42afcfb1f2`; benchmark source SHA-256 `3d2a2eaedeff6f9de641ea03208e8a9ae60f30d4f22cf9b5acaa93c5d6c42909`.

| Synthetic case | Input / rows | Median wall / CPU | Max observed wall / CPU | Max observed RSS | Budget |
| --- | ---: | ---: | ---: | ---: | --- |
| Small valid | 20 KiB / 200 | 0.060 s / 0.060 s | 0.066 s / 0.066 s | 18 MiB | 0.5 s / 64 MiB |
| Medium valid | 1 MiB / 5,000 | 1.687 s / 1.687 s | 1.821 s / 1.820 s | 86 MiB | 2 s / 128 MiB |
| Large valid | 8 MiB / 10,000 | 3.723 s / 3.723 s | 3.968 s / 3.967 s | 178 MiB | 5 s / 256 MiB |
| Malformed excessive depth | 1 KiB | 0.00049 s / 0.00048 s | 0.00053 s / 0.00052 s | 15 MiB | 0.25 s / 64 MiB |

These are single-process synthetic parser-plus-arithmetic diagnostics only. They do not measure Windows, disk/export use, startup/shutdown, concurrency, cancellation, retries, or real-paper workloads and do not establish production performance.

## Scientific and custody gates

- Historical public aggregates reported zero confirmed untouched eligible correction-backed positives and 363 eligible relationships across five DOI document IDs. Those historical counts do not establish 15 independent works or the current v1.3 exact-source-join, exact-operand, checked-match criteria. DOI aliases, versions, corrections, and paper families require deduplication.
- The inherited minima remain unconfirmed: at least one untouched eligible positive and at least 50 eligible correct negative relationships across at least 15 independent works. No qualifying replay or fresh scientific-source acquisition occurred here. No reserved paper was executed and no Wave 3 run occurred.
- The managed development runtime has an enforced network allowlist broader than the approved source-host list, no configured outbound identity, and no custodian executor. It is not the required protected custodian boundary. Private Windows v5 installation/rollback, effective access under all relevant identities, and independent host egress denial remain unqualified.
- No additional spending occurred. No merge, release, publication of findings, researcher contact, or Wave 3 execution occurred.

## Ten-category acceptance matrix

| Category | Evidence and status | Remaining gate |
| --- | --- | --- |
| Product usefulness | c6 hosted browser journey passed; current staged product changes have not run in hosted browser CI. **BLOCKED** | Run the current exact candidate through the full hosted journey and verify a clean-install launch. |
| Scientific correctness | Synthetic source-mapping and v1.3 regressions pass locally; inherited aggregates do not satisfy the positive or independent-work minima. **BLOCKED** | Complete source-only eligibility and independent adjudication under the frozen allocation contract; do not execute Wave 3 before readiness. |
| Security | CodeQL passed on c6; targeted synthetic review covered the changed denominator scope logic. No full security scan ran, and no Codex Security start route is available. **BLOCKED** | Run hosted CodeQL on the exact candidate and finish declared threat-model checks; qualify custodian identity and enforced egress. |
| Privacy | No research source or reserve data was acquired in this development environment. The environment does not qualify as custodian-isolated. **BLOCKED** | Verify protected storage access boundaries, retention/deletion, and independent egress denial under the authorized custodian identity. |
| UX and accessibility | c6 real-browser keyboard and responsive checks passed. Current candidate is pending browser CI; no human assistive-technology audit exists. **BLOCKED** | Re-run on the exact candidate and complete human keyboard and screen-reader review. |
| Reliability | Exact working tree pytest passed 744 tests; eight environment/platform-dependent tests were skipped. The Linux synthetic v5 worker package qualifies locally; the c6 Windows custody-worker job failed as recorded above. **BLOCKED** | Pass exact-candidate browser/Windows worker jobs and complete private recovery checks. |
| Performance and cost | Declared synthetic budgets passed for four parser cases. Workload scope is limited as stated above; no spending occurred. **BLOCKED** | Measure Windows, disk/export, concurrency and recovery workloads before making broader performance claims. |
| Installation and portability | Exact staged source passed offline release qualification and Linux synthetic v5 packaging; c6 Windows application-wheel job passed. Windows worker qualification and private installation remain pending. **BLOCKED** | Pass Windows worker qualification on the exact candidate; perform private v5 installation and rollback rehearsal. |
| Maintainability and reproducibility | Exact staged source passed source checksums, quality gate, clean offline install, and two byte-identical application-wheel builds. Hosted checks on this candidate have not run. **BLOCKED** | Commit and run CI/CodeQL on the exact candidate; verify hosted artifact identity. |
| Documentation and release quality | This ledger separates live c6 evidence from exact-working-tree results. PR #12 remains draft and unreleased. **BLOCKED** | Refresh this ledger and the PR body against final hosted evidence; keep the preview unreleased until all required gates pass. |

PR #12 remains an engineering candidate, not a qualified research-preview release. Keep it draft and unmerged. Do not publish findings, contact researchers, retrieve reserve evidence in the development environment, or run Wave 3 while scientific and custody gates remain unmet.
