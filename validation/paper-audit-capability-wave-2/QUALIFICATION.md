# Paper-audit capability wave 2 qualification

**Purpose:** expand active source-mapped paper checks while preserving narrow
eligibility and candidate-only reporting. This is development work, not a
sealed or independent evaluation. Wave 3 was not run.

## Baseline

- Canonical base: open draft PR #6 at commit
  `94cd15859ec37a965db5f0a2f6dc7ebf620f56c5`, tree
  `de5b083c1afc455750a3efb5898ee7ec110b13aa`.
- The local starting commit `5b4ddbedc75efe35e0dacca620ee049b58902c48`
  has the same tree. The wave-2 work used branch
  `codex/paper-audit-capability-wave-2`; PR #6 was not changed.
- PR #6 was open, draft, and unmerged at baseline verification. Its GitHub CI
  and CodeQL checks passed. See [`BASELINE.md`](BASELINE.md).

## Active capability families

The registry distinguishes `ACTIVE_SOURCE_MAPPED`, `EXPERIMENTAL`,
`IMPLEMENTED_HELPER`, and `UNSUPPORTED`. It has seven active source-mapped
detector IDs across six conceptual families: explicit count-marker discovery,
JATS and Markdown table percentages, direct JATS cell ratios, JATS sample
flow, JATS PRISMA flow, and JATS unadjusted 2×2 odds ratios. The JATS and
Markdown percentage contracts are separate IDs; the two percentage forms and
direct ratio are counted within the broad count/percentage correction family
in development results. Count-marker discovery reports repeated assertions
but does not establish an error.

| Family | Source format and eligibility boundary |
| --- | --- |
| Explicit count/percentage arithmetic | Structured JATS cells with an explicit same-scope header denominator, direct same-cell JATS `n/N (%)`, and guarded legacy Markdown pipe tables. Exact operands and scope are required; ambiguous row or footnote scope, weighting, adjustment, missingness, overlap, and multiple-response cues skip the check. PDF table arithmetic is unsupported. |
| Sample flow | Active source mapper for JATS prose; the graph helper is separate. One paragraph must establish a shared population, unit, group, and study scope, plus disjoint/exhaustive or sequential-removal semantics. Uncertain overlap or scope is `FLOW_RELATION_AMBIGUOUS`. No table-flow mapper is active. |
| PRISMA/synthesis flow | Active source mapper for JATS prose. It checks the explicitly labelled relation `records identified - duplicates removed = records screened` in review context. Other stages, ambiguous scope, and image-only flows are unsupported; no OCR or diagram reading is performed. |
| Crude 2×2 effect | Active JATS source mapper for an unadjusted odds ratio only. One reliable body row must provide four integer cells, outcome polarity, group direction, a common timepoint, and the reported unadjusted OR. Adjusted, weighted, model-derived, zero-cell, multirow, or direction-ambiguous results are skipped. RR and risk-difference source mapping are not implemented. |
| Explicit count-marker discovery | Active on text, Markdown, and extracted PDF prose with local anchors. It reports repeated `n = integer` / `N = integer` assertions or possible scope differences; it does not establish shared identity or contradiction. |

SD/SE/n is experimental for JATS rows under an unweighted summary assumption;
it does not establish the paper's chosen standard-error method. Simple rate
recomputation is unsupported. Cross-section numeric identity remains a helper
without an active source mapper. Outputs remain human-review candidates, and
`paper_error_established` remains false.

## Aggregate development replay

The source-native JATS replay used 33 source documents and 16 correction-backed
issues. The classification was post-hoc and is not a holdout. Public validation
artifacts contain aggregate metrics only: source identifiers, individual
source hashes, candidate arithmetic, and per-document records are omitted.
The replay tool accepts a private eligibility file at runtime and writes only
aggregate output.

| Metric | Result |
| --- | ---: |
| Eligible correction issues | 2/16 (12.5%) |
| Conditional sensitivity among those eligible issues | 2/2 |
| Matched correction target cells | 4/4 |
| Eligible issues by detector | 1 direct JATS cell ratio; 1 structured table percentage |
| Selected controls with candidates | 0/17; controls are not certified error-free |
| Candidate items | 12, without a precision estimate |
| Unmatched candidates requiring adjudication | 8; not individually identified in this packet |
| Reports with some incomplete table or detector coverage | 33/33 |
| JSON and HTML reports byte-repeatable | 33/33 |
| Paper errors established | 0 |

The two eligible correction issues are variants of the broad count/percentage
mechanism. There is no correction-backed positive for flow, PRISMA, 2×2, rates,
or summary statistics under the current contracts. The 2/2 conditional
sensitivity is not a general performance estimate.

### Granular coverage

Across the replay, 123 tables were discovered: 62 had a reliable structured
grid and 61 had unsupported structure. Metrics are reported separately by
detector and table status, so an unrelated unsupported table does not make
every check on that paper look unscannable.

- Direct JATS cell ratio: 2 eligible tables, 8 incomplete, 113 not applicable;
  76 operands checked and 9 candidate cells.
- Structured JATS count/percentage: 1 eligible table, 84 incomplete, 27 not
  applicable, 11 unsupported; 63 cells checked and 3 candidate cells.
- Sample flow: one source object matched a flow shape and was skipped because
  disjointness, exhaustiveness, or sequential subtraction was not explicit.
- PRISMA: 23 potential review-flow objects were unsupported or not applicable;
  none was eligible for arithmetic.
- 2×2: no table was applicable in this corpus. Source mapping is covered by
  synthetic fixtures only.
- SD/SE/n: 7 tables unsupported, 2 incomplete, 114 not applicable, and no row
  was checked.

The regression packet contains 66 synthetic hard-negative scenarios. None
produced a candidate in its asserted negative path. These crafted scenarios are
not papers and do not estimate a real-world false-positive rate.

## Historical candidate validation

The aggregate validation packet covers 15 historical off-target candidates:
14 reproduce as internal arithmetic discrepancies in the locked JATS-derived
representation, and one has a correction pointer whose mapping to a specific
candidate is unconfirmed. All 15 remain externally unresolved. The aggregate
publisher-PDF signature comparison found differences in 8 of 8 paired records,
but cannot confirm any individual table value. Confirmed correction mappings,
supplement-resolved cases, format artifacts, and benign-presentation resolutions
are all zero in the current packet. Later-version resolution and scientific
consequences remain unassessed. These are development observations, not
scientific discoveries or public accusations.

## Engineering qualification

The full offline quality gate passed on Python 3.12.14:

- 482 pytest cases passed.
- Synthetic conformance: 500/500.
- Historical deterministic verifier fixtures: 3/3.
- Trusted-core static scan, schemas, schema drift, source checksums,
  frozen-screen review, capability examples, and compile checks: pass.
- Two reproducible wheel builds produced byte-identical artifacts.
- Clean wheel installation and agent, review, summary, and paper-audit CLI
  smoke tests: pass.
- Runtime dependencies: none.

JATS tests cover external/internal DTD and entity behavior, unknown entities,
malformed XML, depth and size limits, malformed spans, table grids and spans,
footnote scope, oversized numeric operands, and HTML escaping. A specialized
provider-backed Codex Security diff scan did not run because its scan tools
were not callable in this session; repository static checks and regression
tests do not substitute for that report.

## Wave 3 readiness

**Not ready to freeze.** The correction-backed development coverage is 2/16,
and both eligible issues use the count/percentage family. Flow, PRISMA, and 2×2
have synthetic positives but no eligible correction-backed positive. Rates
are unsupported, cross-section consistency is helper-only, and the negative
suite is synthetic. No unseen eligible positive or matched-negative cases have
been independently selected in the current workspace; the count is **0**.
External availability is unknown, and selected controls do not provide an
adjudicated false-positive rate.

The highest-value next step is to curate a source-version-verified correction
for explicit sample flow, select matched hard negatives, and freeze both labels
before changing that detector or evaluating it. A wave-3 protocol should wait
until multiple families have eligible correction positives, independent
adjudication, matched negatives, and CI/CodeQL on the frozen candidate.
