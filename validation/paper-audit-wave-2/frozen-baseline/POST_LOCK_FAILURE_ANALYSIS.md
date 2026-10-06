# Wave 2 frozen-run scoring and failure analysis

This is a post-lock analysis of the unchanged detector frozen at baseline
commit `3042b3d62b8f20cc646b0c121dff376bfdd201cb`. The 24-paper, two-pass
run is byte-locked at commit `4659ddd2335595ab77f96949469318f8c50f021b`;
`LOCK.json` SHA-256 is
`78752f228a87a324b1d1f9f3ce234ee2d86b7c2f4b6cec04906dbb0c38dc5788`.
The lock lists 145 raw records. No detector behavior changed before that
commit.

`SCORING_SUMMARY.json` contains the scorer's aggregate output.
`EVIDENCE_HASHES.json` records the exact source, lock, scoring, custody, and
adjudication input hashes. Full ground truth and per-item adjudication remain
outside the repository; this report does not reproduce paper text or make
claims about authors.

## Corpus and separation

The corpus contains 12 correction-backed positive papers and 12 difficult
negative controls. The source-only manifest contained no correction labels or
targets, and the blind runner accepted only that manifest. It staged each
source separately, ran the frozen CLI twice, and committed JSON, HTML, run
metadata, and hashes before adjudication opened the truth file. All 24 source
hashes matched the committed manifest.

The corpus covered these source-reported domains:

| Domain | Papers |
|---|---:|
| Clinical medicine | 7 |
| Health services and digital health | 5 |
| Clinical research methods and evidence synthesis | 4 |
| Sports and exercise science | 3 |
| Public health and epidemiology | 2 |
| Animal and agricultural science | 1 |
| Medical education and student wellbeing | 1 |
| Scholarly communication and peer review | 1 |

The result is **blinded within the workflow**, not independently sealed.
Before the primary run, a separate format worker ran the frozen CLI once on
six JATS-rendered sources. Those exploratory reports were kept outside the
repository and excluded from primary metrics, but the six papers therefore
had prior output exposure within the team. The custodian held informal
correction facts and tentative screen-fit notes before the run, but no
structured supportability labels, target mappings, ground-truth file, or hash
existed then. The final supportability labels and empty targets were first
serialized after lock. They were not changed based on output, but they were
not preregistered. Positive eligibility and sensitivity results are therefore
exploratory.

## Primary metrics

All fractions include raw numerators and denominators. Wilson intervals are
95% intervals. They describe this selected corpus only.

| Metric | Result |
|---|---:|
| Positive known-issue rediscovery, all positive issues | 0/12; 95% Wilson CI 0–24.2% |
| Positive rediscovery among detector-eligible issues | 0/0; undefined |
| Positives labeled unsupported by frozen screens | 12/12 (100%); labels serialized after lock |
| Exact known-issue candidate matches | 0/88 |
| Candidate precision under the strict target rule | 0/88; 95% Wilson CI 0–4.18% |
| Candidate items adjudicated as false | 61/88 |
| Legitimate nonbenchmark arithmetic or count discrepancies | 15/88 |
| Unresolved candidate items | 12/88 |
| Negative papers with one or more candidates | 5/12; 95% Wilson CI 19.3–68.0% |
| Confirmed false candidate items across all papers | 61/24 = 2.54 per paper |
| Confirmed false candidate items on negative controls | 20/12 = 1.67 per negative paper |
| Scope notes | 42 across 13/24 papers; 1.75 per paper |
| Scope-note adjudication | 24 useful, 18 benign, 0 misleading, 0 false |
| Primary-run extraction failure / degraded extraction | 0/24 / 0/24 |
| Primary-run extraction warnings | 0; all 24 reported `TEXT_AVAILABLE` |
| JSON reports byte-identical across repeats | 24/24 |
| HTML reports byte-identical across repeats | 24/24 |
| Candidates promoted to verified paper errors | 0/88 |

Candidate precision uses all surfaced items, including unresolved items, as
the denominator; it is a conservative exact-target fraction, not a general
estimate of paper-error detection precision. Candidate items are clustered
within papers, so the item-level Wilson interval may be too narrow. The 0/12
all-positive fraction is descriptive only: there were no issues designated
eligible before lock, so this run gives no interpretable sensitivity estimate.

The 12 corrected issues comprised six percentage/rate corrections, four
participant, demographic, follow-up, or sample-flow corrections, one
synthesis-count/percentage correction, and one miscoding followed by
statistical reanalysis. None had an exact target under the frozen screen
definitions. One candidate touched the same broad table area as a corrected
issue, but its required denominator came from a footnote and was not the value
used by the candidate; it was not counted as a rediscovery.

## Failure classes

The frozen run produced 80 table-percentage candidates and eight
conflicting-count candidates. The table candidates comprised 54 false
candidates, 14 source-visible but nonbenchmark discrepancies, and 12
unresolved items. The count candidates comprised seven false candidates and
one legitimate nonbenchmark discrepancy.

The main false-candidate mechanisms were:

1. **Column alignment lost in multirow or ragged table headers.** In one
   four-column outcome table, the rendered denominator row omitted the stub
   columns that appeared in data rows. The detector mapped values to adjacent
   group or per-protocol denominators. This accounted for 14 false candidates.
   In another table, a total column had no explicit denominator, so the next
   subgroup's denominator was applied to it, producing 28 false candidates.
   One additional group table showed the same missing-stub alignment pattern.
2. **A row-specific denominator was ignored.** Ten false table candidates
   applied a global column denominator to rows whose stub explicitly limited
   the row to a subset. The screen should not treat a header denominator as
   applicable when a row supplies its own `n`.
3. **Footnote-scoped population.** One table candidate used a group header
   denominator despite a footnote marker on the row; the capture did not
   establish that the header denominator applied to that row.
4. **Different count populations compared as one quantity.** Seven
   conflicting-count candidates compared planned with analyzed participants,
   subgroup with full-cohort counts, review-level counts, or outcome-specific
   populations. A repeated `n` or `N` marker alone does not establish the same
   underlying quantity.

The 15 legitimate nonbenchmark discrepancies were arithmetic or count
differences visible in the captured source, but did not map to a curated
correction target. They must remain candidates for review, not be presented
as confirmed paper errors. Twelve other candidates remain unresolved because
row denominators, rounding conventions, or scope could not be established.

Among the 42 scope notes, reviewers judged 24 useful and 18 benign. None was
classified misleading or false. Scope notes still require reader review and
do not count as issue rediscoveries.

## Source format and PDF limits

The primary corpus used 24 Europe PMC JATS snapshots rendered to Markdown.
The separate, post-lock source-format follow-up verified five licensed PDFs
against the same PMC records; one additional PDF could not be retrieved or
version-verified. All 65 pages in the five PDFs yielded text and all five
reports had zero extraction warnings. The PDFs contained embedded font
resources, non-ASCII text, and images. The PDF extraction path did not
reconstruct tables as structured Markdown.

Across the five same-record pairs, extraction status and warning lists
matched in 5/5, but extracted-text hashes and count-assertion anchor hashes
differed in 5/5. Candidate signatures differed in 5/5: 27 candidates were
JATS-only, five were PDF-only, and one matched across the corpus; that shared
candidate had different anchors. The table-percentage screen only runs on
Markdown pipe tables, so these candidate differences combine parser output
and format-specific screen coverage. They are not a parser-only comparison.
See `SOURCE_FORMAT_SUMMARY.json` for pair-level hashes and counts.

The existing seven PDF tests passed on the frozen code before development
changes. They covered generated born-digital page mapping, partial extraction,
missing parser, timeout, malformed and encrypted files, and size limits. This
does not establish robust extraction for arbitrary publisher PDFs. Image-only
scans receive no OCR, and the source-format sample did not validate
supplementary PDFs or every requested layout feature.

## Decisions for development wave 2

The next detector change is to fail closed on table layouts where row widths
do not preserve the same column mapping, and to skip cells with explicit
row-local denominator or footnote-scope cues. The report will say when these
conditions prevented a table check. Regression fixtures will cover the
observed structural mechanisms plus difficult denominator controls. Changes
will be validated against the wave-1 development cases and synthetic
adversarial inputs. The locked wave-2 corpus will not be rerun as an
unseen-performance estimate.

No statistical-consistency checker is added in this wave. The corrected
statistical reanalysis did not provide enough unambiguous, frozen inputs to
validate a narrowly specified statistic. The next positive corpus should
include preregistered, detector-eligible examples with explicit operands and
assumptions before a new checker is built.

**A public research preview is not justified by this evidence.** The wave has
no predesignated eligible positive issues, zero exact known-issue matches, a
5/12 negative-paper candidate rate, and large PDF/JATS candidate differences.
