# Supplemental reserved correction positive screening protocol v1.3

Status: created 2026-10-08 after the custodian had already accessed reserved
source-body material. It does not retroactively preregister that screening or
qualify any case found before this protocol was reviewed. The custodian was
asked to pause further body access until reviewing this protocol. This governs
eligibility curation only; it does not authorize running ResearchWitness on a
reserved source.

## Frozen metadata allocation

The custodian reports a metadata-only inventory of 225,080 deduplicated
original/correction identifier pairs and that its recorded inventory digest
matches. The previously reported 22,305 `RESERVED` assignments were produced
with a separate DOI-pair modulo-10 rule, not the repository's predeclared
split. Reapplying the repository's canonical rule to the inventory produces
45,211 `RESERVED` assignments. The two allocations do not agree, so the
previous allocation is unverified and the 22,305 count is superseded. No
case from that allocation can count toward the reserve gate.

The existing
`validation/paper-audit-evidence-maturation/CORRECTION_SPLIT_PROTOCOL.md`
defines identifier normalization and the SHA-256 modulo-five allocation; its
full-text boundary remains in force.

The canonical split rule was recorded before broad correction-corpus mining,
but the custodian's recorded allocation did not follow it. On 2026-10-08, the
custodian verified the metadata inventory digest and created a new,
hash-bound canonical allocation ledger and deterministic order before any
further body retrieval. The canonical bucket counts were 45,211, 44,783,
45,204, 44,885, and 44,997 (bucket 0 is RESERVED). If the private ledger or
order cannot be verified during screening, leave further bodies unopened and
report the limitation.

## Custodian and deterministic screening order

1. Only the independent custodian may inspect reserved original and
   correction material. The custodian must not receive detector code,
   DEVELOPMENT reports, candidate labels, or detector output.
2. Deduplicate reserved records by the normalized original/correction
   identifier pair defined in the split protocol.
3. Before any further retrieval, verify the metadata inventory hash, canonical
   allocation, and deterministic order; preserve the count of all pairs
   already opened; and record that the original screening did not use the
   canonical allocation or order. Fourteen unique source-body pairs were
   opened, among 50 metadata-screened pairs, under the mismatched allocation.
   The exact membership of the 14 is unavailable in the prior aggregate
   record, so exclude all 50 legacy metadata-screened pairs from any further
   body retrieval and from the untouched-positive count. This conservative
   content-independent exclusion covers the 14 without revealing identities.
   Report any failure or uncertainty in the reconciliation.
4. For any further screening, order the canonical reserved inventory by the
   full split-protocol SHA-256 digest, then normalized original identifier,
   then normalized correction identifier. Skip the 50-item exclusion set and
   any other already-opened pairs without disclosing them. Do not reorder based
   on availability or apparent table content. Because this supplemental
   protocol postdates the initial access, any resulting search must be
   described with that limitation and must not be represented as
   prospectively preregistered from the first body.
5. For each unopened pair, determine source availability and v1.3 eligibility
   from the original and correction only. Do not run ResearchWitness, a local
   detector, or a candidate-matching script.
6. Stop after the first case satisfies every acceptance rule below. If none
   qualifies, continue through the complete reserved inventory when source
   acquisition permits. If screening stops early for a material limitation,
   report only the aggregate screened count and limitation; do not claim that
   no eligible case exists.

## Acceptance rules

A reserved positive qualifies only when the custodian independently confirms
all of the following under the finalized count/percentage contract v1.3:

- The uncorrected original source and correction notice are available and
  individually hash-pinned.
- The exact original source version is pinned and is not an already-corrected
  substitution.
- The correction maps to one explicit count/denominator/percentage
  relationship in the original.
- Numerator, denominator, percentage unit, displayed precision, and semantic
  denominator scope are explicit under v1.3.
- Exactly one most-specific compatible denominator source applies; any
  competing denominator has a source-anchored rejection reason.
- The correction identifies that exact relationship and the expected
  corrected value.
- Eligibility does not require a model-derived result, image-only source,
  inferred denominator, or arithmetic-convenience reconstruction.

## Sealed record and return boundary

For a qualifying case, the custodian stores a sealed packet outside the
repository and every development-runner input directory. The packet contains
the case identifier, original/correction identifiers and hashes, exact
eligibility evidence, correction mapping, and expected target. The runner and
development owner receive no identifiers, target cells, values, mapping, or
expected output.

The only return is `RESERVED_CASE_FOUND=true/false`, the sealed packet
SHA-256 if true, aggregate count screened, confidence, and non-identifying
limitations. If a qualifying case is found, stop. Preserve it as an untouched
future Wave-3 input; do not evaluate it in this wave.

The reserved-negative source-only pool is separate and remains unavailable to
this custodian unless independently assigned under its own source-only
protocol. Neither reserve pool may be passed to a detector or joined to
detector output in this wave.

## Screening result at qualification cutoff

After canonical allocation and order were verified, two pairs were screened:
one was fully assessed and found outside the correction scope, and one remains
unresolved because publisher material was inaccessible. No eligible positive
is confirmed; this is not an absence finding. The custodian reported low
confidence, kept target details hidden, and did not run the detector. Automatic
review rejected a Crossref metadata fetch because it would transmit a
custody-held identifier externally; no alternate retrieval route was used, so
canonical screening remains incomplete.

The prior mismatched allocation had 50 metadata-screened pairs and 14
source-body pairs opened, with exact membership of the 14 unavailable. All 50
were excluded from further body access and from the untouched-positive count.
