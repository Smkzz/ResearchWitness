# Release process

ResearchWitness releases are evidence-bearing artifacts. A version bump is not complete until the packaged artifact reproduces the release gate.

## Prepare

1. Update `CHANGELOG.md`, `README.md`, `CITATION.cff`, and package version metadata.
2. Regenerate schemas / generated fixtures when their source changes.
3. Ensure validation cases contain only redistributable or synthetic text, never publisher PDFs or private evidence.

## Qualify

From a full maintainer checkout with development dependencies installed (the generated source archive intentionally excludes the test suite and most development validation files):

```bash
python -m pytest -q
python benchmarks/run_synthetic.py
python validation/mvp_real/run_validation.py
python tools/quality_gate.py
```

`quality_gate.py` additionally checks schema drift, compilation, trusted-core forbidden primitives, deterministic wheel construction, clean offline installation, and installed-CLI smoke behavior.

The application source archive and `CHECKSUMS.sha256` use the same Git-index tracked-file selection. Untracked files are omitted; symlinks, reparse points, hard links and non-regular inputs in selected paths stop packaging. Case-level evaluation/evidence records, the test suite, and custody installation/qualification materials are excluded. One reviewed aggregate-only source adjudication summary is included by an exact path allowlist; all other validation and evidence paths remain excluded. `docs/` and `tools/` use explicit reviewed path allowlists so a newly tracked owner-only note or paper-specific qualification tool cannot silently enter an artifact. Any other public aggregate or integrity commitment must be reviewed and explicitly allowlisted before release. On systems with directory-relative no-follow opens, selected file reads stay anchored to opened parent directories. The Windows fallback detects static reparse points and checks the opened leaf but does not defend against a concurrent parent-path replacement; run packaging only from a clean, single-writer checkout there. The release command regenerates the checksum manifest, then refuses to build artifacts if tracked changes remain, so commit the regenerated manifest and source first.

Artifacts are staged inside the selected output directory and moved into place only after the source archive, wheel, manifest and checksums have been built and hashed. Existing linked or non-regular destination files are rejected.

## Tagging policy

- `0.x`: research-preview releases; verifier coverage is explicitly incomplete.
- `1.0`: reserved for a release whose supported scope and empirical validation justify a stable public API/protocol commitment.

Do not create a release whose notes imply general paper correctness, autonomous peer review, or author-contact authorization.
