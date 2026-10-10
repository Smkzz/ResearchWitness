# Threat model — ResearchWitness offline custody worker v5

## Protected assets

Original/correction source bytes and hashes, identifiers and versions, relation values and locations, eligibility attestations, correction mappings, private review records, and inventory seals. These must not enter development prompts, logs, shared caches, source control, or public exports.

## Trust assumptions

The custodian identity and a trusted system administrator are privileged. This worker does not defend against a hostile local administrator, compromised custodian token, filesystem rollback, or same-token process racing file operations.

Development agents must not have filesystem or execution access to the custody environment. A different directory on a shared filesystem is not isolation.

## Implemented application controls

- Fixed production identity/root preflight and a marked synthetic-only temp mode.
- Exact byte-span validation over hash-verified imported UTF-8 source objects.
- V5 eligibility requires a one-physical-line relation context, an explicit literal `count` field cue before the numerator, non-overlapping table and relation-value spans, and complete mapping of numeric characters on that line; cross-line table/header joins and ambiguous extra values fail closed.
- Hash-pinned source imports record an approved-host source URL, UTC acquisition time, license notice, and public-use attestation; review manifests record the active custodian account and time.
- Strict JSON keys and versions, duplicate-key rejection, safe names, bounded source and ledger sizes, and bounded directory traversal.
- Refusal of symlinks, Windows reparse points, hard-linked files, unexpected entries, and unsupported review formats.
- Exclusive operation lock, immutable content-addressed source storage, source-object hash revalidation, relation deduplication, and non-repairing verification.
- Per-store random HMAC key; the public commitment is keyed and is not a bare hash of predictable identifiers.
- Threshold-only public summary after its declared count thresholds, schema checks, and one-time export bound to a sealed inventory. The document count is distinct DOI IDs, not alias-resolved independent works, and cannot alone satisfy the independent-paper gate.
- Generic CLI errors with no private path, source text, or identifier.

## External controls still required

- Isolation of the execution environment and descendants, installed code, temp space, backups, logs, clipboard and output destinations.
- Identity-specific access-denial proof for ordinary users, development agents, and the separate WW2 runner.
- Independent outbound policy limited to the four approved hosts, TLS checks, redirect validation, response-size/decompression limits, request pacing and retry caps. The worker has no network client; this does not enforce egress.
- Source licensing, source authenticity, original-version status, and semantic applicability review by the custodian.
- Resolution of DOI aliases and other version/work-family links under a separately reviewed custodian identity map before treating DOI IDs as independent documents.
- Acquisition provenance fields are attestations. This code does not fetch sources, follow redirects, evaluate licensing terms, or authenticate the timestamp.
- A separately controlled offline handoff process that binds acquisition provenance to identifiers, timestamps, licensing notices, byte lengths, and hashes.

No custodian environment is available to this development session. The external controls are not claimed as passed. V5's one-line profile intentionally leaves ordinary multi-line table header/cell relationships unresolved; it is not an independent structured-table parser.
