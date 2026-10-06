# Roadmap

ResearchWitness is growing narrow, reproducible checks before expanding marketing or automation.

## Current local branch — 0.4.0.dev0 integration candidate (unreleased)

- Agent-prepared structured intake and a ten-area human-review ledger.
- Ten bounded deterministic verifier families for explicitly formalized claims.
- `paper-audit` screens explicit `n`/`N` contexts, selected Markdown table percentages, and one explicit exclusion-flow sentence. Reports include source anchors, context, rounding tolerance, possible stage/denominator notes, and unsupported checks.
- Optional PDF text extraction in a separate resource-limited worker. The worker is not a sandbox and performs no OCR.
- A source-pinned development set of four correction-backed positives and five selected negative controls. Current development results are 3/4 positive issues rediscovered, 4/4 surfaced items matching correction-backed arithmetic, and 0/5 negative-control papers with candidates. These cases were visible during detector iteration.
- No sealed holdout, independent evaluation custodian, or cross-disciplinary performance estimate. The candidate is not release-qualified.

## Next empirical gate

Keep the current detector implementation fixed while an independent custodian builds and evaluates a sealed set. Include more disciplines, publishers, table formats, and extraction paths; preserve negative controls with known denominator, stage, subgroup, repeated-measure, and missing-data differences. Publish the split protocol and exact source/version hashes before running it. Do not expose correction labels to the detection process.

After an invalidating bug, document the failed run and create a new evaluation wave instead of silently replacing its results. Report positive rediscovery, candidate-item precision, false positives per paper, scope notes, unsupported cases, extraction failures, and repeatability separately.

## Further detector work

Use source-grounded development cases to decide whether to add:

1. Markdown table row and column totals, with explicit aggregation rules;
2. repeated numeric-claim comparison across prose, tables, and abstracts, with section/population alignment;
3. confidence-interval, standard-error, or test-statistic checks only where inputs and test assumptions are fully stated;
4. better table extraction for publisher PDFs, with extraction quality measured independently.

Every new detector needs exact source anchors, explicit uncertainty and denominator handling, positive and negative controls, boundary tests, and a reproducible evidence artifact. Keep candidates separate from verified arithmetic or formalization results. Statistical or interpretive checks must return insufficient evidence when assumptions are absent.

## Release boundary

Do not describe ResearchWitness as a general paper fact-checker. Do not infer fraud or misconduct, score researchers, publish accusations, or contact authors. No result from `paper-audit` authorizes external action. The existing frozen 15-corrigendum verifier screen remains a separate mechanism-coverage artifact, not a discovery benchmark.

Consider a public research preview only after the exact public commit passes the engineering gate and an independent holdout demonstrates useful discovery without an unacceptable false-positive rate. No release or publication is part of this development wave.
