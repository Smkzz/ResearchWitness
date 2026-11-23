# Separate security review pending

Synthetic engineering code only; not custody-qualified. Protected custody
**NOT RUN**. Production is disabled pending Sami's separate security review.
No independent security audit or certification is claimed.

The CLI blocks all production commands before preflight. Retained Windows
identity/ACL inspection is unreachable through that CLI path. The runtime has
no network client, credential reader, publisher or account/ACL modifier.
The per-store random HMAC key is generated locally; never log or export it.
A keyed commitment is not a signature or independent-custody proof.

Review must address effective access to descendants/code/temp/logs/backups,
same-user races, output handling, host egress and source rights before any
separately authorized protected implementation is enabled. Synthetic tests
and static analysis do not substitute for that review.

Recovery validates the complete bounded import ledger and hashes objects before
deleting exact mkstemp residues or valid unreferenced objects. It refuses links,
directories, unexpected names and corrupted objects; it does not repair records.
Persistent kernel advisory locks prevent takeover of a live V3 holder and permit
recovery after its death without unlinking the lock file. Legacy V2 takeover
requires explicit `recover` and the operator's assertion that no legacy worker is
active. Unknown markers fail closed. Network filesystems are unsupported.
The trusted, quiescent-filesystem assumption still
applies; this is not a defense against same-token races or crash-durability proof.

Never delete `audit/.exclusive-lock` by hand: deleting it while a holder is live
lets a second process acquire a lock on a new inode. Stop all workers, then use
`recover`; leave unknown-content locks for manual review without deletion.

## Open items for Sami's security review

- Drop the legacy V2 takeover in `recover` (operator assertion) before production.
  An operator assertion cannot prove that no live legacy holder remains.
