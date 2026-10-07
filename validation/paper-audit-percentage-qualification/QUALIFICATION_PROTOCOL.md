# Count/percentage qualification protocol

Status: frozen before the expanded matched-negative corpus is scored.

This protocol governs only the explicit count/percentage arithmetic family.
It does not qualify any other ResearchWitness detector family.

## Contract semantics

The active relationship types are `CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE`
and `DIRECT_N_OVER_N_PERCENTAGE`. Each is checked independently at the cell
or row relation whose numerator, denominator, percentage, precision, and
scope are explicit, including numerator and denominator units, population,
group, timepoint, analysis set, and percentage base. Whether other categories
overlap does not change that local arithmetic relation when those facts are
clear. Category totals, mutually exclusive partitions, and percentage sums
are distinct relationship types and are not inferred or checked by these
contracts. A source cue is an exclusion only when it makes the operands,
denominator, weighting, adjustment, or population scope of the individual
relation ambiguous. This semantic rule applies generally and is not
conditional on benchmark results.

If implemented, this clarification is contract version 1.2. Contract 1.1
artifacts and replay outputs remain immutable and are reported separately.
Any v1.2 development replay is post-hoc development evidence, not unseen
evaluation.

## Frozen graduation criteria

`READY_TO_FREEZE_FOR_WAVE_3` requires every mandatory criterion below. A
missed threshold remains a miss; thresholds and labels will not be changed
after expanded-negative scores are revealed.

1. At least one unquestionably eligible development correction positive
   under the finalized contract. It must map an exact explicit relation in an
   available, pinned, uncorrected source version to a pinned correction.
   Two distinct eligible correction issues is the preferred target when the
   source semantics support them, but one is the minimum.
2. At least 50 independently source-qualified, arithmetically correct,
   contract-eligible development relationships from at least 15 distinct
   documents. Tables and documents represented are also reported.
3. Every unquestionably eligible correction issue and target cell is
   detected. At least 90% of adjudicated development candidates are
   independently confirmed as printed arithmetic discrepancies; targets and
   source-reproduced non-target discrepancies both qualify for this metric.
4. No more than 5% of checked matched-negative relations have a false
   candidate, and no more than 10% of negative-bearing document clusters
   contain a false candidate. The one-sided 95% exact upper bound for the
   document-cluster event rate must be at most 20%. These are development
   gates, not population guarantees.
5. All 12 existing development candidates are adjudicated, with no unresolved
   cases and no unexplained parser/source artifacts.
6. Every potential percentage relation has one deterministic identity and
   exactly one terminal status. The status totals partition the potential
   relations. Every `INCOMPLETE` or `UNSUPPORTED` relation has exactly one
   canonical primary skip reason; secondary reasons do not count toward the
   partition. The sum of primary skip-reason counts equals
   `INCOMPLETE + UNSUPPORTED` relations.
7. The same pinned inputs and software revision produce identical canonical
   replay output, including findings and relation telemetry.
8. The complete local qualification passes, GitHub CI passes, and CodeQL
   passes.
9. At least one eligible reserved correction positive is independently
   confirmed by a custodian and remains unopened to the runner. If that
   isolation is unavailable, the reserved case stays unopened and this
   criterion fails.
10. A source-first reserved negative pool remains available with at least 50
   correct eligible relationships across at least 15 documents. No reserved
   detector result may be joined or inspected in this wave.

The preferred negative target is 100 or more eligible relationships across
20 or more documents. Missing this preferred target does not change the
mandatory 50/15 threshold.

## Relationship accounting

The terminal statuses are `NOT_APPLICABLE`, `ELIGIBLE_CHECKED_MATCH`,
`ELIGIBLE_CHECKED_MISMATCH`, `INCOMPLETE`, and `UNSUPPORTED`.
`checked` means either eligible checked status. `skipped` means
`INCOMPLETE + UNSUPPORTED`; `NOT_APPLICABLE` is reported separately.

For each reported count, use the relation as the arithmetic unit and also
report represented table and document counts. A relation identifier is a
deterministic digest of detector ID, contract version, source hash, exact
source cell element path, and relation slot. Table labels, IDs, and row labels
are not identity inputs. The canonical primary reason is selected by the
frozen reason-precedence order in the implementation; all additional
applicable reasons are secondary. No one relation contributes to more than
one primary-reason bucket.

For relation-based false-candidate metrics, a false candidate is one unique
emitted mismatch relation on an independently labeled correct negative;
duplicate alerts for that same source relation count once in the relation
rate and are separately reported as raw alerts. A document event is one
canonical source document with at least one such relation.

## Source-first labels and split

Negative truth labels are determined and frozen from pinned source evidence
before any detector output is joined. A negative is contract-eligible and
independently arithmetically correct. Detector silence is never used to
establish a label.

For newly added source documents, normalize the DOI by trimming whitespace,
removing a leading `https://doi.org/` or `doi:` prefix, and lowercasing. Set
`h = SHA256(normalized_doi UTF-8)`. Before table review, assign the whole
document to `RESERVED` when the first digest byte is less than 64; otherwise
assign it to `DEVELOPMENT`. Documents without a stable DOI are not added to
either scored pool. Existing reserved assignments remain unchanged. Reserved
labels, source relations, and detector outputs are not opened to the runner
or joined in this wave.

New correction candidates discovered after the current allocation is closed
are split before correction-body inspection using
`SHA256(lowercase(trim(original_doi)) + NUL + lowercase(trim(correction_doi)))`;
first digest byte `< 64` is `RESERVED`, otherwise `DEVELOPMENT`. Existing
allocations do not move. No reserve body is inspected during this wave.

## Frozen development metrics

Report each metric independently; do not collapse them into a generic
accuracy value.

| Metric | Definition |
| --- | --- |
| Candidate arithmetic validity | Source-reproduced arithmetic discrepancies / adjudicated candidates |
| Known-correction target share | Known correction target candidates / adjudicated candidates |
| Matched-negative relation false-candidate rate | False candidate relations / independently qualified correct eligible relations |
| Paper-level false-candidate occurrence | Documents with at least one false candidate / documents with eligible negative relationships |
| Eligibility yield | Contract-eligible relationships / all independently reviewed potential relationships |
| Source coverage | Eligible relationships checked / all independently considered source relationships |

Always give numerator, denominator, relation count, table count, and document
count where applicable. Because relations cluster within tables and papers,
relation-level proportions are descriptive and clustered; do not present a
naive relation-independent binomial interval as paper-level uncertainty.

## Evidence boundaries

Only development correction sources and development negative detector scores
may be opened and joined after labels are frozen. The reserved correction
body, operands, target cells, and detector output remain unseen. No Wave 3,
merge, release, or publication is authorized by meeting these criteria.
