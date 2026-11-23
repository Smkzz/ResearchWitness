# Synthetic engineering checks, not custody qualification

Not custody-qualified; protected custody **NOT RUN**. Production is disabled
pending Sami's separate security review. No historical results, artifact hashes,
installation receipts or protected-run claims are imported.

The unittest suite uses synthetic text and marked temporary roots. The existing
pytest CI matrix discovers these tests. The offline zipapp check builds two
clean copies, compares bytes and manifests, exercises the synthetic CLI and
checks below-threshold export refusal. These are synthetic engineering checks,
not OS isolation, effective Windows access separation, egress enforcement,
escape-resistance evidence or scientific performance measurements.

Run README.md's commands and ../RELEASING.md's release checks. Record exact-head
results separately. Platform skips remain evidence gaps; synthetic success does
not authorize protected material or qualify custody.

Recovery regressions cover injected manifest-write failure and retry, hash-valid
orphans, interrupted-write temporaries, corrupt imports, bad object hashes,
unsafe file types, scan limits and unchanged records/seals.
These are synthetic engineering checks, not power-loss or storage-durability proof.
Lock regressions use real subprocess holders and forced termination to exercise
live-holder refusal and V3 recovery after death, plus nested acquisition, explicit
legacy V2 takeover, invalid lock rejection and persistent RELEASED markers.
Never delete `audit/.exclusive-lock` by hand: deleting it while a holder is live
lets a second process acquire a lock on a new inode. Stop all workers, then use
`recover`; leave unknown-content locks for manual review without deletion.
These are synthetic engineering tests, not production qualification. Advisory
locks require a trusted local filesystem; network filesystems are unsupported.
Recovery does not repair corrupt ledgers/objects; those require manual review. Production
remains disabled, not qualified, and protected custody NOT RUN pending Sami's
separate security review.
