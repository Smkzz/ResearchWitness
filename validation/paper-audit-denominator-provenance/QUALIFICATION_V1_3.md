# Count/percentage denominator provenance qualification v1.3

Status: local development replay and package qualification passed; new stacked
PR checks pending. This is post-hoc DEVELOPMENT evidence, not a blind or
holdout evaluation. Wave 3, merge, and release were not run.

## Frozen baseline and plan

- PR #10 remains open, draft, unmerged, and mergeable at
  `f2490bd55568915c501b3c81d1ae3d08fda18cad`; its tree is
  `2e38c8485c4cb9915b41318f5e45733d299bda50`.
- GitHub CI run `37576329966` and CodeQL run `37576329974` both completed
  successfully on that baseline.
- This branch starts at that exact PR #10 head. PR #10 has not been rewritten.
- Frozen implementation and Wave-3 gates are in
  `QUALIFICATION_PLAN_V1_3.md`. The file was committed before inspecting the
  14 implementation-level denominator failures and remains unchanged.
- The baseline local gate recorded 538 tests, 500/500 synthetic cases, 3/3
  historical verifier fixtures, contract v1.2, and wheel SHA-256
  `f9f6b05e52c8765a175d15acda4c75a18f23736443cbaac695d87b28f0b71317`.

## Contract v1.3

The structured-table and JATS cell-ratio percentage checks now use contract
v1.3. Historical v1.2 reports and evidence retain their original version and
interpretation.

Each candidate relationship gets a source-anchored denominator-resolution
record. It captures the relationship scope (population, subgroup, treatment
arm, timepoint, analysis set, outcome, unit, and percentage base), each
explicit denominator candidate, structural applicability, source anchor,
footnote linkage, scope comparison, selected candidate, and rejected
competitors with reasons. Candidate classes include cell-local, row-local,
subgroup-row, column-header, header-group, table-global, and linked-prose
denominators.

Resolution first requires structural applicability and compatible known scope.
Among compatible sources, the resolver ranks semantic scope matches and
specificity before using structural directness as a tie-break. A single
most-specific candidate is required. Equally ranked explicit denominators
produce `DENOMINATOR_AMBIGUOUS`; missing, conflicting, malformed,
footnote-dependent, weighted, adjusted, or missingness-dependent bases fail
closed. Arithmetic runs only after this resolution. A zero numerator cannot
select or validate a denominator by producing the same zero percentage for
multiple bases.

The report schema enforces resolved provenance for checked v1.3 relations.
The report HTML presents the selected denominator, its source, and rejected
competitors for candidates; skipped relations explain when scope was not
resolved. v1.2 schema records remain valid, and no v1.2 artifact was silently
reinterpreted.

## Development positives

The complete 33-report DEVELOPMENT replay reproduced every JSON and HTML
report deterministically.

- Three correction issues were eligible under the locked source-first review;
  all 3/3 were detected and all 5/5 target cells matched under v1.3.
- The full current v1.3 corpus produced 21 candidates: 5 known correction
  targets, 8 source-reproduced uncorrected discrepancies, and 8
  source-version-unverified discrepancies. All 21/21 had valid recomputed
  arithmetic; 0 were invalid or unresolved.
- The 19 historical v1.2 candidate slots remain reported as 17/19 (89.47%).
  The v1.3 source/scope re-audit found that two slots were not eligible because
  an available-case denominator was not explicit. On the 17 eligible slots,
  arithmetic validity is 17/17. The frozen 90% threshold did not change; the
  denominator changed only through the complete v1.3 eligibility replay.
- The four additional v1.3 candidates were source-adjudicated as
  version-unverified. Arithmetic validity alone does not establish that a
  paper is wrong or that a conclusion changes.

## Known denominator failures

The fixture artifact binds all 14 former false candidates and both
zero-numerator wrong-denominator records to the full v1.3 replay hash.

- Of the 14 former false candidates, 10 now use a source-valid local base and
  are checked matches; 4 fail closed as
  `MISSINGNESS_CHANGES_DENOMINATOR`. None emits a candidate.
- Both zero-numerator cases select local `N=3` and reject broader `N=5` before
  arithmetic. They no longer validate the wrong base through a coincident
  `0%` result.
- No wrong-denominator checked match remains in these 16 regression records.
- All 30 named adversarial scenarios pass. Coverage includes multi-level and
  duplicate headers, row and cell bases, treatment arms, subgroup/timepoint/
  analysis-set conflicts, footnotes, missingness, available cases, multiple
  response and weighted bases, 0% and 100%, malformed/grouped/Unicode numbers,
  extreme header depth, malformed spans, repeated IDs, and hostile markup.

## Development negatives

The locked source-first negative corpus contains 4,163 independently labelled
correct eligible relationships from 61 documents and 110 tables. The v1.3
negative runner did not load reserved records.

| Source join result | Relations | Share of 4,163 |
|---|---:|---:|
| Exact numerator, denominator, percentage, and precision join | 1,128 | 27.09% |
| Source-anchor-only join | 2,276 | 54.67% |
| No report relation joined | 759 | 18.23% |

Exact coverage increased from the frozen v1.2 result of 615/4,163 (14.77%)
after adding explicit percent-unit cues from applicable labels such as `n (%)`,
`No. (%)`, and `%`. The 50% exact-join target was not reached; it was a
descriptive target, not a frozen graduation gate.

There were 0 candidate emissions on source-labelled correct relations,
affecting 0 documents and 0 tables. There were 0 checked wrong-denominator
relations and 0 zero-numerator wrong-denominator checked matches. The 2,276
anchor-only records were skipped or unsupported under their recorded primary
reason; the remaining 759 source labels did not join any report relation.

The 4,163-label primary skip/join ledger reports: `ADJUSTED_RESULT` 39;
`DENOMINATOR_NOT_EXPLICIT` 158; `DENOMINATOR_SCOPE_UNRESOLVED` 66;
`FOOTNOTE_SCOPE_UNRESOLVED` 244; `GROUPED_INTEGER_FORMAT_UNSUPPORTED` 30;
`MALFORMED_NUMERIC_TOKEN` 12; `MISSINGNESS_CHANGES_DENOMINATOR` 115;
`PERCENT_UNIT_NOT_EXPLICIT` 370; `TABLE_STRUCTURE_UNSUPPORTED` 1,234;
`WEIGHTED_RESULT` 8; and 759 unmatched source labels. Every checked source
relation has the selected denominator anchor and full rejected-competitor
ledger.

## Relation telemetry

The positive 33-report replay has 2,069 potential relations: 311 eligible and
checked (290 matches, 21 mismatches), 812 incomplete, and 946 unsupported;
1,758 were skipped. Primary skip reasons were `ADJUSTED_RESULT` 26,
`DECIMAL_SEPARATOR_UNSUPPORTED` 3, `DENOMINATOR_NOT_EXPLICIT` 115,
`DENOMINATOR_SCOPE_UNRESOLVED` 5, `FOOTNOTE_SCOPE_UNRESOLVED` 314,
`GROUPED_INTEGER_FORMAT_UNSUPPORTED` 30, `MALFORMED_NUMERIC_TOKEN` 94,
`MISSINGNESS_CHANGES_DENOMINATOR` 213, `PERCENT_UNIT_NOT_EXPLICIT` 232, and
`TABLE_STRUCTURE_UNSUPPORTED` 726. All 311 checked records retain full
denominator provenance; accounting passes.

Across all 61 negative source reports, the detector telemetry contains 5,037
potential relations: 1,230 eligible/checked (1,189 matches and 41 mismatches),
1,293 incomplete, and 2,514 unsupported; accounting passes. These whole-report
counts are broader than the 4,163 independently source-labelled correct
relations. Only the source-ledger joins above are used for the false-candidate
result.

Both positive and negative JSON/HTML report pairs replayed identically (33/33
and 61/61).

## Reserved pools and information boundaries

No reserved record was passed to a detector, replay runner, or candidate join.
The development owner received no source identity, target cell, correction
value, or detector result from the positive custodian; the returned result was
aggregate-only.

The positive-custody check found an allocation deviation. The prior count of
22,305 reserved pairs came from a separate DOI-pair modulo-10 allocation,
which differs from the repository's frozen normalized-identifier SHA-256
modulo-5 rule. The custodian reports 225,080 metadata pairs and 45,211 reserved
assignments under the repository rule. Fourteen source-body pairs had already
been opened under the mismatched allocation. They are excluded from any
untouched-positive count, and the old `false` result is not an absence finding.
Fifty pairs had been metadata-screened under the mismatched allocation; exact
membership of the 14 body-opened pairs was not retained. The custodian has
since verified a canonical, hash-bound 225,080-pair allocation ledger and
deterministic order before any further body retrieval. Its five bucket counts
are 45,211, 44,783, 45,204, 44,885, and 44,997. All 50 legacy metadata-screened
pairs are excluded from further body retrieval and from the untouched-positive
count. The supplemental v1.3 screening protocol records this chronology. At
this qualification cutoff, no canonical, contract-eligible reserved positive
is confirmed; the earlier `false` was not an absence finding.

The reserved-negative custodian independently source-reviewed available
material under v1.3 without running or joining the detector. The custodian
confirmed 363 eligible/correct relations across 10 tables and 5 documents.
Another 191 ledger-labeled eligible/correct relations were not counted because
their denominator scope could not be independently confirmed under v1.3.
Available ledgers cover 950/1,152 relations, 20/31 relation-bearing tables,
and 13/16 documents; the pool is incomplete. Source-version integrity passed
for all 13 available source documents and both sealed records. The 363
validated relations exceed the relation-count threshold, but five documents
do not meet the frozen 15-document threshold. The two sealed batch hashes are
`feb3e9862f7cc3ceeb139f77469a26efa28d64d701a5091270e406aced0543e5` and
`c207fee7d4e349aed1370ba042f19f01fe213f84f2160fe0bb39ba1891234813`.
No reserved-negative detector execution or join occurred.

The canonical positive custodian screened two pairs after verifying the
canonical allocation and order. One was fully assessed and rejected as outside
the correction scope; one remained unresolved because publisher material was
inaccessible. No eligible positive is confirmed, and this is not an absence
finding. Target details remained hidden and no detector was run. The custodian
reported low confidence. Automatic review rejected an attempted Crossref
metadata fetch because it would transmit a custody-held identifier externally;
the custodian stopped and did not use an alternate retrieval route. The
canonical search is therefore incomplete.

The earlier process deviation remains disclosed: 14 source-body pairs were
opened under a mismatched allocation, among 50 metadata-screened pairs, whose
exact membership was not retained. All 50 legacy pairs were excluded from
further body retrieval and from the untouched-positive count. No identities,
target details, correction values, or detector outputs were disclosed to the
development runner. Neither reserved pool was used to tune detector behavior.

## Local qualification and decision

- Pytest: **593 passed**.
- The 30-case adversarial suite, 14 denominator-failure fixtures, both
  zero-numerator regressions, percentage tests, and full v1.3 replays pass.
- Synthetic conformance: **500/500**; historical verifier fixtures: **3/3**.
- Generated schema checks, source checksums, compilation, trusted-core static
  checks, clean wheel installation, and CLI smoke checks: **pass**.
- Two wheel builds were byte-identical. Wheel SHA-256:
  `4a308752049c4006d5acf7127c443c4f097410b8c1f777d58a2a4fdfbee6bd9b`.
- GitHub CI and CodeQL are pending for the new stacked draft PR; PR #10's
  existing checks remain passed.

**NOT READY TO FREEZE FOR WAVE 3.** The development contract gates pass, but
no eligible unseen positive is confirmed and the incomplete v1.3 negative
reserve has only five validated documents, below the frozen 15-document
threshold. Wave 3, merge, and release remain unrun.

### Decision answers

1. Denominator provenance removed all 14 known local-subgroup false candidates:
   10 became valid matches and 4 failed closed on missingness.
2. A zero numerator cannot make a wrong denominator acceptable; resolution and
   provenance are required before arithmetic.
3. Current v1.3 candidate arithmetic validity is 21/21 (100%); the historical
   raw comparison remains 17/19, with two slots now scope-ineligible under v1.3.
4. False-candidate emissions on the independently labelled correct negative
   corpus are 0/4,163, across 0 documents and 0 tables.
5. Exact operand joining covers 1,128/4,163 (27.09%); this remains below the
   descriptive 50% target.
6. The v1.3 detector contract and development replay are locally stable; the
   overall capability is not ready for Wave 3 while reserve gates are open.
7. No truly untouched, contract-eligible reserved positive is confirmed.
8. The v1.3 reserve-negative relation count is 363 across 5 documents and 10
   tables; source review is incomplete and the 15-document threshold is not met.
9. `READY_TO_FREEZE_FOR_WAVE_3` is **false**.
10. Blocking sentence: No eligible unseen positive is confirmed, and the
    incomplete v1.3 negative reserve validates only 363 eligible relations
    across 5 documents, below the frozen 15-document threshold.
11. ResearchWitness can claim only that it recomputes supported,
    source-anchored count/denominator/percentage relationships and emits
    arithmetic discrepancy candidates for human review.
12. ResearchWitness must not claim that it detects all research errors,
    establishes that a paper is wrong, proves a scientific result invalid, or
    determines that a discrepancy changes a conclusion or indicates
    misconduct.
13. Single next action: complete source-only v1.3 custody screening of both
    canonical reserve pools through an approved source-access route, then
    update the readiness table; do not run Wave 3 as part of that action.
