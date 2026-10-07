# Count/percentage denominator provenance qualification plan v1.3

Status: frozen before implementation-level inspection of the 14 known
denominator-scope false candidates. Date: 2026-10-07.

## Baseline

- Repository: `Smkzz/ResearchWitness`.
- PR #10: open, draft, unmerged, mergeable; head
  `f2490bd55568915c501b3c81d1ae3d08fda18cad`; tree
  `2e38c8485c4cb9915b41318f5e45733d299bda50`.
- PR #10 CI run `37576329966` and CodeQL run `37576329974`: success.
- New branch: `codex/paper-audit-denominator-provenance`, created at the exact
  PR #10 head. PR #10 will not be rewritten.
- Baseline local quality gate: Python 3.12.14; 538 tests passed; synthetic
  conformance 500/500; historical verifier fixtures 3/3; contract v1.2;
  wheel SHA-256
  `f9f6b05e52c8765a175d15acda4c75a18f23736443cbaac695d87b28f0b71317`;
  reproducible wheel builds; source checksums, generated schemas, compile,
  trusted-core static checks, install, CLI checks, and frozen-screen checks all
  passed. Worktree was clean before branch creation.

## Frozen v1.3 development qualification criteria

The count/percentage contract is not qualified unless all of the following
hold after the complete v1.3 replay:

1. All 14 known denominator-scope false candidates disappear for the correct
   reason: a source-valid match or a fail-closed scope/eligibility result.
2. Both zero-numerator wrong-denominator records are identified as
   denominator-selection failures, never validated by arithmetic coincidence.
3. Every known correction target cell still detects.
4. All eight fully source-reproduced non-target discrepancies behave
   consistently, unless source denominator review proves an earlier relation
   invalid; any downgrade is recorded with evidence.
5. No new false candidate appears on the independently labelled eligible
   negative corpus.
6. Each checked relationship records its selected denominator source and why
   it outranked every competing candidate. Rejected candidates carry explicit
   reasons.
7. Deterministic replay remains exact.
8. Local and GitHub CI and CodeQL pass.

The separate development-candidate arithmetic-validity gate remains at least
90%. Its denominator may change only when the full replay under v1.3 establishes
that a prior relation was not eligible; thresholds and labels will not be
changed after seeing results.

## Frozen Wave-3 readiness criteria

Before final replay, readiness requires all criteria below, without changing
thresholds after results are observed:

1. At least one untouched reserved eligible correction-backed positive.
2. At least 50 untouched reserved eligible negative relationships across at
   least 15 documents.
3. All known denominator-scope development failures remediated or
   fail-closed.
4. Zero silent denominator validation by arithmetic coincidence.
5. Development candidate arithmetic validity of at least 90%.
6. All known correction target cells detected in development.
7. No unexplained parser artifacts.
8. Exact relation-level telemetry accounting passes.
9. Deterministic replay.
10. GitHub CI passes.
11. GitHub CodeQL passes.
12. Reserved cases have never been used to tune detector behavior.

Exact operand-level negative join coverage is a target of at least 50% if
technically feasible without risky heuristics. This is descriptive and is not
a Wave-3 gate.

## Scope and evidence boundaries

This wave changes only count/percentage denominator provenance and its shared
report/schema infrastructure. Other detector families remain out of scope.
Development evidence may be inspected and replayed. The independent custodian
may inspect reserved-positive eligibility, but the implementation runner must
not receive reserve identities, target details, or detector output. The
reserved-negative source-only pool must not be joined to detector output.

Wave 3, merge, release, and publication are not authorized.
