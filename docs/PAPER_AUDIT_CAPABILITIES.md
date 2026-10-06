# Paper audit capability boundaries

ResearchWitness paper checks are bounded arithmetic and source-consistency
screens. A candidate means that explicit source operands did not reconcile
under the detector's declared rule. It does not establish that a paper is
wrong, identify which source value is wrong, assess scientific importance, or
validate the study's methods or conclusions.

## Source-mapped checks

| Detector family | Active input and rule | Important exclusions |
| --- | --- | --- |
| Counts and percentages | JATS tables with explicit numerator/denominator/percentage in one cell, or an explicit numerator with a same-scope header denominator; exact integer/decimal arithmetic and printed precision. | PDF table geometry, weighted or adjusted percentages, changing denominators, multiple responses, ambiguous row scope, and unresolved footnote effects. |
| Sample flow | One source-anchored JATS paragraph with explicit starting, exclusion, and included counts; arithmetic runs only when disjoint/exhaustive or sequential-removal language is explicit. | Cross-paragraph joins, table flow mapping, image extraction, overlap, arm ambiguity, and unresolved attrition or analysis-set scope. |
| Synthesis flow | One source-anchored JATS paragraph in systematic-review context stating records identified, duplicates removed, and records screened; checks identified minus duplicates against screened. | Multi-database totals, later full-text/study stages, qualitative/quantitative subsets, inferred transitions, PRISMA images, and OCR. |
| Crude 2×2 odds ratio | One reliable JATS body row with four explicit integer cells, event polarity, exposed-versus-unexposed orientation, one explicit timepoint, and an unadjusted OR in that row. Exact cross-product arithmetic is rounded to the printed precision. | Adjusted/model/weighted estimates, reversed or missing reference direction, multiple rows/timepoints, confidence intervals in place of an explicit value, and zero-cell corrections. |
| Explicit count-marker discovery | Text extraction locates repeated explicit `n = integer` or `N = integer` assertions with local byte/page/section anchors. | It does not decide whether assertions share a population, denominator, timepoint, or meaning. It is candidate discovery, not a consistency proof. |

## Experimental and helper-only checks

- The JATS `n`/SD/SE screen is experimental. It checks one same-row simple-summary identity, `SE = SD / sqrt(n)`, but cannot establish that this is the paper's chosen SE method.
- Simple rate recomputation is unsupported. In particular, adjusted or annualized rates with unavailable person-time construction or model operands are not recomputed.
- Cross-section numeric identity and general flow/2×2 arithmetic remain helpers. They do not compare source-mapped claims across sections or infer a study's statistical model.
- Confidence-interval reconstruction, row/column totals, subgroup summation, and generic statistical validation are not active detectors.

## Format and coverage reporting

JATS XML is the only input format for the table, sample-flow, synthesis-flow,
2×2, and summary-statistic source mappers. PDF support is limited to bounded
text extraction and prose count discovery; table arithmetic is unsupported
for PDF. Figure captions can be inspected as text, but image contents are not
read and no OCR is run.

Each paper report includes paper, detector, operand, and table-level coverage.
It records applicability, eligibility, checked and skipped objects, parser
status, bounded reason codes, and whether a result cap made a screen
incomplete. Unsupported unrelated tables do not by themselves make an
otherwise eligible table appear unchecked. A report with skipped or
unsupported content remains explicitly incomplete.

The report's `paper_error_established` value remains false. Human review must
check the original source version, table semantics, supplements, corrections,
and scope before drawing a paper-level conclusion.
