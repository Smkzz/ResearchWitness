# Opt-in JATS prose flow review — RW-01G

**Type:** installed offline development aid, not general research error
detection, independently validated source interpretation or custody
qualification. This selectively adapts the reviewed PR #11
`paper_flow_source.py` model and current `paper_flow.py` checker.

## Use

```text
python -m researchwitness audit-jats examples/synthetic-jats/prose-flow.xml --document-id synthetic-flow --output-dir work/prose-flow --include-prose-flows
python -m researchwitness replay-jats work/prose-flow --expected-manifest-sha256 OUTSIDE_PIN_OF_AUDIT_MANIFEST
```

The output contains `sample_flow_review` in `report.json`, with each
eligible mapped relation classified as `FLOW_BALANCED`,
`FLOW_ARITHMETIC_CANDIDATE`, `FLOW_RELATION_AMBIGUOUS` or
`UNSUPPORTED`. The HTML includes an escaped unreviewed-candidate table.
The unchanged default audit remains percentage-only. The optional flags
`--include-structure`, `--include-unadjusted-2x2` and
`--include-prose-flows` may coexist, using one saved original XML source
and replay contract. The report always states
`whole_article_coverage_established: false`.

## What is actually supported

- The same `_jats_parser` as the installed table audit produces
  original-byte `Paragraph` element anchors; no legacy XML-normalizing
  parser is used. Each fragment quote is a **normalized, bounded text
  excerpt** and its element `start_byte:end_byte` covers the **entire
  original XML paragraph including markup**, not the excerpt or its number
  tokens. Never treat them as token byte offsets.
- A candidate requires total and included operands plus at least two
  exclusion operands, all from **one** eligible body paragraph, and explicit
  disjoint/exhaustive/remainder or sequential/remainder language.
  Population, unit, group and timepoint must agree; mismatches or uncertain
  exclusion overlap are unsupported/ambiguous.
- Front matter, abstracts, figures, table captions, footnotes, back matter,
  nested paragraphs and unsupported complex inline markup are excluded.
  The source model exposes eligible and excluded counts/warnings.
  The system never combines prose from two paragraphs, tables or sections
  to manufacture a proof.
- The source parser has original input, XML depth/node and JATS resource
  limits. Body paragraph counts and flow relation counts have separate
  bounds. Exceeding one fails closed rather than truncating candidates.
- The same integer `paper_flow.check_flow_relation` validates only
  supported, explicit finite add/subtract operations. No interpretation of
  causal inference, trial populations, study design or publication versions
  is established.

## Research and security limitations

Passing arithmetic is not publisher authentication or proof of a paper
being right; a discrepancy is not proof of it being wrong. Syntactic
source-local eligibility does not independently authenticate the
exclusion categories or their exhaustiveness. Full sample-flow recall
is not measured, and absent mappings do not count as confirmed negatives.
Source bytes and deterministic replay establish consistency with the same
installed code, not scientific applicability.

Only private, offline JSON/HTML bundles are generated. The JATS parser
rejects DOCTYPE/ENTITY and XML depth abuse; no source-side instructions,
external URLs, providers or scripts are run. Without an externally held
manifest digest, coordinated modifications to all bundle files cannot
be excluded solely by self-replay. This is not a separate security
sandbox. Do not send private/unlicensed source data to unapproved
providers, contact authors or publish unreviewed findings.

The synthetic example is intentionally made up: 100 initial, 10 and 5
exclusive exclusions, 80 printed included (candidate versus expected 85),
and separate balanced and ambiguous examples. These do not demonstrate
scientific discovery accuracy. Remaining RW-01 work includes provenance,
source-mapped SD/SE/n and other paper-level relations; protected custody and
real PDF remain separate RW-03/05 gates.
