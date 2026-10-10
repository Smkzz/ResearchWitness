# ResearchWitness offline custody worker v5

**Status: synthetic development qualification only. Do not install or use this package with reserved material.**

The worker stores offline, source-bound percentage reviews for a separate custodian. It does not retrieve papers, run ResearchWitness, decide scientific scope, authenticate publications, or enforce network isolation.

## What v5 checks

- An import manifest pins each file's SHA-256 and byte length, a canonical article DOI, source identifier, version, role, approved-host URL, UTC acquisition time, license notice, and custodian public-use status. Real-source provenance is accepted only in production mode; synthetic mode rejects it. A hash-pinned handoff is rechecked against imported bytes; it is not an external signature.
- Eligible reviews bind count, explicit N denominator, displayed percentage, table/object locator, context, and scope text to exact UTF-8 byte spans in the imported source. The v5 eligibility profile is intentionally narrow: the complete relation and its context must be one exact physical line; the table locator must be explicit and must not overlap any relation value; a literal `count` field label must immediately precede the numerator; object/scope labels may not contain digits or percent signs; and every numeric character on that line must be covered by the selected operands, table locator, or correction old-value spans. Cross-line header-to-cell joins and ambiguous rows remain unresolved.
- The percentage is recomputed independently with decimal arithmetic and declared precision.
- A correction-positive review requires an original arithmetic mismatch, a correction for the same article family, byte-bound old and corrected values, an exact list of all changed relation fields, and a corrected arithmetic match.
- Version, scope, and correction mapping are stored as custodian attestations. The software does not authenticate those judgments.
- Each review records the active custodian account name and UTC recording time. This is an audit field, not a trusted timestamp or proof of which human performed the review.
- Equal normalized numeric relationships are collapsed conservatively per DOI document, even across selected context, locator, scope, source-version, and precision differences. This can undercount separate valid rows. PDF bytes can be imported as opaque source evidence, but the worker cannot create byte-mapped PDF reviews.
- Store reads and writes are serialized. Verify is read-only and fails on missing/corrupt source objects. Inventory traversal and aggregate storage are bounded.
- A keyed HMAC commitment protects the inventory commitment from simple membership guessing. It is not a signature or proof of independent custody.
- Public export requires a sealed inventory and count thresholds. It exposes only threshold buckets and a keyed commitment. Its `distinct_negative_document_ids` count is based on custodian-supplied canonical DOI keys; it does not resolve DOI aliases or independently establish 15 distinct works and therefore cannot alone satisfy the frozen independent-document gate. One export is allowed per store snapshot; a changed snapshot requires owner review and cannot be exported through the same store.

## Synthetic qualification

From the repository root:

    TMPDIR=/tmp/rw-custody-test-root python -m unittest discover -s tests -p 'test_custody_worker.py' -v
    python -m py_compile custody_worker/*.py

Tests use synthetic strings and temporary roots marked under the system temporary directory. They do not access the production store or fetch research sources. The tests require jsonschema from the project's development dependencies; the worker runtime itself uses the Python standard library.

Build the explicit source allowlist after the tests pass:

    python custody_worker/build_release.py

The allowlist contains the worker modules, current schemas, and project LICENSE; it excludes tests, fixtures, caches, papers, and private records. The builder writes custody_worker/dist/rw-custody-0.5.0.dev0.pyz and a checksum file. It does not read the custody store, network, or external services. Inspect the manifest and archive members before any controlled handoff.

A synthetic CLI run must use a marked child under the system temp directory. Initialize the store before importing:

    python -I -S custody_worker/dist/rw-custody-0.5.0.dev0.pyz --dev-root /tmp/rw-custody-synthetic-only/example doctor
    python -I -S custody_worker/dist/rw-custody-0.5.0.dev0.pyz --dev-root /tmp/rw-custody-synthetic-only/example init

Copy only the checked-in synthetic example files into that root's incoming directory, then use import, record-review, verify, seal, summary, and export-summary. The checked-in tests perform this end-to-end flow. export-summary intentionally fails until all minimum thresholds are met.

## Production and acquisition boundary

Production mode is hard-coded to the custodian identity and configured root, with an ACL preflight. That application check covers the root DACL only; it does not prove descendant, code, temporary-file, backup, runner, or network isolation. Production preflight has not been exercised in this integration environment.

There are no network calls in the worker. That does not block other processes or enforce the approved host allowlist. Source acquisition must occur through a separately controlled custodian route that enforces the approved host policy and records provenance. Hash-pinned offline handoff is also acceptable inside that isolated route.

The v5 review, v4 review-record, v3 summary/seal, and v2 public-export contracts are versioned separately from historical artifacts; no migration command exists. Keep the installed v1 worker and its records intact. Do not point this development artifact at the existing production store.

See DEPLOYMENT.md, QUALIFICATION.md, SECURITY_REVIEW.md, and THREAT_MODEL.md for the current qualification and blockers.
