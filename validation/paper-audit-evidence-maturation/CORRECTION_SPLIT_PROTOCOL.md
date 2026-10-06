# Correction lead allocation protocol

**Protocol ID:** `researchwitness-correction-split-v1`  
**Recorded:** 2026-10-06  
**Recorded before:** broad correction-corpus mining for this wave.

This is an evidence-maturation protocol. It does not change detector code,
eligibility rules, thresholds, or the existing 33-document development replay.
The already-reviewed 16 correction issues remain in the pre-existing
`DEVELOPMENT` corpus. Every newly discovered correction lead is allocated by
the procedure below before its corrected operands or any ResearchWitness
output are inspected.

## Allocation

1. Record the original-work identifier and correction identifier from
   bibliographic metadata only. Prefer DOI. If one DOI is unavailable, use a
   stable namespaced identifier (`PMID:`, `PMCID:`, `arXiv:`, or `EuropePMC:`).
2. Normalize each identifier with `tools/assign_correction_split.py`: trim
   outer whitespace, normalize the namespace and identifier to lowercase, and
   normalize DOI URLs or `doi:` prefixes to `doi:<identifier>`.
3. Construct UTF-8 bytes for
   `researchwitness-correction-split-v1\n<original-id>\n<correction-id>`.
4. Compute SHA-256. Convert the first eight hexadecimal digits to an integer
   and take modulo 5.
5. Bucket 0 is `RESERVED_FOR_FUTURE_EVALUATION`; buckets 1–4 are `DEVELOPMENT`.
   Record the full hash, bucket, and assignment in the screening ledger before
   opening correction full text or the original source.

This fixes an approximately 20% reserved share without choosing cases by
detector family, ease of interpretation, or apparent result. Assignments are
immutable. Duplicate records for the same normalized identifier pair inherit
the original assignment. Leads without a stable identifier pair stay
`UNALLOCATED`; they cannot be run as development cases or counted as reserved
eligible positives.

## Information boundary

After allocation, a development lead may be source-adjudicated and replayed.
For a reserved lead, the mining workflow records only bibliographic
identifiers, source/version availability, retrieval date, and family-level
metadata. It does not open full text, inspect correction operands, extract
table values, inspect detector output, or invoke ResearchWitness. Any later
unsealing requires a separately controlled future evaluation protocol.

The split script only computes the deterministic allocation. It neither
retrieves sources nor runs a detector. The allocation itself is metadata-only;
it is not an eligibility or correctness judgment.
