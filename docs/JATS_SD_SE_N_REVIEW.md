# Source-mapped SD/SE/n JATS review — RW-01H

**Scope:** offline, installed engineering review of a very narrow explicitly
declared statistical relationship. NOT independent empirical correctness,
paper-level validation, a new trusted verifier family, or a scientific
accuracy benchmark.

## Use

```text
python -m researchwitness audit-jats examples/synthetic-jats/se-statistics.xml --document-id invented-se --output-dir work/synthetic-se --include-sd-se-n
python -m researchwitness replay-jats work/synthetic-se --expected-manifest-sha256 EXPECTED_MANIFEST_DIGEST
```

The default installed JATS report remains percentage-only. This opt-in adds
`statistical_se_review` in private JSON and escaped offline HTML. It can
coexist with `--include-structure`, `--include-unadjusted-2x2` and
`--include-prose-flows`, with each part recomputed from the original XML
and implementation source on `replay-jats`.

## Precisely supported assumptions

- One source JATS table with structurally mapped, non-overlapping header/data
  cells. The parser and table model use exact original XML element byte spans,
  normalized text separately, original source SHA-256 and element path.
- The caption **explicitly states** the formula `SE = SD/sqrt(n)` and
  independent observations, and the table header has exactly one clear
  n, SD and SE role for the same row and header group. Header `SEM` is
  not silently treated as `SE`. A row label and valid source anchors are
  mandatory. Counts and decimal inputs have fixed integer/precision limits.
- Weighted, model-adjusted, conditional, paired/matched, clustered,
  stratified, repeated, transformed, panel-specific, missingness-affected,
  negated/dependent, mixed-unit/header-scope or unproven formulas are refused. Footnotes or unsupported source
  denominator/role cues cannot silently supply assumptions. The current
  source mapping must have no structural ambiguities.
- A 60-digit Decimal point estimate is reproducible and independent from
  ambient precision, rounding and traps. Importantly, printed SD is *also*
  rounded: before raising a candidate, the checker tests exact rational
  half-up display intervals for **both** SD and SE. If ANY compatible pair
  can satisfy SE = SD/sqrt(n), it returns ROUNDING_COMPATIBLE (or
  CONSISTENT_WITH_ROUNDING for a matching point estimate), not a false
  discrepancy. Only disjoint mathematical intervals can produce a candidate.
  This is an engineering convention; source-specific alternative rounding
  conventions still require independent review. No CI, sampling-design
  correction or model estimate is inferred.
- All attempted applicable row interpretations are either checked, skipped
  with reason or marked incomplete. Limits fail closed. Candidate cap is
  not presented as complete coverage; the report does not claim independent
  science.

## Synthetic acceptance, limitations and authority

An invented article lists n=4, SD=6.0 and printed SE=2.9, while its declared
rule yields SE near 3.0; the **full SD and SE display intervals** are
incompatible, so it remains a synthetic arithmetic candidate. This is only a reproducible test candidate from developer-
exposed data. A formally valid arithmetic comparison does not authenticate
publication identity, estimator semantics outside the table or correctness
of the real paper's sampling model.

Review bundles preserve original XML, source anchors, exact implementation
hashes, JSON/escaped HTML and a SHA-256 manifest. Replay detects modified
results or code, but does not prove publisher source authenticity; preserve
an externally trusted manifest hash. No provider access, PDF, author contact,
financial spend, production publication or protected test material is involved.
See [the original-byte table projection](JATS_TABLE_PROJECTION.md),
[agent instructions](../AGENTS.md) and [current execution state](EXECUTION_STATE.json).
