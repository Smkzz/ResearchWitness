# Synthetic-only offline custody worker

Ported from PR #12 at `78b26e2`. Synthetic engineering code only; not
custody-qualified. Protected custody **NOT RUN**. Production is disabled
pending Sami's separate security review. No historical installation or
qualification claims are carried forward.

The standard-library runtime rehearses hash-pinned source imports, exact
UTF-8 byte-span percentage reviews, verification, inventory seals and
threshold-only public summaries. It does not fetch papers, run detectors,
authenticate publications or establish independent custody. DOI counts do not
establish independent works; scope and licensing fields remain attestations.
The narrow v5 review profile requires one physical line with an explicit count
cue and complete numeric-span accounting. General tables remain unsupported.

## Synthetic engineering checks

    python -m unittest discover -s tests -p test_custody_worker.py -v
    python tools/qualify_custody_zipapp.py
    python custody_worker/build_release.py

Development dependencies supply jsonschema for tests. Pytest discovers these
unittest cases on the existing CI matrix. The zipapp builder emits its explicit
source/schema/LICENSE allowlist, manifest and sidecar under custody_worker/dist/.
The researchwitness wheel excludes this package.

Every CLI command requires --dev-root, a marked child under the system temp
directory's rw-custody-synthetic-only directory. Its .synthetic-only file must
contain RESEARCHWITNESS_SYNTHETIC_ONLY_V1 followed by a newline. Use only the
checked-in synthetic examples; the tests create roots and rehearse the workflow.
Missing --dev-root refuses before production preflight; invalid roots fail
closed without a production fallback. See the other documents in this directory.

## Bounded synthetic recovery

    python -m custody_worker --dev-root SYNTHETIC_DIRECTORY recover

Recovery holds the operation lock and validates the import ledger before deleting
anything. In objects/sha256, manifests/imports, manifests/reviews and sealed-labels,
it removes only regular, single-link files matching `.rw-tmp-[a-z0-9_]{8}` (the
mkstemp suffix). It removes unreferenced 64-hex objects only when their bounded
content hash equals their name. Referenced objects and records are never removed.
Output contains only status and removal counts, no paths or source bytes.

Import automatically performs the same recovery before indexing. On failure
before manifest commit it best-effort removes only objects newly created by that
call; a later retry/recover handles remaining valid orphans. `verify` never repairs.
The scan uses existing file/count/byte limits and refuses unknown entries, unsafe
file types, invalid manifests and object corruption without deleting candidates.
Seals commit to manifests, so removing unreferenced objects leaves seals unchanged.
Recovery is not atomic across deletions; an unlink failure may leave work for retry.
The persistent audit/.exclusive-lock uses non-blocking OS advisory locking
(POSIX flock or Windows byte-range locking). It is never unlinked. Live holders
cause STORE_LOCK_HELD_BY_LIVE_PROCESS, including nested acquisition. The kernel
releases the lock when a holder dies; a later operation safely replaces its V3
HELD marker under the acquired lock and leaves V3 RELEASED on normal exit.
Legacy V2 markers require explicit `recover` as an operator assertion that no
old-version worker is active; other commands fail with
STORE_LOCK_LEGACY_STALE_MANUAL_REVIEW_REQUIRED. Unknown markers fail with
STORE_LOCK_UNRECOGNIZED_MANUAL_REVIEW_REQUIRED and are never overwritten.
Only trusted local filesystems honoring these locks are supported; network
filesystems are unsupported. No real-root recovery is authorized.
Production remains disabled / NOT RUN / not qualified / awaiting Sami's security
review, including for the new command.
