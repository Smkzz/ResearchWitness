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
