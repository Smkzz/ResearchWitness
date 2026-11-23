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

Locked recovery removes only exact mkstemp regular files and hash-valid orphan
objects after bounded import-ledger validation. Referenced objects and manifest
records remain untouched; seals bind those manifests, not orphan presence.
Import rollback is best-effort and touches only that call's new objects before
manifest commit. Deletion is not an atomic transaction and may need retry after
an I/O error. Persistent OS advisory locks are released by the kernel on holder
death; no PID probing or lock-file deletion is used. Live V3 holders cannot be
taken over. Explicit legacy V2 recovery asserts no old-version worker is active;
the OS lock cannot prove this for the old protocol. Unknown lock markers,
corruption and over-limit inventories remain manual-review failures. Network
filesystems are unsupported because advisory locking may not be honored. These
synthetic checks do not enable production or establish custody qualification.
