# Opt-in unadjusted 2×2 JATS review — RW-01F

**Scope:** source-linked developer arithmetic candidates only. This is not
a research benchmark, a new trusted proof-checker family, independent
publisher authenticity or evidence that a paper is scientifically wrong.

## Interface

A standard installed `researchwitness` wheel provides:

```text
python -m researchwitness audit-jats examples/synthetic-jats/odds-ratio.xml --document-id synthetic-or --output-dir work/synthetic-or --include-unadjusted-2x2
python -m researchwitness replay-jats work/synthetic-or --expected-manifest-sha256 EXPECTED_HASH
```

The default `audit-jats` remains percentage-only and byte/replay compatible
with its existing contract. `--include-unadjusted-2x2` adds
`odds_ratio_review` to the private JSON and escaped HTML report. It can
coexist with `--include-structure`. The same source XML, source hashes,
implementation hashes and manifest are preserved; replay recomputes all
opt-in sections rather than trusting a supplied detector result.

## Exact acceptance conditions

- Source is bounded UTF-8 JATS, parsed by the *current* original-byte parser.
  The legacy XML-normalizing parser is not installed or invoked.
- The table caption must explicitly describe independent, unmatched or mutually
  exclusive groups. Mere "unadjusted OR" wording does not qualify a marginal
  estimand. Matched, paired, conditional, stratified, crossover or otherwise
  complex contexts in the table/header/wrapper metadata suppress candidates.
  Adjacent narrative outside the table is not yet projected; independent study
  interpretation remains mandatory even when this syntactic gate passes.
- A single structurally mapped body row has precisely one outcome column,
  four distinct nonnegative integer count columns and one reported *unadjusted
  odds ratio, exposed versus unexposed* column. Four header roles must be
  explicit and unique, along with the direction of the estimate.
- The source must explicitly identify a timepoint and outcome. No numerical
  cell may span rows/columns. The old unadjusted, weighted, transformed,
  modeled or uncertain context is never silently assumed.
- Extra body rows, header ambiguity, duplicate table identities, unresolved
  footnotes, scope cues and missing or zero-cell conventions refuse or
  yield incomplete coverage instead of an unqualified mismatch.
- The arithmetic engine is the existing exact operand-only
  `recompute_two_by_two`, comparing at the printed decimal precision.
  Failure to reproduce is an **unreviewed arithmetic candidate**, not an
  established false published conclusion or causal effect.
- The JSON contains five original XML element anchors for the four counts
  and reported statistic, plus a separate outcome/timepoint row anchor.
  The anchors' byte ranges cover original XML markup; their normalized quotes
  are separate, not purported literal-byte substring offsets.
- The capped candidate count and incomplete scans remain visible.
  A cap or parser refusal never masquerades as a clean study.

## Evidence and limits

The invented fixture has 12 exposed events / 88 non-events and 6 unexposed
events / 94 non-events. Its crude OR is 47/22, which rounds to 2.14
under the stated half-up display rule; the fixture deliberately prints 2.20.
This establishes only deterministic engineering behavior on made-up data.

Even when every structural gate passes, the extracted source might report
adjusted or weighted values without indicating them, use a different analysis
population or contain revisions and errata. A source hash authenticates bytes,
not their publisher or the scientific applicability of a statistic. No
automatic author contact, PDF extraction, protected data, licensed corpus,
paid model call, scientific Wave 3, sealed holdout, or statistical superiority
claim is activated by this interface.

See [the table projection](JATS_TABLE_PROJECTION.md),
[the execution state](EXECUTION_STATE.json) and the PR's exact commit checks.
