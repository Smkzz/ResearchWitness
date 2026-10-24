# Contributing

Start with [AGENTS.md](AGENTS.md), the [development plan](docs/DEVELOPMENT_PLAN.md)
and [execution state](docs/EXECUTION_STATE.json). Autonomous agents make ordinary
implementation/review/merge decisions without routine owner approval. New safety
permissions or actual unauthorized spending remain escalation points.

ResearchWitness keeps deterministic verification small. Reuse the existing
paper-audit stack; do not grow an orchestration framework inside the verifier.

## Core rules

A new checker must have a precise bounded schema, deterministic operations,
explicit proof scope and exclusions, fail-closed unsupported input, and positive,
negative, boundary, mutation/resource tests. Include differential or independently
formulated checks where practical. No network, model vote, unchecked solver result,
subprocess or arbitrary source-code execution belongs in the trusted core.

## Development

Use a real Git checkout with Git on PATH and an isolated environment. Install the
build backend explicitly for the later offline gate:

```text
python -m pip install 'setuptools>=68'
python -m pip install -e '.[dev]'
python -m ruff check .
python -m coverage run -m pytest -q
python -m coverage report
python -m coverage report --include='researchwitness/*.py' --fail-under=90
python benchmarks/run_synthetic.py
python validation/mvp_real/run_validation.py
python tools/quality_gate.py
```

The full repository coverage remains visible; the deterministic package has a 90%
combined statement/branch floor. Do not lower it or exclude failing tests to pass.
Use focused checks while editing and the mandatory exact-head gates when ready,
not repeated identical runs to increase a test count. Record actual skips/limits.

Regenerate affected schemas and examples using their existing generators. Keep
root and packaged schemas aligned. Stage only reviewed paths and regenerate
checksums using [RELEASING.md](docs/RELEASING.md). Never stage caches/private data.

## Parallel work and review

One coordinator owns the execution ledger; each package has one owner and separate
branch/worktree. Preserve other agents' work and reconcile current main before a
write. A separate AI review is accepted; disclose its modality and missing review
rather than implying human independence. No blind stack merge or force-push.

A PR records its package, actual defect/deliverable, changed contracts, exact test
results and limits. Explain how a regression test would fail without the fix.
Required checks must pass at the proposed head, then verify main after merge.
Routine qualified merges have standing authority; do not ask "may I continue?".

## Result language and scientific evidence

Prefer `FORMALIZATION_COUNTEREXAMPLE_VERIFIED`, not `PAPER_FALSE`;
`OLD_WITNESS_NO_LONGER_REFUTES_REVISION`, not `CORRECTION_VERIFIED`.
Do not infer misconduct, intent or researcher quality. Tests are engineering
evidence, not paper-discovery precision or source-interpretation accuracy.

Update current docs and append new evidence when semantics change. Do **not**
rewrite frozen historical validation, source hashes, labels or exposure records.
Keep the plan, current capability descriptions and machine-readable task state
consistent. New experiments need their own identities and declared limitations.

## External actions and private data

The core must not send email, post comments, modify repositories, publish reports
or expose a contact-authorization flag. Repository-development agents may use
GitHub within the owner's task authority; that does not give the runtime verifier
external-action powers. Author-contact integrations are outside this plan.

Do not upload private manuscripts, credentials, correspondence, protected labels
or private QEH evidence. Use synthetic reproducers or cleared public evidence.
Security-sensitive material follows [SECURITY.md](SECURITY.md), not public issues.
