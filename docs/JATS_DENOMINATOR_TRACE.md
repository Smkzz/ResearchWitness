# Source-anchored JATS denominator evidence trace — RW-01I

**Type:** optional deterministic fail-closed scope-first resolver report;
advisory, not adjudication, source-authenticity proof, correction finding, study-level
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
  normalizing XML parser is not imported. The standalone PR #11 resolver
  consumes projected Table objects; current detector numerator, denominator, status, scope and
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

The report schema is now `rw-jats-denominator-evidence.v3` (the version is
recorded in bundles). Each relation adds `denominator_provenance`: resolution
status/reason, relationship scope, selected value/source anchor and rejected
competitors/reasons. `resolved_value_equals_detector_base` is null when the
resolver selects no base or the detector base is missing; otherwise it compares
the two integers. Top-level `resolution_status_counts` summarizes resolver
statuses. `detector_resolver_disagreement_count` counts only relations where both
bases exist and differ. `resolver_selected_without_detector_base_count` separately
counts relations where the resolver selected a base but the detector had none.
These v3 semantics replace v2's comparison against a missing base. This does not
alter detector decisions. Implementation fingerprints are included in every
product report, plain or trace. Any bundle made before an implementation
change that alters those fingerprints will not replay exactly under the new
implementation. Replay it with the implementation commit that created it.
Old bundles are not migrated; exact replay stays strict, with no compatibility
shim. See [the release process](RELEASING.md#exact-bundle-replay).

Product reports run the detector once and build at most one table projection,
shared between trace and all structure-backed modes. Public `trace_denominators`
and `project_jats_tables` still recompute and compare any supplied detector report
in full; only private product paths reuse reports computed from the same bytes.
Tables are indexed by original cell byte spans. The adapter
retains `RELATION_CELL_NOT_PROJECTED` as defense in depth: projection normally
raises on an unbound detector finding, so this branch requires bypassing that
contract (as the existing monkeypatch test does). The adapter
binds row-group identity to the original enclosing XML element's byte offset,
including separate unnamed body groups, preserving cells and anchors. Subgroup
boundaries and parent-count groups stop at group boundaries and are computed
once per table. Printed cell-ratio denominators are passed as explicit local
source facts with their original printed numeric spelling (grouped tokens
remain unsupported), not inferred from arithmetic agreement. Ambiguous header/body
layouts and spanning-cell roles produce `UNRESOLVED / TABLE_STRUCTURE_UNSUPPORTED`.
Invalid candidates retain their printed value, source anchor and rejection
reasons even when no denominator resolves. A
valid broader candidate blocked by an invalid equally or more specific base
retains an explicit blocking reason. A missing
projected relation cell produces `UNRESOLVED / RELATION_CELL_NOT_PROJECTED`.
Neither arithmetic fit nor a detector-inferred base is fed to the resolver.
Review packets continue to expose source facts, not these advisory preferences.

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
