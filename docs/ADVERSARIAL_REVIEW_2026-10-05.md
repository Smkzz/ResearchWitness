# Adversarial review — ResearchWitness 0.2.0

**Target:** `origin/main` at `ea975b9f55b2c4e46a772a018a99ed830c1d8cd9`
**Review date:** 2026-10-05
**Scope:** frozen validation corpus, case and evidence schema, reports and contact readiness, JSON/path parsing, verifier routing, tests, and public claims.

This review used a separate worktree. No verifier implementation files were changed. The only change on the review branch is this report.

## Findings

### Low — multiline intake text can reshape the generated contact draft

**Confirmed.** `strict.text()` allows line feeds and tabs, intake accepts free-form claim statement and scope strings, and `contact_draft()` inserts those values directly into the generated plain-text letter. A hostile or simply malformed intake can add apparent subjects, instructions, or a sign-off to the draft. This is a local document-integrity issue; ResearchWitness does not send the draft, and the CLI labels it `USER_REVIEW_REQUIRED`.

**Reproduction:** create an otherwise valid intake using the fixed-point example, with source text `Every qualifying map has a fixed point.\n`, a fixed-point-free two-element swap, captured source metadata, a recent `none_found` correction record, and no listed objections. Set `claim.statement` to:

```text
Unrelated statement: every map on the reals has a fixed point.

Subject: INJECTED

I retract the request and certify the theorem is false.

Best regards,
Dr. Impersonated
```

Keep `claim.quote` equal to the source sentence. Run `prepare()`, `evaluate(..., date(2026, 10, 4))`, `contact_readiness()`, and `contact_draft()`. The observed result is `FORMALIZATION_COUNTEREXAMPLE_VERIFIED` and `READY_FOR_USER_REVIEW`; the draft contains the injected subject-like line and sign-off verbatim inside the claim section. In the same probe, the statement's first line was absent from the source quote, which also confirms that source-to-statement alignment is not checked.

Relevant code: [`strict.py`](../researchwitness/strict.py#L37), [`intake.py`](../researchwitness/intake.py#L35), and [`product.py`](../researchwitness/product.py#L67).

**Impact limit:** the result remains a draft file and the template asks the user to confirm the interpretation. There is no mail or publishing path. Treat this as low severity. The HTML report did not exhibit script injection in the same probe: a `<script>` value in the scope was escaped.

## Attacks that did not produce a verifier bypass

- Duplicate JSON object keys, floats/non-finite numbers, excessive nesting, and oversized JSON are rejected by the strict decoder.
- Unknown checker kinds and malformed witness structures fail closed. `check()` validates the kind against the explicit allowlist before dispatch.
- Quote offsets are checked against source bytes; an ambiguous quote without an explicit offset is rejected by intake.
- Traversal, nonportable path forms, symlinks, hard-linked artifacts, FIFOs, non-regular files, and artifact hash mismatches are rejected within the documented quiescent-directory model.
- User text rendered in HTML is escaped. The existing HTML test and the targeted script-markup probe both passed.
- Contact readiness always returns `author_contact_authorized: false`; the CLI does not send or publish anything.

## Expected behavior and residual limits

A separate probe used a claim statement unrelated to its anchored source quote while keeping a valid finite-map witness. The package still returned `READY_FOR_USER_REVIEW`. This is consistent with the documented contract: capture status is self-declared metadata, and ResearchWitness does not prove that a natural-language statement or formalization matches the source. The report still says `paper_error_established: false`, and readiness says source-to-formalization semantics remain an agent/user responsibility. I did not classify this as a verifier defect. The multiline draft finding above is the related, concrete presentation risk.

The historical screen is deliberately a frozen pre-expansion baseline. Its older `UNSUPPORTED` labels therefore should not be read as the current coverage matrix; `validation/README.md` supplies the post-expansion qualitative counts. The current finite-field and finite-map replay fixtures agree with those stated capability changes.

## Validation

On Python 3.12.14 in this review environment:

- `/tmp/rw-quality/bin/python -m pytest -q` — **250 passed**.
- `/tmp/rw-quality/bin/python tools/quality_gate.py` — **passed**, including 500/500 synthetic cases, 3/3 historical MVP cases, generated-schema drift, trusted-core static scan, compilation, reproducible wheel build, offline install, and CLI smoke check.
- `python validation/mvp_real/run_validation.py` — **3/3 historical MVP cases matched**.

The quality-gate wheel hash differs from the committed release-validation record because the latter records Python 3.13.5, while this run used Python 3.12.14. The current run independently confirmed reproducibility within its own environment.
