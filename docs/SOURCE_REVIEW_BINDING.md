# RW-01L: Bind developer source captures to source-scope reviews

The checkout-only `tools.source_review_binding` uses existing RW-01K and
RW-01J tools to ensure that exactly one **declared** article/version,
source hash, source capture manifest and denominator review packet are
replayed over the **same original JATS XML bytes**.

This is an engineering identity check, **not** publisher authenticity,
licence verification, researcher independence, scientific denominator
adjudication, protection of a sealed dataset, or authorization to contact
authors. Do not put real source XML or private reviewer statements in Git.

## Workflow

Create offline capture metadata and an envelope using RW-01K, and make
the corresponding packet using RW-01J. Preserve the externally recorded
capture and packet digest values in a separate trusted store. Then run:

    python -m tools.source_review_binding --source PRIVATE_source.xml --metadata PRIVATE_metadata.json --capture-envelope PRIVATE_capture.json --expected-capture-sha256 CAPTURE_DIGEST --packet-envelope PRIVATE_packet.json --expected-packet-sha256 PACKET_DIGEST

For two already collected review records, add:

    --review-a PRIVATE_review_a.json --review-b PRIVATE_review_b.json

The second form checks complete, source-ID-bound reviews using RW-01J
and emits the digest and status counts of its descriptive reconciliation.
It never prints original source text, full review rationales or publisher
claims. A selected source fact or matched review does not become a
scientifically true denominator from this procedure.

### Failure behavior

- Different raw source bytes, altered version IDs/metadata, stale external
  digest commitments, packet facts added or removed, swapped original
  anchors or invalid review records cause a nonzero exit.
- The CLI requires either both reviewer declarations or neither. An absent
  review stays `REVIEWS_NOT_SUPPLIED`.
- All declarations must stay in the exposed development partition; protected
  material is not mounted or queried.
- Returned rights, family and reviewer status is **not authenticated**.
  The captured publisher URL or claimed CC license remains an operator
  declaration only. This tool makes no network requests.

The synthetic regressions are in
`tests/test_source_review_binding.py`. They cannot substitute for genuinely
independent source-context review of licensed original articles. The next
scientific evidence milestone is proper real-source capture, rights checks,
documented exposure and separate substantive adjudications — not more
agreement among agent personas.
