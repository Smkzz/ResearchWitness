# Release process

A merge, an engineering assessment and a package release are separate events.
`0.3.0.dev0` is on main but remains UNRELEASED. A version bump alone is not
qualification. Follow the [scientific release gate](ROADMAP.md#release-gate)
as well as this engineering procedure; publication needs separate owner approval.

## Environment

Use a real, clean Git checkout with Git on PATH and a supported Python version.
An extracted source ZIP can run the software, but lacks the Git index required
by `tools.make_release` to select or regenerate release files.

Create and activate an isolated virtual environment. On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

From the repository root, install the declared build backend explicitly, then
the development extra:

```text
python -m pip install 'setuptools>=68'
python -m pip install -e '.[dev]'
```

The gate calls `pip wheel --no-build-isolation`; an editable installation with
build isolation does not guarantee that setuptools exists in the active
runtime environment. The development extra supplies pytest, jsonschema,
coverage and Ruff. Network access is needed for this setup unless the required
packages are already provisioned through an approved local package source.
The subsequent offline gate does not fetch dependencies.

## Prepare and regenerate the manifest

1. Update the changelog, README, citation and package version metadata only when
   their meaning changes. Regenerate any affected schemas or synthetic fixtures.
2. Review intended source changes and redistribution rights. Never stage private
   manuscripts, credentials, author correspondence or reserved evaluation data.
3. Stage the **specific intended paths** with `git add -- PATH...`; replace the
   placeholder with actual reviewed filenames. Do not blindly use `git add .`.
4. Regenerate and stage the existing tracked checksum manifest:

```text
python -c "from tools.make_release import write_checksums; write_checksums()"
git add -- CHECKSUMS.sha256
git diff --cached --check
git diff --cached --stat
```

The approved selector uses Git-indexed, allowlisted paths. It refuses unstaged
changes to selected files, unmerged entries, symbolic links, unsafe portable
names and collisions. Caches, ignored/untracked files and local artifacts are
not release inputs. `CHECKSUMS.sha256` is already tracked even though its name
also appears in `.gitignore`; do not remove it from the inventory to pass checks.

## Qualify

Run the same local checks that support the hosted gates:

```text
python -m ruff check .
python -m coverage run -m pytest -q
python -m coverage report
python -m coverage report --include='researchwitness/*.py' --fail-under=90
python benchmarks/run_synthetic.py
python validation/mvp_real/run_validation.py
python tools/quality_gate.py
```

The last command checks source hashes, schema drift, trusted-core primitives,
compilation, synthetic conformance, historical MVP replay, two wheel builds in
one environment, clean offline wheel installation and installed-CLI behavior.
Tests include source-ZIP reproducibility and documentation examples. Source-tool
coverage remains visible separately from the core threshold. Inspect any skips;
POSIX-only tests are intentionally skipped on Windows, not silently passed.

Commit only the reviewed source and regenerated manifest. Push a PR and require
all nine `Python 3.11–3.13 / ubuntu-latest, windows-latest, macos-latest` checks,
`Release gate` and CodeQL `Analyze Python` at the **exact proposed commit**.
Also inspect the PR's `Dependency evidence` run and its dated advisory/license
results. That job needs approved network access; it is not part of the offline
gate. An unavailable advisory query is not proof of zero vulnerabilities.

If any source change follows validation, repeat affected checks and qualify the
new exact commit. Never bypass the protected main ruleset, weaken tests or
change scientific labels to obtain a pass. After merging, verify the new main
CI and CodeQL; PR success alone is not post-merge evidence.

## Build review artifacts

With intended changes staged and a consistent manifest, use a **fresh output
directory outside the source checkout**:

```text
python tools/make_release.py --output-dir ../researchwitness-review-artifacts
```

Review source ZIP and wheel inventories, sizes and SHA-256 values. The builder
creates review artifacts; running it is not permission to upload a release.
Reproducibility comparisons apply to the recorded build environment. Do not
claim byte-identical wheels across different toolchains without testing that.

## Tagging policy

- `0.x`: research-preview releases with explicit scope and incomplete coverage.
- `1.0`: reserved for justified stable public API/protocol and empirical scope.

Never describe a release as certifying arbitrary papers, autonomous peer review,
author-contact authority or independent human approval. PDF/custody qualifications
and scientific evaluation remain distinct from engineering acceptance.
