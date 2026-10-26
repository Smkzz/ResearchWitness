# Source-anchored JATS denominator evidence trace — RW-01I

**Type:** optional engineering/source-continuity audit, not a denominator
*resolver*, source-authenticity proof, correction finding, study-level
verification or scientific benchmark evaluation.

## Interface

```text
python -m researchwitness audit-jats examples/synthetic-jats/denominator-trace.xml --document-id synthetic-denominator --output-dir work/denominator-evidence --include-denominator-trace
python -m researchwitness replay-jats work/denominator-evidence --expected-manifest-sha256 EXTERNALLY_PRESERVED_DIGEST
```

By default the installed JATS audit keeps its existing percentage-only
output. The opt-in adds `denominator_evidence_trace` to the same private
JSON report and a compact escaped HTML preview. The full JSON retains every
source fact, including unresolved relationships; HTML displays up to eight
facts per relation and **explicitly signals** any remaining facts are in JSON.

The review can be combined with any already-supported optional JATS mode
(including structured tables, unadjusted 2×2, SD/SE/n and prose flows).
All optional sections are deterministically recomputed on bundle replay.

## What the trace independently checks — and what it does not

- It uses only the existing bounded, original-byte JATS XML parser. The old
  normalizing XML parser and the legacy full denominator resolver are **not**
  imported; current detector numerator, denominator, status, scope and
  ambiguity decisions are **never changed**.
- Every relationship is replayed against unchanged source bytes. A supplied
  detector report that merely has the correct SHA-256 but differs in facts,
  offsets, source positions or arithmetic status is rejected.
- Every existing denominator source fact is tied to its **actual parsed XML
  element**, with its role, printed integer, element path, exact original
  XML start/end bytes, normalized excerpt and source hash. A semantic number
  cannot be attached to a fabricated or absent byte span. Element byte
  ranges contain **markup**, not an asserted numeric-token byte range.
- Any visible competing numeric values remain visible. Equality between a
  source fact and the detector's selected number is **numerical equality only**,
  not proof that its denominator applies to the stated population.
- Already-ambiguous, rounding-uncertain and conditional calculations retain
  their non-accepted states; the trace does not revise them, suppress
  mismatches or promote unresolved facts. Missing source facts and method-
  scope overflow are explicitly visible. This ledger records existing
  detected relations only, not a full census of scientific percentages.
- Exact input, XML node count/depth, result count, per-relation source-fact
  and total source-fact caps apply. An over-limit trace fails closed and
  cannot silently appear complete. Output retains the existing finite
  private JSON/HTML and manifest size ceilings.

## Scientific, security and licensing limits

A contradictory header and table caption may refer to different analysis
populations; different numeric facts are not automatically false. This
tool does not independently evaluate subgroups, missingness, alternative
percentage bases, statistics models, source/publisher authenticity,
numerical precision conventions, footnote applicability or causal claims.

The example files are invented and developer-exposed. There is no PDF/OCR,
real protected corpus, provider model, author communication, software
publication, new sandbox permission or real-money expense. Do not use this
as a negative-label oracle or publicly accuse authors. Source custody,
licensed material and scientific promotion require separate RW-03/RW-05
gates. An **externally preserved** manifest digest is necessary to detect
coordinated changes to source and results; self-replay by itself does not
establish origin or scientific correspondence.

See [current status](PROJECT_STATUS.md), [the integration map](INTEGRATION_MAP.md)
and [the autonomous agent instructions](../AGENTS.md). Source and exact
CI/postmerge receipts belong to PR #32.
