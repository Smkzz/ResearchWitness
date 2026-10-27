# Offline PMC OAI-PMH source derivation (RW-01M)

**Status:** engineering development adapter, not a real-source collection, an authenticated acquisition, a licence clearance or a scientific result. It is checkout-only and does not make network requests.

## Input and evidence custody

The operator must use a separately authorized PMC acquisition path and preserve the complete, unmodified **decoded HTTP response entity** as a private file. These bytes are not necessarily the compressed wire bytes. Keep request details, response status, capture time and an independently calculated SHA-256 externally. A web snippet, copied JATS fragment or reserialized XML is not original OAI response evidence.

Only a single PMC OAI-PMH 2.0 GetRecord response for a declared research article is currently supported. Its request must specify verb GetRecord, metadataPrefix pmc and an exact OAI identifier. The caller also supplies a private transfer-declaration JSON with these exact keys:

    {
      "schema_version": "rw-pmc-oai-transfer-declaration.v1",
      "endpoint": "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/",
      "verb": "GetRecord",
      "metadata_prefix": "pmc",
      "requested_identifier": "oai:pubmedcentral.nih.gov:12345",
      "http_status": 200,
      "body_stage": "decoded_http_entity",
      "expected_body_sha256": "REPLACE_WITH_64_CHARACTER_RAW_SHA256",
      "captured_at_utc": "2026-10-26T20:21:00Z",
      "provider_response_id": null,
      "declared_license_id": "CC-BY-4.0",
      "rights_evidence_uri": "https://creativecommons.org/licenses/by/4.0/"
    }

This is a fictional template, not a valid original response or verified licence record. The operator-declared timestamp, provider HTTP status, response ID and licence evidence are **not authenticated by the tool**. Do not invent response IDs if unavailable. Source XML must itself contain one unambiguous article-level licence link compatible with the declared CC-BY-4.0 or CC0-1.0 classification. Source syntax alone does not establish legal reuse rights. Confirm actual article-specific terms independently before handling real material.

## Offline extract and replay

Operate inside an existing private directory. Never commit original response, standalone article, raw review data or private receipts.

    python -m tools.pmc_oai_envelope --action extract --raw-envelope PRIVATE_response.xml --transfer PRIVATE_transfer.json --output-source PRIVATE_derived.xml > PRIVATE_receipt.json

Store the receipt SHA-256 separately from the private receipt. Replay with that externally retained pin:

    python -m tools.pmc_oai_envelope --action replay --raw-envelope PRIVATE_response.xml --transfer PRIVATE_transfer.json --derived-source PRIVATE_derived.xml --receipt-envelope PRIVATE_receipt.json --expected-receipt-sha256 EXTERNAL_RECEIPT_DIGEST

Extraction creates a fresh file only, with private file mode on supported systems. It never prints article contents. The receipt ties together the full raw envelope hash, exact original article byte span and hash, independently derived standalone JATS hash and byte length, extraction profile, and count of namespace declarations inserted into the derived start tag.

An inherited namespace such as xmlns:xlink may be injected to preserve expanded XML semantics. The resulting XML is **derived**, not the original raw transfer or necessarily an identical byte slice. The original and derived representations have separate SHA-256 commitments and strict replay. The bounded existing JATS parser is used for the derived article.

## Next-stage chain

Use the **derived** SHA-256 as RW-01K origin.expected_source_sha256, not the original envelope hash. Keep the RW-01M receipt and original response externally beside the private RW-01K manifest. Use the same derived article bytes for RW-01J review and RW-01L source-to-review binding. This version does **not** automatically verify the complete RW-01M-to-RW-01K chain. Publisher/source identity, actual rights, correction lineage, reviewer independence and scientific denominator interpretation still require separate evidence.

Malformed, oversized, DTD/entity/XInclude-bearing, multiple-article, incompatible-namespace, ambiguous-license, correction/retraction, mismatched-ID and unavailable-response inputs are rejected or unsupported. Failed source attempts must remain in acquisition denominators, not quietly disappear. No real provider capture is included in public tests. Issue #35's independent source pilot and custody gates remain open.

## RW-01N: enforce the complete declared identity chain

After replaying the raw-to-derived response, create an RW-01K capture envelope
using the **derived** JATS bytes, not the original OAI-PMH response. Set its
retrieval route to `pmc_open_access`, capture URI to the literal OAI endpoint
(no request query), declared captured time and licence/evidence declarations
to the exact values in the private RW-01M transfer record, and source SHA to
the derived-JATS SHA. Build an RW-01J reviewer packet from precisely those
same derived bytes; preserve the external digests for each stage.

The checkout-only RW-01N command validates the complete offline chain:

    python -m tools.pmc_source_review_chain \
      --raw-envelope PRIVATE_response.xml \
      --transfer PRIVATE_transfer.json \
      --derived-source PRIVATE_derived.xml \
      --derivation-envelope PRIVATE_derivation_receipt.json \
      --expected-derivation-sha256 EXTERNAL_DERIVATION_DIGEST \
      --metadata PRIVATE_metadata.json \
      --capture-envelope PRIVATE_capture.json \
      --expected-capture-sha256 EXTERNAL_CAPTURE_DIGEST \
      --packet-envelope PRIVATE_packet.json \
      --expected-packet-sha256 EXTERNAL_PACKET_DIGEST

Two locally supplied development reviewer records may additionally be passed
with `--review-a` and `--review-b`, **together**. Existing RW-01L reconciliation
rules and safety limits are reused unchanged.

The summary includes the pinned raw envelope, derived source, capture and review
hashes and aggregate review status. It never prints article text or reviewer
rationales. Version/family identity remains an **operator declaration**, and
metadata equality is not an external attestation, historical timestamp,
publisher/rights verification, human review, scientific correctness or a sealed
holdout permission. The command performs no network acquisition, privileged
custody operation, external publishing or scientific evaluation.

## Private pilot intake ledger (RW-01O1)

When actual permission-cleared raw PMC responses exist in an already
authorized environment, use [the private ledger](PMC_PILOT_LEDGER.md)
to account for every selected source-family attempt and replay the
RW-01M/N/K/J/L evidence chain. Unavailable, licence-blocked,
parser-refused and pending-review cases remain in the denominator.
No download, publisher authenticity, legal licence adjudication,
reviewer-independence proof or sealed material access is enabled.
