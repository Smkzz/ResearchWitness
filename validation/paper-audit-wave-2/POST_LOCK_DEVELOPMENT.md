# Wave 2 post-lock development

The primary wave-2 reports remain the frozen outputs produced by the detector
at baseline commit `3042b3d62b8f20cc646b0c121dff376bfdd201cb`. Their
`results/LOCK.json` and hash are unchanged. No changed detector was run against
the wave-2 primary corpus, and the locked outputs were not rescored. Work
described here began only after the lock and adjudication evidence was
committed.

## Changes made after lock

The wave-2 failure analysis found denominator shifts in rendered tables with
missing stub cells, grouped headers, and row-specific denominator cues. The
Markdown table screen now:

- Requires each row in a pipe table to have the same number of cells. If a
  later row changes width, it removes candidates already produced from that
  table, skips the rest of it, and marks the report scan incomplete.
- Omits a row whose label contains a local `n = ...` denominator or a
  footnoted `n (%)` marker.
- Omits denominator cells and count/percentage cells with attached footnote
  markers when their scope cannot be resolved safely.
- Adds each skipped-coverage reason to `unsupported_checks` and the HTML report.
- Labels displayed items as candidate anomalies and says that the screen has
  not determined whether they affect the paper's conclusions.

The screen still handles only Markdown pipe tables. It does not reconstruct
merged headers, infer PDF table geometry, validate row or column totals, or
resolve footnotes. Skipped tables produce an incomplete-scan status rather
than a clean result.

Regression tests cover a candidate removed after discovering a ragged row,
missing stub cells, row-local denominators, footnoted headers and values,
rounding and byte anchors, an image-only PDF with explicit no-OCR behavior,
and a generated two-column PDF with a Unicode header, footer, and page anchors.
The PDF fixtures are generated tests; they do not estimate extraction quality
on arbitrary publisher PDFs.

## Development-set replay

The source-pinned wave-1 development runner was rerun twice per paper using the
exact source hashes in `validation/paper-audit-wave-1/cases.json`. Reports were
written outside the repository under `/tmp/rw-wave2-development-after-changes`.
All nine papers had `TEXT_AVAILABLE` extraction and byte-identical JSON and
HTML across repeats.

| Exploratory metric on selected wave-1 cases | Result |
|---|---:|
| Correction-backed mechanisms rediscovered | 3/4 |
| Correction-backed issue unsupported by these screens | 1/4 |
| Candidate items matching listed correction targets | 4/4 |
| Selected negative-control papers with candidates | 0/5 |
| Scope/denominator notes | 5 (not systematically adjudicated) |
| Reports with incomplete table coverage | 7/9 |
| Candidates promoted to verified paper errors | 0 |

These cases and labels were known during development, are few and clinically
selected, and are not a blinded benchmark. The 4/4 item match is not an
estimate of general precision. The three positive papers retain their
correction-matching candidates, but their reports now say coverage is
incomplete because at least one other table could not be aligned. Four
negative controls also report incomplete table coverage. The fifth negative
control and unsupported positive did not have such a table-shape limitation.
Scope-note volume fell from 17 to 5 because suspect table rows were skipped;
note precision remains unscored.

## PDF evidence boundary

After locking the unchanged detector, five legally accessible same-record
publisher PDFs were compared with their JATS-derived Markdown sources; one
source PDF could not be retrieved. The paired check found matching extraction
status and warning counts for 5/5 pairs, but extracted text hashes and count
anchor signatures differed for 5/5. Candidate signatures differed across all
five pairs (27 JATS-only, 5 PDF-only, and 1 shared candidate signature in
aggregate). This is not a parser-only comparison because table arithmetic is
Markdown-only and PDF table geometry is unsupported. These figures are
excluded from the primary locked metrics and were not rerun with post-lock
code.

The current PDF tests cover born-digital page mapping, partial and empty text,
missing parser, timeout, malformed and encrypted inputs, configured limits,
Unicode text, and positioned two-column text. No real image-only, OCR, scanned
table, or supplement corpus has been validated. PDF extraction remains a
limited text-extraction aid, not a general paper-format parser.

The offline repository qualification gate passed after these code changes on
Python 3.12.14: 363 tests; 500/500 synthetic conformance cases; 3/3 historical
verifier cases; generated schemas, source checksums, compile and static checks;
and clean wheel install and CLI smoke checks. Two wheel builds were byte
identical (SHA-256 `3a6c74162f39f2b1ff1ffba3639344431fef893c1bd9902eaf994fa21bc0d494`).
No remote CI result is claimed for this branch unless one is reported after
push.

## Next experiment

Before a public preview, run a separately preregistered development wave that
contains detector-eligible positive corrections with explicit targets and
matched difficult negatives. Include paired same-version JATS and publisher
PDF sources, source-layout classes such as grouped headers and row-specific
denominators, and adjudicated omission reasons. Keep the detector fixed for
the first run, lock outputs before adjudication, and report candidate and
coverage metrics with denominators. Development failures can then inform the
next code iteration without consuming that evaluation set.

ResearchWitness remains a numeric screening and evidence-linking tool. These
results do not establish paper errors, misconduct, author intent, or arbitrary
paper correctness.
