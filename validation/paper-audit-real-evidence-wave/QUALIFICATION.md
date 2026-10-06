# Real-evidence and capability-graduation review

**Decision:** no detector family is ready for a Wave 3 freeze. This review
adds source-version checks and an aggregate follow-up to the current v1.1
development replay. It is post-hoc development evidence, not a blind or
independent performance evaluation. Wave 3 was not run.

## Starting point

- Canonical starting commit: `57fedcd9efa9afaabd76bc56b1bc06f1063354fe`.
- Tree: `a0490f241bd98616958360f60246fb9d804d5b23`.
- The starting worktree was clean on branch
  `codex/paper-audit-real-evidence-wave`.
- PR #7 remained open, draft, unmerged, and mergeable. Its CI and CodeQL
  workflows passed at the starting commit. This work is on a separate branch;
  PR #7 and PR #6 were not changed.
- Active source-mapped detector contracts are version 1.1.

The engineering gate passed at the baseline and after the current documentation
and validation updates:
484 tests, synthetic conformance 500/500, historical verifier fixtures 3/3,
static trusted-core checks, schemas, checksums, compile checks, reproducible
wheel builds, clean wheel installation, and CLI smoke checks. The two wheel
builds were byte-identical; SHA-256
`aa88b1ab94bede82c82f71acecc1bfebf012d5909080de0a8584c416980c81c7`.

## Current source-native development replay

The current v1.1 replay was rerun on the pinned 33-document JATS corpus using
the private eligibility file. The artifact
[`SOURCE_ADJUDICATION_AGGREGATE.json`](SOURCE_ADJUDICATION_AGGREGATE.json)
contains aggregate counts only.

| Measure | Result |
| --- | ---: |
| Source documents | 33 |
| Correction-backed issues considered | 16 |
| Issues eligible under current contracts | 2/16 |
| Eligible issues detected | 2/2 |
| Correction target cells detected | 4/4 |
| Eligible issues by detector | 1 direct JATS cell ratio; 1 structured-table percentage |
| Selected controls with candidates | 0/17 |
| Qualified matched real hard negatives | 0 |
| Candidate items | 12 |
| Candidate items mapped to correction targets | 4 |
| Source-reviewed internal discrepancies outside target corrections | 2 |
| Unresolved candidate items | 6 |
| Candidate precision | Not estimated |
| Reports with some incomplete table or detector coverage | 33/33 |
| JSON and HTML reports byte-repeatable | 33/33 |

The four matched target cells come from two distinct correction mechanisms
within the count/percentage family: two structured JATS cells and two direct
`n/N (%)` cells. The eight unmatched candidates are not all false positives:
two are source-level internal mismatches confirmed against a publisher PDF;
six remain unresolved. The selected controls provide no eligible matched
negative denominator, so neither candidate precision nor a false-candidate
rate can be estimated. The replay runner reports all eight as unadjudicated;
the two source-level checks are a separate post-replay review, not detector
labels.

The older contract replay is recorded separately: it yielded 1/16 eligible
issues, 1/1 detected, and 2/2 target cells. Contract v1.1 adds the direct-cell
ratio positive. These are two versioned runs, not a combined sensitivity
estimate.

## Detector-family decisions

“Matched negative” below means a real source object that was independently
checked to be structurally eligible for the same relation and should produce no
candidate. Selected papers with no candidates do not count as matched negatives
when their relevant objects were unsupported, incomplete, or not eligible.

| Family | Real correction-positive evidence | Matched real negatives | Decision |
| --- | --- | --- | --- |
| Structured and direct-cell count/percentage | 2 eligible issues; both detected; 4/4 corrected cells | 0 qualified; 17 general controls emitted no candidates but are not certified or matched | **NOT READY** — evidence exists, but six replay candidates remain unresolved and the matched-negative requirement is unmet. |
| Sample flow | 0 eligible positives among 6 correction records screened; one source-native relation was skipped because disjointness, exhaustiveness, or sequential removal was not established | 0 qualified | **NOT READY** — the narrow contract has no correction-backed positive. |
| PRISMA/synthesis flow | 0 eligible positives among 5 correction records screened; 23 potential flow objects were skipped or not applicable in the source corpus | 0 qualified | **NOT READY** — corrections found involve stages, source scopes, or images outside the narrow relation. |
| Unadjusted 2×2 odds ratio | 0 eligible positives among 4 correction leads; one plausible source spans separate tables and needs a cross-table join | 0 qualified | **NOT READY** — no correction-backed same-row source mapping. |
| SD/SE/n | 0 eligible positives among 6 correction records screened | 0 qualified | **EXPERIMENTAL** — methods rely on SEM, model-based, weighted, repeated-measure, bootstrap, or transformed uncertainty. |
| Simple rates | No eligible correction positive | 0 qualified | **UNSUPPORTED** — no safe corpus basis to implement it. |
| Cross-section numeric identity | No source-mapped correction positive | 0 qualified | **HELPER ONLY** — complete population, outcome, metric, time, unit, and adjustment identity is not extracted from sources. |
| Explicit count-marker discovery | Active locator; it reports repeated count assertions and possible scope changes, not errors | Not an error-classification family | **ACTIVE, CANDIDATE-ONLY** — no claim of contradiction follows from count discovery. |

Case-level source/correction evidence for the two eligible positives and
candidate notes are kept in a local working dossier outside this repository.
The committed JSON deliberately omits paper identifiers, hashes, arithmetic
records, and case-level findings.

## Wave-2 historical candidate follow-up

This is the 15-item off-target paper-audit candidate set. It is separate from
the frozen 15-case verifier representability screen described below.

The locked set still reproduces 14 archived JATS-derived arithmetic candidates
and one non-exact correction pointer. Follow-up publisher-source checks
confirmed four printed mismatches across two source records. A separate
publisher PDF contained a 38/39 count difference whose population scope remains
unclear. Six selected Table 2 values were unchanged in the official corrected
replacement table and do not map exactly to the correction. Three other
selected percentages remain JATS-only because the publisher PDF could not be
retrieved. One candidate has a correction pointer at a location where the old
screen used the wrong denominator. All 15 remain unresolved as to supplements,
complete correction history, later versions, and scientific consequence.
These observations do not establish paper errors or scientific consequences.

The separate frozen verifier screen remains unchanged. A source follow-up for
its backward-heat case is recorded in
[`validation/verifier-wave/SOURCE_FOLLOWUP.md`](../verifier-wave/SOURCE_FOLLOWUP.md).
The official erratum supports the concise counterexample description in that
screen; it does not make PDE stability checks representable in the current
checker set.

## Negative-control and coverage limits

The 17 selected source-native controls yielded zero candidates. However,
source structure was often incomplete or unsupported, and zero of them was
qualified as a matched hard negative for the active percentage contracts.
There is no real-world false-positive estimate. The 66 hard-negative scenarios
in unit tests and synthetic regression fixtures all produced zero candidates;
those fixtures are not papers.

Coverage remains narrow and must be visible to report readers. In the current
corpus, direct-cell ratios checked 76 operands and emitted 9 candidates;
structured percentages checked 63 operands and emitted 3. Sample flow checked
no object because its only applicable relation was skipped for unclear flow
semantics. PRISMA had 23 potential objects and no eligible arithmetic. No 2×2
table was applicable, and SD/SE/n checked no row. All 33 reports retain at
least one incomplete or unsupported area.

## Wave 3 readiness and case availability

**Not ready to freeze.** No family meets all graduation rules, chiefly because
there are no qualified matched real negatives; flow, PRISMA, and 2×2 also have
no correction-backed eligible positives. Count/percentage evidence is useful
but remains development-only due six unresolved candidates and incomplete
coverage.

Confirmed unused eligible positives: **0 for every family**. External case
availability is unknown. Three bibliographic-only DOI pairs remain uninspected
and were not replayed. They remain potential future cases, not established
positives. No release, publication, or external action is part of this review.
