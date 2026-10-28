# RW-01R: opt-in exact participant count-total check for JATS

**Status:** an intentionally narrow new category-total arithmetic candidate
generator. It does not certify that a table is scientifically correct,
that a publication's source version is authentic, or that all categories
really are disjoint/exhaustive. It does not contact publishers, run PDF/OCR,
or access protected evaluation.

## Motivating real development evidence

The earlier October 6, 2026 **exposed** correction manifest included
count-only table transcription and demographic category errors that
the percent-only JATS detector could not evaluate. In particular its
`issue-007`, `issue-009` and `issue-011` descriptions concerned
count-only categories or a digit omission. Those corrections are
**not automatically eligible for this new check**, because an explicit
summation relation, trustworthy source version and correct grouping
have not been independently verified for their original JATS tables.

The new mechanism is meaningful for the narrower situation where the
table itself **states** that its categories are *mutually exclusive and
exhaustive*, gives one complete, explicit participant count per category,
and prints a single final total. This is evidence to attempt a sum,
**not proof that the underlying source statement is true**.

## Exact source contract

Opt-in via:

```text
researchwitness audit-jats PRIVATE_SOURCE.xml \
  --document-id PRIVATE_LOCAL_ID \
  --output-dir NEW_PRIVATE_BUNDLE_DIR \
  --expected-source-sha256 PREVIOUSLY_SAVED_SOURCE_SHA256 \
  --include-count-totals

researchwitness replay-jats NEW_PRIVATE_BUNDLE_DIR \
  --expected-manifest-sha256 RETURNED_MANIFEST_SHA256
```

For each table projected with the existing bounded original-byte
JATS parser:

- Exactly **two columns** with explicit `Category` and
  `Number of participants`, `Participants` or
  `Participants (n)` headers.
- A caption containing **`mutually exclusive and exhaustive categories
  of participants`**, with no contradictory missingness,
  overlapping/multiple-response, weighted/adjusted or partial-cohort
  context. Implicit disjointness is insufficient.
- Clean, non-spanning, single-group body rows with 2–64 rows, no
  footnotes, cross-references, complex inherited scope, duplicate
  labels or noninteger/invalid count tokens. At least two category
  rows plus **one unique final `Total`** row.
- Counts are exact nonnegative integers no greater than 999,999,999.
  Only canonical digit or comma-thousands tokens are accepted. A sum
  exceeding the limit abstains, rather than overflowing or inventing a
  category interpretation.
- The result is one of `COUNT_TOTAL_MATCH`,
  `COUNT_TOTAL_MISMATCH_CANDIDATE`, `UNSUPPORTED` or
  `NOT_APPLICABLE`. All tables and unsupported reasons remain in the
  denominator. A mismatch is the exact final total minus the category sum.
- Each operand and the total are anchored to the **full original XML cell
  element**: byte start/end, stable element path and SHA-256. These are
  not numeric-token byte positions. The HTML is escaped, the source bundle
  and candidate report are replayed from bytes on demand, and
  `scientific_error_established` is always false.

An entirely invented table with disjoint/exhaustive participant categories
40 and 60 and a final total 99 yields a source-linked **candidate**:
computed 100, printed 99, difference −1. The same source with total 100
is a match. Footnoted denominators, missingness, overlapping responses,
multicolumn spans and ambiguous row groups abstain rather than generating
an allegation.

This is **not** a general row/column total engine. It intentionally
doesn't infer total population, category overlap, missing-case treatment,
binary responses, study identity, adjusted counts, derived rates, person-time
or statistical significance. No PDF tables, PRISMA diagrams or cross-table
comparisons are attempted.

## Current qualification versus real-paper discovery

Synthetic positive and adversarial-negative checks, installed CLI
`--include-count-totals`, original-byte anchors, deterministic manifest
and complete replay qualify **engineering behavior** only. The feature
does not retroactively increase the old 2/16 exposed eligible-correction
count, and no original correction-article JATS source was obtained for a
new measurement.

[The archived real-paper development record](HISTORICAL_EXPOSED_REAL_PAPER_EVIDENCE.md)
documents why coverage was the dominant known gap. Future RW-01Q work
must obtain original, legally reusable source versions in a genuinely
authorized environment, independently verify whether each count-only
correction falls under the frozen contract, and compare a fixed baseline
and candidate on identical source bytes and full attempted denominator.
Until then, neither improved real-world recall nor a new discovery is
established. [RW-01Q](https://github.com/Smkzz/ResearchWitness/issues/50)
and [the new PMC pilot](https://github.com/Smkzz/ResearchWitness/issues/35)
remain open.
