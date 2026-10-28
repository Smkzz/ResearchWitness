# RW-01P: source-mapped PRISMA record-flow review in installed JATS audit

**Scope:** optional offline arithmetic screening; no original-paper truth,
publisher authenticity, independent scientific labels, PDF/diagram extraction
or authorization for protected custody. The installed JATS command is
still a *development* tool; all findings remain `unreviewed` candidates.

## Why it matters

A previously implemented but unmerged [legacy PR #11](https://github.com/Smkzz/ResearchWitness/pull/11)
contained a narrow PRISMA count-mapper. RW-01P selectively ports that mapper
into the **current installed** `audit-jats` product using the **current**
strict original-byte JATS parser and `PaperDocument` projection, not the
legacy parser or a wholesale PR stack merge.

Only the relation

```text
records identified - duplicate records removed = records screened
```

is tested, where all three operands and their stage labels occur in one
standalone JATS `<body><p>` paragraph in a PRISMA/systematic-review context.
For example (entirely invented):

```text
PRISMA systematic review: records identified: 1,200;
duplicates removed: 200; records screened: 999.
```

The tool emits an **unreviewed arithmetic candidate**: expected screened
count = 1,000, printed = 999, difference = −1. It does *not* assert that
the paper made a mistake; extra sources, eligibility stages, later
corrections or unreported diagram context may explain the difference.

The same relation with screened = 1,000 is `PRISMA_FLOW_BALANCED`.
Unsupported or ambiguous cases are reported explicitly as
`UNSUPPORTED` with bounded reasons, never silently accepted as
correct or omitted to improve a success ratio.

## Guardrails and evidence

- Context must explicitly say PRISMA, systematic review, or literature search.
  Three **labeled** stages are required in a recognized single-paragraph
  order; no normal-language inference across multiple paragraphs.
- Counts are bounded integers. Invalid grouping, nonnumeric counts,
  duplicates exceeding identified records, multiple candidate sequences,
  unrecognized order, and certain incompatible scope cues cause abstention.
- Additional databases, adjusted/weighted counts, overlapping stages,
  full-text/report/study-specific stages, unrecognized synthesis stages,
  diagram-only data and opaque table/caption paragraphs are not checked.
  The `records` unit cannot be converted to `reports` or `studies`.
- The `PaperDocument` source anchor covers the **complete original UTF-8
  XML paragraph element**, including markup. A shortened normalized
  numeric quote is a separate text projection and is **not** a token-level
  original-byte offset.
- Review records preserve source SHA-256, exact source element path,
  unchanged byte start/end, role names and candidate-only status. A
  SHA-256 proves consistency with supplied bytes, not original publisher
  authenticity.
- Full source JATS is parsed by the same bounded parser as existing
  percentage checks. No DTD/ENTITY, network requests, HTML execution,
  arbitrary expressions, source-supplied code or privileged worker.
- Bounded mapper results; current `jats_product` builds deterministic
  report/HTML/source/manifest bundles and replays them by recomputing the
  map from source bytes. Unknown and unsupported paragraphs remain visible
  in coverage limitations; this **is not whole-paper screening**.

## Run and independently replay the exact private input

```text
researchwitness audit-jats PRIVATE_ARTICLE.xml \
  --document-id LOCAL_IDENTIFIER \
  --output-dir NEW_PRIVATE_OUTPUT_DIRECTORY \
  --expected-source-sha256 PREVIOUSLY_SAVED_SOURCE_SHA256 \
  --include-prisma-flows

researchwitness replay-jats NEW_PRIVATE_OUTPUT_DIRECTORY \
  --expected-manifest-sha256 RETURNED_MANIFEST_SHA256
```

If both sample-flow and PRISMA review are wanted, also include
`--include-prose-flows`. Both share one bounded original-byte paragraph
projection and are reported in separate sections. The unchanged
percentage detector remains the base result, and its counts are **not
relabelled** as PRISMA performance.

The opt-in report section is `prisma_flow_review`, schema
`rw-jats-prisma-flow.v1`. It includes total and excluded body paragraph
counts, supported/unsupported relation counts, candidate count,
source-mapped cases, explicit `whole_article_coverage_established: false`
and no scientific truth promotion. The HTML renderer escapes all
untrusted text and discloses limitations. The replay command re-derives
the optional section from the pinned source/implementation and fails if
the report, HTML or manifest has changed.

## Historical real-paper evidence is not a new benchmark

See the [separate archival evidence ledger](HISTORICAL_EXPOSED_REAL_PAPER_EVIDENCE.md)
for the earlier exposed 9- and 33-JATS-paper development cohorts,
eligibility denominators, candidate resolution gaps, and strict difference
between old unmerged branches and the installed RW-01P code. The
original fulltext source bytes and new independent source labels were
not obtained or rereplayed in the current session.


An archived **October 6, 2026** unmerged capability-branch development
evaluation processed 33 JATS source documents and 16 correction-backed
issues. The broader branch classified only **2/16** issues as eligible
for its source-mapped mechanisms, with 2/2 eligible detections; 17
selected controls emitted zero candidates, and all 33 documents had
incomplete coverage. That archived branch included a PRISMA mapper,
but **zero correction-backed PRISMA positives were eligible**.
Its outcomes were exposed/post-hoc, not independent accuracy or
quantified new scientific discoveries; the archived baseline is not a
measurement of this merged installed module.

This RW-01P port is supported initially by synthetic direct-JATS
regressions and installed-wheel/CLI replay evidence only. Before claiming
a gain in scientific coverage, the team must obtain approved source
snapshots, genuinely separate source-grounded labels and matched negative
cases, then rerun the current frozen candidate and baseline on the
**same exposed development cohort**. A protected confirmatory study
still requires RW-03/RW-05 isolation and a real pre-outcome freeze.
