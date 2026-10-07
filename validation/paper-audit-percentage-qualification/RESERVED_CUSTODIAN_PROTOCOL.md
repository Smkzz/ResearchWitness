# Reserved correction eligibility custody protocol

Status: frozen before any reserved correction body or detector output is
opened. This protocol applies only to the single preallocated metadata lead;
it does not authorize a broader correction search.

## Custodian separation

1. A separate custodian receives the existing reserved metadata record and the
   frozen percentage contract. The custodian does not receive detector code,
   candidate reports, the DEVELOPMENT replay, or any DEVELOPMENT candidate
   labels.
2. The custodian may retrieve and inspect the original source and correction
   solely to determine whether at least one exact correction target is
   eligible under contract 1.2. The custodian must not run ResearchWitness or
   inspect any detector output.
3. The custodian records source/version identity, hashes, and a private
   eligibility rationale in a hash-bound record stored outside the
   repository and outside every runner input directory. The record must not
   be passed to the development replay.
4. The only result returned to the qualification owner is exactly one of
   `ELIGIBLE_FOR_FROZEN_CONTRACT` or `NOT_ELIGIBLE_FOR_FROZEN_CONTRACT`, plus
   the sealed record SHA-256. No DOI, target cell, operands, corrected values,
   or rationale are returned.
5. If the original/correction source cannot be pinned or eligibility cannot
   be established without weakening contract 1.2, return
   `NOT_ELIGIBLE_FOR_FROZEN_CONTRACT`. If the custodian cannot keep the body
   and record outside runner inputs, leave the lead unopened and report the
   limitation instead.

This procedure confirms source eligibility only. The reserved positive and
its detector sensitivity remain unseen and unscored in this wave.
