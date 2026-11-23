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
unsafe file types, scan limits, stale-lock refusal and unchanged records/seals.
These are synthetic engineering checks, not real process-kill or durability proof.
Explicit `recover` and automatic import recovery do not clear stale locks or
repair corrupt ledgers/objects; those still require manual review. Production
remains disabled, not qualified, and protected custody NOT RUN pending Sami's
separate security review.
