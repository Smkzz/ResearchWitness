# Offline development-source capture & version lineage (RW-01K)

**Scope:** prepare auditable **declarations** about source bytes, retrieval
route, rights and publication/version family before real-world denominator
review. No internet fetch, publisher authentication, actual legal opinion,
independent label adjudication, protected corpus or holdout qualification
is performed. No raw JATS XML is printed or committed by this tool.

This is a **checkout-only** helper, not a newly installed core verifier or a
replacement for licensed acquisition or independent source review.

## Offline capture procedure

Given a private local JATS XML file, independently compute its SHA-256. Create
a private metadata JSON file with exact schema `rw-development-source-metadata.v1`.
The keys are:

- `record_id`: unique source/version record identifier.
- `work_family_id`: conservative **declared** family grouping. Corrections,
  revisions and supplements must share their parent article's family.
  Different families may nonetheless share underlying data; this tool cannot
  rule that out.
- `version_id`: unique within a declared family; `kind` is `article`,
  `revision`, `correction` or `supplement`.
- `parent_record_id` is null for an initial article and must reference an
  included record for every correction/revision/supplement.
  `correction_notice_uri` (HTTPS) is mandatory for kind `correction` and null
  otherwise. URI existence and notice meaning are *not* checked.
- `origin` has `retrieval_route` (publisher_open_access,
  pmc_open_access, institutional_repository or operator_supplied),
  `capture_uri` and `publisher_uri` (HTTPS with no query/credentials, nullable
  for operator supplied), `captured_at_utc` (operator-declared exact UTC
  calendar timestamp) and `expected_source_sha256` (independently retained
  original file digest).
- `rights` has `classification`, `license_id` and `evidence_uri`.
  Declared open status only accepts CC-BY-4.0/CC0-1.0 with a declared
  evidence URL, or separately documented permission with its evidence URL;
  unknown/restricted material cannot claim any license. The tool never
  verifies that a URL truly proves a license or redistribution permission.
- `exposure` must be `partition=development_exposed` with
  `prior_access` of known_exposed/unknown/declared_not_exposed, and
  `label_status=no_independent_scientific_label`. No protected or
  confirmatory source identity may be promoted by changing fields.

With source file, metadata JSON and its declared digest:

    python -m tools.source_capture_manifest --action capture --source PRIVATE.xml --metadata PRIVATE_metadata.json > PRIVATE_capture-envelope.json

The command prints exactly an envelope containing `manifest` and
`manifest_sha256`. The manifest includes original source SHA-256/byte length,
metadata, supported JATS parser contract and explicit FALSE flags for
publisher/rights/timestamp authenticity, label quality and protected access.
The output has no original source excerpt. Keep raw XML and metadata outside
public Git; identifiers or URLs might still be sensitive.

Preserve the capture-manifest hash **outside the envelope**. Replay exact
source and metadata, using that hash:

    python -m tools.source_capture_manifest --action replay --source PRIVATE.xml --metadata PRIVATE_metadata.json --capture-envelope PRIVATE_capture-envelope.json --expected-manifest-sha256 EXTERNALLY_SAVED_HASH

The program regenerates the metadata-bearing manifest and rejects source
mutation, tampered rights/exposure/lineage fields, altered hashes or a
different source. This proves consistency of supplied bytes and operator
declarations only. It does NOT independently check acquisition, timestamp,
license, publisher version identity, study population or source meaning.

## Version-family registry (declared lineage)

Prepare a private JSON object:

    {
      "schema_version": "rw-development-source-registry-input.v1",
      "captures": [
        {"manifest": {"...": "one complete capture manifest"},
         "manifest_sha256": "its captured canonical SHA-256"}
      ]
    }

The example above illustrates the shape; the capture entry must be the **exact
envelope**, not a placeholder manifest. Include one entry per distinct source
record/version, compute and preserve the canonical registry input digest
(UTF-8 ASCII JSON, sorted keys, minimal separators, trailing LF) as documented
by `tools.verification_benchmark.commitment`. Validate:

    python -m tools.source_capture_manifest --action registry --registry PRIVATE_registry-input.json --expected-registry-sha256 EXTERNALLY_SAVED_REGISTRY_HASH

The registry requires unique record IDs and unique version IDs per family;
no two declared independent families may share identical source bytes.
Identical source bytes under a different version ID **within the same family**
are also refused: replay an existing capture instead of inventing a new version.
It checks that each correction/revision/supplement parent appears in the same
family, has a nonlater **declared capture timestamp**, and that no parent cycle
exists. All versions and supplements remain grouped under the family: they
cannot inflate the number of claimed independent works.

**Important:** registry mode does **not** reopen the original XML files. It
only checks the manifest envelopes and separately supplied external registry
pin. It reports `source_bytes_replayed_by_registry=false`, and does NOT
authenticate rights, origin, correct correction relationships or scientific
work-family independence. Actual shared datasets can cross declared
families without duplicate XML bytes. This is a positive obligation for
subsequent independent provenance review, not a green scientific gate.

## Negative evidence and future integration

The original JATS parser rejects malformed UTF-8/XML, DOCTYPE/ENTITY and
over-limit input. A capture refuses a source-hash mismatch or non-JATS root.
JSON parsing rejects duplicates, noninteger numbers, nonfinite values and
overdeep structures. Plainly invalid URLs, noncanonical UTC timestamps,
unsigned lineage links and rights/protected-classification claims fail closed.
Source file symlinks/special files are rejected by the shared bounded
regular-file reader. The CLI never fetches the URLs it records.

All automated tests use **invented/developer-exposed** XML and metadata. No
real licensed paper or independently adjudicated label is included here.
The source review packet in [DENOMINATOR_SCOPE_REVIEW.md](DENOMINATOR_SCOPE_REVIEW.md)
uses the same raw-source SHA and can later be associated with this capture
manifest externally; the current tool does not claim two independently
authenticated reviewers or complete substantive JATS source interpretation.

Next required work: obtain separately permission-cleared original
publisher versions/corrections, independently verify rights and identity,
capture actual retrieval evidence and exposure, and collect separate
substantive denominator-scope interpretations. Compare the old PR #11
scope resolver against these **development** annotations without retuning a
protected holdout. A custody/sealed test would still require RW-03/RW-05.
