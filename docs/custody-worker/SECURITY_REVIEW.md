# Custody worker v5 security review

Scope: current offline worker source, runtime schemas, checked-in synthetic fixtures, and synthetic tests in the integration worktree. The v4 code was separately reviewed read-only; that audit found a way to use a table identifier digit as an arithmetic operand. V5 implements the reported restriction and adds exploit regressions. The v5 changes have not received a separate post-fix review. This is not a Codex Security scan, Windows access evaluation, or hostile-operator exercise.

## Remediations implemented

- Imported source bytes are hash-checked and eligible text relationships use exact UTF-8 byte spans. V5 requires an exact one-physical-line context, a literal `count` field label immediately before the numerator, non-overlapping table-locator and relation-value spans, and complete coverage of numeric characters and percent markers. Correction old values must be on that same line and not overlap relation values.
- Synthetic regressions reject both a correction-positive attempt to reuse `Table 2`'s digit as the numerator and an otherwise source-bound row with no explicit `count` cue.
- Correction positives require an original arithmetic mismatch, a correction filed under the submitted canonical DOI family, byte-bound correction values, exact changed fields, and a recomputing corrected relation. The identity, mapping, and scope judgments remain custodian attestations.
- Equal normalized numerator/denominator/percentage values collapse per DOI, independent of reviewer context, locator, source version, or display precision. This can undercount separate rows; it cannot create a higher relation minimum through those aliases.
- Positive issue count is capped at one per DOI because correction identifiers are not independently validated.
- Summary/public-export schemas call their count `distinct_negative_document_ids`, not independent documents. DOI aliases/work-family identity are not resolved.
- Source-version identities cannot bind changed bytes; store verification rejects missing, modified, orphaned, or unexpected source objects. Imports, reviews, summary, and seals use serialized store operations.
- Build paths reject symlink/reparse components and hard-linked input/output files; output checksum sidecars are atomically replaced. Synthetic regressions cover linked sidecars and input parents.
- Public export uses strict versioned schemas, withholds below count thresholds, is keyed to a sealed inventory, and is one-time per snapshot. It is an aggregate mechanism, not proof that identity/readiness gates passed.
- CLI errors use public codes. Doctor explicitly says host egress must be verified externally; the worker has no network client.

## Remaining material issues

- **No custody boundary is proven.** This session has no separate custodian route. Identity/SID, descendant ACLs, temp/log/backup/output channels, installed-code ownership, the separate runner, Windows junction behavior, and host egress remain unverified. No reserved data was accessed.
- **Source identity and semantics are still asserted.** Hashes bind bytes, not publication authenticity, version, permission, DOI-to-work-family identity, correction applicability, or meaning of scope. A custodian-supplied DOI can be an alias; the worker cannot resolve aliases.
- **V5 narrows eligibility sharply.** Multi-line tables, header-to-row joins, and numerator expressions without a literal `count` field are unresolved. A same-line one-relation profile is not a substitute for a validated structured parser; no real paper was tested.
- **The DOI-ID denominator is not the independent-document minimum.** The renamed public aggregate cannot prove 15 independent works. A custodian-controlled, independently reviewed work-family/alias mapping is needed before that gate can pass.
- **The same-account threat remains.** Local processes under the custodian token and privileged administrators can race or alter local files; no OS sandbox or network allowlist exists in the worker.
- **Local product HTTP/browser validation is blocked here.** Loopback binding returned `PermissionError: Operation not permitted`; no alternate route was attempted. Direct local-store lifecycle tests pass, but API/CSRF and real-browser UX remain unqualified.
- **Hosted and platform gates remain open.** Pytest is unavailable, so full repository regression did not run. No Windows build, CI, CodeQL, clean Windows install, or production rehearsal ran on this working tree.

The source-span contract limits operand borrowing for one narrow source format; it does not prove that an identified sentence or table row has the scientific meaning asserted by the reviewer. No worker review is equivalent to a detector result or independent publication verification.
