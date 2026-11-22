# Synthetic worker threat model

Synthetic engineering code only; not custody-qualified. Protected custody
**NOT RUN**. Production is disabled pending Sami's separate security review.

Only synthetic fixtures belong in this development workflow. Source bytes,
identifiers, review records, seals and the locally generated HMAC key would be
sensitive in real use; no such use is authorized here. Never import private
sources or reserved labels.

Application controls include bounded strict JSON and ledger traversal, path/link
checks, source hashes and byte spans, operation locks, immutable writes,
relationship deduplication and sealed threshold exports. Provenance, rights,
version and scope fields remain attestations. DOI IDs do not prove independent
works. The one-line profile does not parse general tables or map PDF reviews.

The trusted interpreter, OS and quiescent filesystem remain assumptions.
This is not a sandbox against administrators, compromised tokens or parent-path
replacement races. A marked temp directory is not independent custody.
Provenance URL validation does not fetch sources or enforce network egress.
Future protected controls require separate review; they remain unproven here.
