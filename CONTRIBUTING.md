# Contributing

ResearchWitness is intentionally small. Contributions should improve deterministic verification rather than grow an orchestration framework around it.

## Core rules

A new checker must:

1. accept a precisely documented bounded input schema;
2. use deterministic operations;
3. state exactly what a positive result proves;
4. state important conclusions it does not prove;
5. reject malformed and unsupported inputs rather than guessing;
6. include positive, negative, boundary, mutation and resource-limit tests;
7. include at least one differential or independently formulated test where practical;
8. avoid network access, subprocess execution and arbitrary source-code execution in the trusted core.

Do not add a checker whose positive output depends only on an LLM judgment or on an unchecked numerical solver objective.

## Development

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python benchmarks/run_synthetic.py
```

If you change `tools/write_schema.py`, regenerate `schemas/case.schema.json` and ensure the schema tests remain green.

If you change the example generator, regenerate all synthetic examples and rerun the full suite.

## Result language

Prefer narrow machine-verifiable wording. Examples:

- good: `FORMALIZATION_COUNTEREXAMPLE_VERIFIED`;
- bad: `PAPER_FALSE`;
- good: `OLD_WITNESS_NO_LONGER_REFUTES_REVISION`;
- bad: `CORRECTION_VERIFIED`.

Never infer misconduct, intent or researcher quality from a technical discrepancy.

## External actions

The trusted core must not send email, post comments, modify a repository, publish a report, or expose an “authorize contact” flag. Integrations that perform external actions belong in separate projects with their own consent and safety boundaries.

## Tests are evidence, not scientific validation

A larger unit-test count does not establish paper-discovery precision or source-interpretation accuracy. Label synthetic and engineering evaluations accurately.


## Pull requests

Keep changes reviewable and scoped. Trusted-core changes should explain the invariant being changed, the failure mode they address, and how the new tests would fail without the patch. Update docs and historical validation metadata when semantics change.

The pull-request template lists the local verification commands expected before merge. CI repeats them on supported Python versions.

## Issues and data hygiene

Use the repository issue forms for reproducible bugs and verifier proposals. Do not upload private manuscripts, credentials, author correspondence, personal data, or private QEH evidence. Prefer synthetic reproductions or public historical cases.

Security-sensitive reports follow [`SECURITY.md`](SECURITY.md), not the public issue tracker.
