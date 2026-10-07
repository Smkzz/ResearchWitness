# Count/percentage v1.2 qualification

**Decision: `NOT_READY_TO_FREEZE_FOR_WAVE_3`.** This is post-hoc DEVELOPMENT evidence. The frozen thresholds were not changed, and no Wave 3, merge, release, or publication was run.

## Contract

Percentage detectors moved from contract v1.1 to v1.2; unrelated detector contracts remain v1.1. A cell-local `count / explicit denominator / percentage` relationship is evaluated on its own operands, scope, units, group, timepoint, analysis set, and display precision. Overlap among sibling thresholds does not make that arithmetic relationship ambiguous when those facts are explicit. Category sums, totals, partitions, complements, and mutual-exclusivity claims remain out of scope. Weighted, adjusted, footnote-modified, or missingness-dependent bases remain excluded when they alter or obscure the relation.

The table detector also resolves explicit body subgroup `n/N` rows as denominator anchors. If a subgroup denominator is present but unresolved, it does not fall back to a broader header denominator. Exact decimal arithmetic uses `ROUND_HALF_UP` at the displayed precision. The old v1.1 replay artifacts remain unchanged.

Regression coverage includes overlapping thresholds, body subgroup denominators and fail-closed cases, grouped numbers, decimal separators, malformed tokens, local/duplicate denominators, footnotes, and rounding. The focused parser/telemetry/replay suite passed **109 tests**.

## Positive replay and candidates

- 33/33 positive-corpus reports reproduced identical JSON and HTML.
- 16 correction issues were considered; 3 were unquestionably eligible under v1.2 and all 3 were detected. All 5/5 eligible target cells were detected. Thirteen issues were unsupported by the frozen contract or available evidence.
- All 19 current candidates were adjudicated: 5 known correction targets, 8 source-reproduced non-target printed arithmetic discrepancies, 4 source-reproduced discrepancies with version status unverified, and 2 candidates whose denominator was not explicit. There were 0 parser artifacts and 0 unresolved candidates.
- Candidate arithmetic validity is **17/19 = 89.47%**, below the frozen 90% threshold. The eight non-target discrepancies are fully classified in the evidence capsules: JATS 8/8, publisher rendering 8/8, same source version 8/8, supplements checked 8/8, correction search 8/8, later version checked 8/8, fully classified 8/8, unresolved 0. Seven original publisher PDFs were captured; one publisher page was verified but its signed PDF could not be captured.

## Source-first negatives

Batches 1–7 reviewed 4,776 source relations across 177 distinct DEVELOPMENT documents and 333 table wraps: 3,977 eligible-correct, 86 eligible-incorrect, and 713 ineligible. The locked negative manifest contains **4,163 correct eligible relations across 110 tables and 61 distinct documents**, including the 186-relation preexisting manifest. The source labels were sealed before detector output was joined; no reserved records were included.

Exact source operands joined to 615/4,163 negative labels (14.77%). In addition, 3,404 source-labeled locations paired to a report relation by source anchor. This broader anchor accounting found:

- **14 emitted false candidates across 2 documents**, where the detector used a broader header denominator instead of the explicitly supported local subgroup denominator. These are 14/4,163 relations (0.34%) and 2/61 documents (3.28%). The one-sided exact 95% upper bound for the document event rate is 9.96%.
- **2 more wrong-denominator report records marked as arithmetic matches** because both source and parsed numerators were zero. These are not exact operand joins and are excluded from the 615 checked-match count.

The overall negative-bearing reports contain 49 eligible mismatch telemetry records. Fourteen map by source anchor to independently labeled correct relations; the remaining 35 were not source-labeled correct-negative hits and are not classified here. All 61 JSON and HTML report pairs were repeatable.

## Relation telemetry

Counts below partition the potential relations; the listed primary reasons sum exactly to `INCOMPLETE + UNSUPPORTED`.

| Replay | Potential | Applicable | Eligible/checked | Matches | Mismatches | Incomplete | Unsupported | Skipped | Invariant |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Positive corpus (33 reports) | 2,069 | 2,069 | 222 | 203 | 19 | 902 | 945 | 1,847 | Pass |
| Negative corpus (61 reports) | 5,037 | 5,037 | 671 | 622 | 49 | 1,854 | 2,512 | 4,366 | Pass |

Positive primary skip reasons: `ADJUSTED_RESULT` 26; `CONFLICTING_HEADER_DENOMINATORS` 134; `DECIMAL_SEPARATOR_UNSUPPORTED` 3; `DENOMINATOR_NOT_EXPLICIT` 149; `FOOTNOTE_SCOPE_UNRESOLVED` 246; `GROUPED_INTEGER_FORMAT_UNSUPPORTED` 30; `LOCAL_ROW_DENOMINATOR` 34; `MALFORMED_NUMERIC_TOKEN` 88; `MISSINGNESS_CHANGES_DENOMINATOR` 198; `PERCENT_UNIT_NOT_EXPLICIT` 213; `TABLE_STRUCTURE_UNSUPPORTED` 726.

Negative primary skip reasons: `ADJUSTED_RESULT` 63; `CONFLICTING_HEADER_DENOMINATORS` 223; `DECIMAL_SEPARATOR_UNSUPPORTED` 16; `DENOMINATOR_NOT_EXPLICIT` 217; `FOOTNOTE_SCOPE_UNRESOLVED` 473; `GROUPED_INTEGER_FORMAT_UNSUPPORTED` 119; `LOCAL_ROW_DENOMINATOR` 73; `MALFORMED_NUMERIC_TOKEN` 143; `MISSINGNESS_CHANGES_DENOMINATOR` 68; `OPERANDS_OUTSIDE_PROPORTION_DOMAIN` 3; `PERCENT_UNIT_NOT_EXPLICIT` 935; `TABLE_STRUCTURE_UNSUPPORTED` 2,015; `WEIGHTED_RESULT` 18.

## Correction search and reserved pool

The allocated development search covered 16 pairs: 13 had body/source-level screening and 3 remained metadata-only or body-unavailable. It confirmed 0 new eligible positives; 9 were ineligible, 1 original was already corrected online, 3 were unavailable or version-uncertain, 2 remained cell-local potentials unresolved, and 1 correction target was rejected for metadata mismatch. These disposition flags can overlap as recorded in the allocation summary. Four prior development pairs are reported separately; they yielded 2 eligible issues and 3 confirmed target cells before the v1.2 replay.

The separate custodian confirmed **0 eligible reserved correction positives**. One reserved correction lead was opened and screened by that custodian and found ineligible; its details remain sealed from the runner. A source-reviewed subset of the reserved negative pool contains 1,152 correct relations across 31 tables and 16 documents, exceeding the 50/15 reserve minimum. The cumulative reserve review is incomplete because of earlier identity mismatches. No reserved detector output was joined or inspected.

The source-review reassignment and the accidental opening of the positive-eligibility artifact before the reassigned reviewer began B6/B7 are recorded in `SOURCE_REVIEW_PROCESS_NOTES_V1_2.md`. No B6/B7 source body or negative score had been opened by the exposed reviewer.

## Frozen graduation gates

| Gate | Result | Evidence |
|---|---|---|
| Eligible correction-backed development positive | Pass | 3 issues; 5/5 target cells detected |
| At least 50 correct negatives across 15 documents | Pass | 4,163 relations; 110 tables; 61 documents |
| Every eligible target detected and candidate arithmetic validity at least 90% | **Fail** | Targets 5/5; candidate validity 17/19 (89.47%) |
| Negative false-candidate limits | Pass | 14/4,163 relations; 2/61 documents; exact upper bound 9.96% |
| Candidate adjudication and parser-artifact gate | Pass | 19/19 adjudicated; 0 parser artifacts; 0 unresolved |
| Relation telemetry accounting | Pass | Both status partitions and primary-reason sums verified |
| Deterministic replay | Pass | Positive 33/33; negative 61/61 JSON and HTML |
| Local qualification, GitHub CI, CodeQL | Pass | 538 tests; synthetic 500/500; historical 3/3; final CI/CodeQL results recorded on the stacked PR |
| Unseen eligible reserved positive | **Fail** | 0 confirmed; custodian-screened lead was ineligible |
| Reserved negative pool | Pass on verified subset | 1,152 relations across 16 documents; cumulative reserve review incomplete; no detector join |

## Local qualification

- Pytest: **538 passed**.
- Synthetic conformance: **500/500**.
- Historical verifier fixtures: **3/3**.
- Trusted-core static checks, schema drift, source checksums, compile, and frozen-screen review: **pass**.
- Two wheel builds were byte-identical; clean-install and CLI smoke checks passed.
- Wheel SHA-256: `f9f6b05e52c8765a175d15acda4c75a18f23736443cbaac695d87b28f0b71317`.

## Decision answers

1. **Ready to freeze for Wave 3?** No.
2. **Which criteria passed?** The eligible-positive and target-detection parts, negative corpus size, false-candidate limits, adjudication, telemetry accounting, deterministic replay, local qualification/CI/CodeQL, and the verified reserved-negative subset.
3. **Which criteria failed?** Candidate arithmetic validity is 17/19, below 90%; no eligible reserved correction positive remains unseen.
4. **How many independent eligible negative relations exist?** 4,163.
5. **Across how many documents?** 61, with 110 represented tables.
6. **What false-candidate behavior was observed?** Fourteen emitted denominator-scope false candidates on source-labeled correct relations, across two documents; two other wrong-denominator results were incorrectly marked matches because the numerator was zero. Exact operand coverage was 615/4,163.
7. **Is the cumulative-overlap case eligible under v1.2?** Yes, for explicit cell-local ratios; overlap does not justify category-sum, partition, complement, or percentage-sum checks.
8. **How many confirmed reserved eligible positives remain unseen?** Zero. One lead was screened by the separate custodian and found ineligible; reserved negative outputs remain unopened to the runner.
9. **How many fully source-reproduced uncorrected arithmetic discrepancies are outside known targets?** Eight. Four more arithmetic discrepancies have unverified source-version status and are not included in that fully classified count.
10. **What can ResearchWitness now legitimately claim?** It can recompute supported explicit count/denominator/percentage relationships and surface source-anchored arithmetic discrepancies for human review.
11. **What must it still not claim?** Reliable fact-checking or discovery of scientific errors, paper invalidity, effects on results or conclusions, or misconduct.
12. **What is the single next action?** Run a separate preregistered, source-first qualification pass that secures an eligible unseen reserved correction positive and resolves the candidate-precision shortfall, using the subgroup-denominator failures as scoped remediation input before any Wave 3.
