# Release process

ResearchWitness releases are evidence-bearing artifacts. A version bump is not complete until the packaged artifact reproduces the release gate.

## Prepare

1. Update `CHANGELOG.md`, `README.md`, `CITATION.cff`, and package version metadata.
2. Regenerate schemas / generated fixtures when their source changes.
3. Ensure validation cases contain only redistributable or synthetic text, never publisher PDFs or private evidence.

## Qualify

From a clean checkout with development dependencies installed:

```bash
python -m pytest -q
python benchmarks/run_synthetic.py
python validation/mvp_real/run_validation.py
python tools/quality_gate.py
```

`quality_gate.py` additionally checks schema drift, compilation, trusted-core forbidden primitives, deterministic wheel construction, clean offline installation, and installed-CLI smoke behavior.

## Tagging policy

- `0.x`: research-preview releases; verifier coverage is explicitly incomplete.
- `1.0`: reserved for a release whose supported scope and empirical validation justify a stable public API/protocol commitment.

Do not create a release whose notes imply general paper correctness, autonomous peer review, or author-contact authorization.
