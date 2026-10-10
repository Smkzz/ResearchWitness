# ResearchWitness engineering qualification — 2026-10-10

**Status: development candidate only. Not a research-preview release, not production-custody qualified, not eligible for reserved evidence or Wave 3.** This completion candidate is PR #12 stacked on denominator-provenance PR #11. The locally qualified sanitized source snapshot is commit `379602e72cc05ad79ba2959a832baf5abbcf27c2`, tree `a1ab414baa959214c02f23a066966a14c809447e`; hosted checks on the forward update remain required.

## Local checks

- `tools/quality_gate.py` on the sanitized snapshot: **833 passed, 11 skipped, 4 subtests passed**; 500/500 synthetic cases and 3/3 historical MVP cases matched. Static scan, schemas, checksums, compilation, and CLI smoke checks passed. Four loopback tests were skipped because the managed sandbox denied socket binding; six Playwright tests await hosted browser CI; one native-Windows PDF resource-limit test was skipped locally.
- Python compilation, JavaScript syntax validation, and whitespace/diff checks passed.
- Focused scientific regressions cover Unicode-spaced count ranges/fractions, weighted or adjusted scope, US/UK standardization forms, JATS ratio lookalikes, source-mapped offsets, and detector abstention.
- `tools/qualify_app_wheel.py` produced two byte-identical builds and passed clean-target installation plus CLI/resource smoke checks. Qualified wheel SHA-256: `551df5e32c54c0ebbb0e2b9d7d65abc5b19d551cd337aefec7cbe35c1285ac56`.
- The offline custody zipapp was rebuilt twice from clean synthetic sources. Archive bytes/member hashes matched; the synthetic CLI workflow passed and below-threshold export was refused. SHA-256: `25b4802c1636fdbe2bd2185eeb2179a38d7fc80b2c4cc56e82d3ca91d913c9d2`. It has not been installed in a protected environment.
- `tools/make_release.py` produced byte-identical release outputs twice. Source archive SHA-256: `bb298797fd7c12b60ab75bbe1d5e5d7096fc7da7cb86a7823eb0733ebf968921` (4,946,838 bytes); release wheel SHA-256: `436d7656b3883ed88bacaeea05c58a89bed57a72bc3753f63e8003af4c9e2d32` (279,462 bytes). The qualified application wheel and release wheel use different declared build epochs.

## Browser and hosted evidence

- The latest baseline CI [run 38008005323](https://github.com/Smkzz/ResearchWitness/actions/runs/38008005323) and CodeQL [run 38008005400](https://github.com/Smkzz/ResearchWitness/actions/runs/38008005400) passed before the current forward changes. Fresh checks on the public forward commit are required.
- Baseline hosted Chromium jobs cover the synthetic Markdown workflow, source-linked findings, export/replay/history, retry, deletion, cancellation, keyboard smoke checks, and responsive widths. The current browser regressions additionally check stale duplicate status and displayed/exported byte-range parity for synthetic JATS.
- The previous Windows and Ubuntu screenshot ZIP digests are retained in the acceptance ledger. They were not visually previewed here. Automated browser/DOM checks do not qualify human screen-reader use or full accessibility conformance.

## Synthetic JATS performance

Predeclared limits and five process-isolated Linux/Python 3.12.14 trials are captured in `docs/qualification/jats-performance-budget-20261010.json` and `docs/qualification/jats-performance-results-20261010-offset-map.json`. Small, medium, large, named-entity and malformed-depth workloads stayed within the declared CPU, wall-time and memory bounds. The report pins its input-source, benchmark-script, budget and result hashes.

These single-process synthetic measurements do not cover Windows, disk/export, concurrency, startup/shutdown, retry/cancellation, or real-paper workloads; they do not establish production performance.

## Scientific, security, and custody limits

- Historical public aggregates report zero confirmed untouched eligible correction-backed positives and 363 eligible negative relationships across five DOI document IDs. They do not establish 15 independent works. The frozen minimum of at least one untouched positive and at least 50 eligible correct negatives across 15 independent works is unmet.
- No scientific source was acquired here. No reserved case was executed. Wave 3 was not run.
- All numerical results remain candidate-only. Hashes bind bytes but do not establish source authenticity, publication version, licensing, scientific scope, or correction applicability.
- Scoped changed-code reviews drove fixes for source-range wording, UI status transitions, Unicode count ranges, standardization morphology, and JATS ratio lookalikes. They did not complete a repository-wide authorization, persistence, export, or hostile-operator audit.
- A Codex Security scan-start route is unavailable here; CodeQL is not a substitute for a complete audit.
- No custodian-isolated executor was available. No production installation, migration, activation, protected-store access, or rollback was qualified. Effective access separation and independent egress remain external gates; preserve existing records and software.
- No additional spending, merge, release, public research finding, researcher contact, or Wave 3 execution occurred.

## Remaining qualification gates

The exact forward public commit needs fresh hosted CI, browser, Windows packaging, custody-worker, and CodeQL checks. Release/evaluation also requires human visual and assistive-technology review; a genuinely isolated custodian execution route with independently enforced egress; owner-side compatibility and access qualification; and the frozen source-only positive and 15-work negative evidence minima. Keep PR #12 draft and unmerged.
