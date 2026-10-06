# Evidence maturation qualification

**Decision: NOT READY FOR WAVE 3.** This is aggregate, post-hoc development
evidence. Wave 3 was not run; no release or publication was made. Detector
families were not broadened.

## Baseline and scope

- PR #8 was open, draft, unmerged, and mergeable at head
  `80f1ee0189a2618377239702046160d7d0208f34`, tree
  `c42732f17a2a7bb77d1d16d34a7f3ba1b5247610`.
- GitHub CI and CodeQL passed at that baseline. This work is on a separate
  branch stacked on PR #8; PRs #6, #7, and #8 were not changed.
- Active source-mapped percentage contracts are v1.1. The new source-native
  replay used the same 33 development documents and reproduced 33/33 JSON and
  HTML reports byte-for-byte.

## Correction-backed development positives

The replay considered 16 correction issues. Its existing eligibility ledger
reports 2/16 eligible, 2/2 detected, and 4/4 target cells detected. A separate
conservative contract review finds only **1/16 definitely eligible**: the
second issue uses cumulative overlapping percentage thresholds, and v1.1
excludes overlapping categories. The source correction and arithmetic are
clear, but its eligibility is not. Until the contract is clarified, the
primary conservative result is 1/1 eligible issue and 2/2 target cells
detected. The replay's 2/2 and 4/4 figures remain reported as historical
runner output, not the conservative primary result.

All 12 detector candidates have now been source-adjudicated:

- 4 map to known correction target cells.
- 8 are source-reproduced printed arithmetic discrepancies outside those
  correction targets. The JATS and publisher rendering agreed; supplementary
  material, correction history, and later versions were checked for all 8.
- 0 were benign scope or rounding cases, source/parser artifacts, or unresolved.

This yields a **strict known-target candidate rate of 4/12 (33.3%)** and a
broader **source-reproduced arithmetic-discrepancy rate of 12/12 (100%)**.
Both are post-hoc candidate-item summaries from development data. The eight
internal discrepancies establish only that printed relationships do not
recompute at the displayed precision under the source-interpreted operands.
They do not establish which operand is wrong, the underlying data, scientific
consequence, paper-level wrongness, or misconduct.

## Relationship-level real negatives

The curator froze source-derived labels before joining them to candidate
outputs. All 99 initially labeled relationships recompute correctly under
their frozen operands, but **only 18 pass the exact active v1.1 eligibility
checks**: 12 structured table relationships and 6 direct same-cell
relationships, across 3 source documents and 3 tables. The other 81 are
excluded by first-failing contract gates:

| Reason | Relations |
| --- | ---: |
| Unsupported table structure | 40 |
| Local row denominator | 20 |
| Conflicting header denominators | 8 |
| Percent unit not explicit | 6 |
| Unsupported space-grouped header denominator | 3 |
| Direct-cell footnote semantics unresolved | 2 |
| Required direct `n/N (%)` syntax missing | 2 |
| **Total excluded** | **81** |

The three grouped-header relations were initially interpreted by the runtime
parser as denominator 10 from a header formatted as `10 015`. I corrected the
integer-token boundary so it now fails closed on space-grouped thousands
instead of partially reading the value. The exact contract still excludes
those relations until grouped denominator syntax is supported and qualified.

No detector candidate matched any of the 18 eligible relations: **0/18**.
No candidate appeared on the eligible relation in any of the three represented
documents: **0/3**. These raw counts are not a general false-positive estimate;
the set is small and clustered in only three documents. The larger original
99-label count must not be presented as the matched-negative denominator.

## Coverage in the 33-document replay

The replay discovered 123 tables; 62 had reliable structure and 61 did not.
All 33 reports had at least one incomplete or unsupported area.

| Detector | Table/object coverage | Operand coverage |
| --- | --- | --- |
| Direct JATS cell ratio | 2 eligible, 8 incomplete, 113 not applicable tables; 8 skipped objects | 194 potential; 76 checked, 67 matches, 9 mismatch candidates, 118 skipped |
| Structured table percentage | 1 eligible, 84 incomplete, 27 not applicable, 11 unsupported tables | 1,542 potential; 63 checked, 60 matches, 3 mismatch candidates, 1,479 skipped |
| Sample flow | 1 applicable object, skipped because flow disjointness/exhaustiveness/sequence was not explicit | 6 potential, 0 checked, 6 skipped |
| PRISMA/synthesis flow | 23 potential objects, 0 checked, 23 skipped | No operand checks |
| Unadjusted 2×2 | 123 tables not applicable | No operand checks |
| SD/SE/n | 2 incomplete, 114 not applicable, 7 unsupported tables | 227 potential rows, 0 checked, 227 skipped |

Exact normalized reason occurrences per table result are in
[`EVIDENCE_MATURATION_SUMMARY.json`](EVIDENCE_MATURATION_SUMMARY.json). Those
counts are grouped by table status and can overlap; they are not counts of
skipped operands. The percentage replay does not currently emit exact
relation-level skip-reason counts. Sample-flow and PRISMA reason counts are
object-level; PRISMA reasons overlap.

## Correction search and other families

A deterministic DOI-pair split allocated 17 metadata pairs before screening:
16 DEVELOPMENT and 1 RESERVED. Seven development notices were body-screened;
none contained an eligible relation. One more development pair was rejected
for a bibliographic relation mismatch; 8 remain not yet body-screened. The
reserved pair remains metadata-only and its eligibility is unknown, so there
are **0 confirmed reserved eligible positives**. A separate contaminated
search batch (22 unique leads across 25 result surfaces) was quarantined
before allocation. This was a bounded, non-exhaustive search.

| Family | Search result | Status |
| --- | --- | --- |
| Count/percentage | 4 allocated; 2 body-ineligible; 2 not yet screened; 0 new eligible | Development-supported, not ready |
| Sample flow / clinical trial flow | Largest lead pool: 9 allocated in the clinical-flow/count grouping, 1 reserved metadata-only; 0 eligible confirmed | Evidence sparse; strongest next family to screen for case availability |
| PRISMA/synthesis flow | 3 allocated; 2 body-ineligible; 1 not yet screened; 0 eligible | Evidence sparse |
| Unadjusted 2×2 | 1 allocated and body-ineligible; 0 eligible | Evidence sparse |
| SD/SE/n | No correction leads allocated; 0 eligible | Experimental |
| Simple rates | No eligible correction-backed evidence | Unsupported |
| Cross-section numeric identity | No source-mapped correction evidence | Helper only |

The count/percentage family is not ready for Wave 3 because the matched
negative set is below the 50–100 relationship and at-least-15-document target,
one correction's overlap eligibility is unresolved, no unused eligible
positive is confirmed in reserve, and relation-level skip-reason telemetry is
missing. Deterministic replay, baseline CI, and baseline CodeQL passed; the new
branch qualification is recorded after the local quality gate and GitHub
checks finish.

## Engineering change and qualification

Evidence review found that an integer parser could read a grouped header such
as `n = 10 015` as `n = 10`. I changed the parser boundary to reject a partial
integer when a digit group follows a space, comma, or decimal separator. The
change is fail-closed and does not expand the detector contract. Regression
tests cover JATS table percentages, Markdown table percentages, and explicit
count-marker extraction.

The local offline quality gate passed on Python 3.12.14:

- 495 pytest cases passed.
- Synthetic conformance: 500/500; historical verifier fixtures: 3/3.
- Trusted-core static scan, schema drift, source checksums, frozen-screen
  review, compile checks, two reproducible wheel builds, clean install, and
  CLI smoke checks passed.
- Wheel SHA-256: `389d99647d3c01473406d0079dc84398569f9cd8f21e35c2d88d14476fec3606`.
- Runtime dependencies: none.

Draft [PR #9](https://github.com/Smkzz/ResearchWitness/pull/9) is open,
unmerged, and mergeable. It is stacked on the PR #8 head branch. Python 3.11,
3.12, and 3.13 jobs, the release gate, CodeQL, and the Analyze Python job all
passed at the initial PR head. The final local commit, final tree, and remote
head are recorded in the task completion summary.

## Nine qualification questions

1. **Is count/percentage READY_FOR_WAVE_3?** No. It is not ready.
2. **What is missing?** A substantial eligible negative set across at least
   15 documents, a clarified overlap rule, a confirmed unused eligible
   reserved positive, and exact relation-level skip-reason telemetry.
3. **How many unused eligible positives remain reserved?** 0 confirmed. One
   metadata-only reserved lead has unknown eligibility.
4. **How many real matched-negative relations exist?** 18 across 3 documents.
5. **What is the best real-world development estimate of candidate quality?**
   Strict known-target 4/12 (33.3%); source-reproduced arithmetic discrepancy
   12/12 (100%). These are post-hoc development figures, not unseen performance.
6. **Did ResearchWitness surface source-reproduced discrepancies outside the
   benchmark corrections?** Yes: 8 printed relationships were reproduced
   against publisher renderings and JATS, with supplements, correction
   histories, and later versions checked. No scientific consequence or
   misconduct is established.
7. **Which other family is strongest to pursue next?** Sample flow has the
   largest bounded correction lead pool, but it still has 0 eligible positives;
   screen those leads before changing its detector.
8. **Is there enough evidence for a focused public research preview?** No.
   The evidence remains post-hoc, lacks an adequate matched-negative corpus,
   and has no confirmed reserved eligible positive.
9. **What is the single highest-value next action?** Expand the independent
   v1.1 matched-negative set across at least 15 source documents while
   resolving overlap semantics and adding relation-level skip-reason reporting.

## Final repository and check record

- Baseline PR #8 head/tree: `80f1ee0189a2618377239702046160d7d0208f34` /
  `c42732f17a2a7bb77d1d16d34a7f3ba1b5247610`.
- The work is on branch `codex/paper-audit-evidence-maturation` with a clean
  worktree after the qualification commit.
- Draft PR #9 is stacked on PR #8 and remains open, unmerged, and mergeable.
- GitHub CI matrix, release gate, CodeQL, and Analyze Python: pass.
- Pytest: 495 passed.
- Synthetic conformance: 500/500.
- Historical verifier fixtures: 3/3.
- Wheel SHA-256: `389d99647d3c01473406d0079dc84398569f9cd8f21e35c2d88d14476fec3606`.
- Schemas, static checks, checksums, compile, reproducible wheels, install,
  and CLI checks: pass.
