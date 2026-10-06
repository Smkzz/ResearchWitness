# Roadmap

ResearchWitness is growing narrow, reproducible checks before expanding marketing or automation.

## Current development — paper-audit capability wave (unreleased)

- Agent-prepared structured intake and a ten-area human-review ledger.
- Ten bounded deterministic verifier families for explicitly formalized claims.
- `paper-audit` has a canonical source-aware `PaperDocument` model and directly parses JATS table grids, preserving header hierarchy, spans, footnotes, xrefs, captions, and source anchors. A guarded Markdown adapter remains available. PDF prose extraction is separate; PDF table arithmetic is unsupported.
- Each reported detector has a machine-readable eligibility contract. Source-mapped JATS checks include explicit count-marker discovery, count/percentage recomputation, a narrow single-paragraph sample-flow relation, labelled synthesis/PRISMA arithmetic, a strict unadjusted same-row 2×2 odds ratio, and an experimental same-row SD/SE/n identity. Markdown supports guarded table checks. Cross-section numeric identity remains helper-only; PDF table arithmetic and OCR are unsupported.
- Optional PDF text extraction in a separate resource-limited worker. The worker is not a sandbox and performs no OCR.
- A post-hoc source-native development replay of 33 papers (16 correction-backed issues, 17 selected controls): contract v1.1 eligibility is 2/16 issues; both eligible issues were detected, matching 4/4 target cells. The replay runner reports 8 unmatched candidates; separate source review confirms two internal discrepancies and leaves six unresolved. All 33 reports have some incomplete table or detector coverage. Selected controls had 0/17 candidate-bearing papers, but none is a qualified matched hard negative, so this is not a false-positive rate.
- A separate legacy JATS-to-Markdown replay found three target-mapped items across two correction issues and missed one flow correction; it is a representation comparison and is not combined with direct JATS results.
- No sealed holdout, independent evaluation custodian, or cross-disciplinary performance estimate. No detector family is ready for a Wave 3 freeze or public release. See the [real-evidence qualification](../validation/paper-audit-real-evidence-wave/QUALIFICATION.md) and the earlier [capability-wave qualification](../validation/paper-audit-capability-wave/QUALIFICATION.md).

## Next implementation and qualification gate

Continue by improving source-mapped eligibility coverage and developing matched hard negatives for the JATS percentage contract. Classify every correction against frozen detector contracts before evaluating detections. Report coverage separately from performance among eligible positives. The 15 wave-2 off-target items remain an independent development adjudication track and cannot be counted as unseen findings.

Only after source-to-result mapping for a detector is stable should an independent custodian build a sealed set for it. Include matched negatives with known denominator, stage, subgroup, repeated-measure, weighting, rounding, and missing-data traps. Publish the split protocol and exact source/version hashes before execution. Do not expose correction labels to the detection process.

After an invalidating bug, document the failed run and create a new evaluation wave instead of silently replacing its results. Report overall correction coverage separately from eligible-positive sensitivity, plus candidate precision, false candidates per paper, unresolved candidates, unsupported cases, incomplete table coverage, extraction failures, source-format strata, and repeatability.

## Further detector work

Use source-grounded development cases to decide whether to add:

1. Markdown table row and column totals, with explicit aggregation rules;
2. broader extraction and matched-control coverage for bounded sample-flow and synthesis/PRISMA contracts;
3. broader eligible-source coverage for the strict 2×2 contract, preserving explicit reference-group, timepoint, and adjustment semantics;
4. cross-section numeric assertion extraction with full population/outcome/timepoint identities;
5. confidence-interval, standard-error, or test-statistic checks only where inputs and test assumptions are fully stated;
6. better table extraction for publisher PDFs only if reconstruction quality qualifies independently.

Every new detector needs exact source anchors, explicit uncertainty and denominator handling, positive and negative controls, boundary tests, and a reproducible evidence artifact. Keep candidates separate from verified arithmetic or formalization results. Statistical or interpretive checks must return insufficient evidence when assumptions are absent.

## Release boundary

Do not describe ResearchWitness as a general paper fact-checker. Do not infer fraud or misconduct, score researchers, publish accusations, or contact authors. No result from `paper-audit` authorizes external action. The existing frozen 15-corrigendum verifier screen remains a separate mechanism-coverage artifact, not a discovery benchmark.

Consider a public research preview only after the exact public commit passes the engineering gate and an independent holdout demonstrates useful discovery without an unacceptable false-positive rate. No release or publication is part of this development wave.
