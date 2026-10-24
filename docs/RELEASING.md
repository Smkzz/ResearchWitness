# Release process

A merge, an engineering preview and a scientific-performance claim are separate.
The observed version `0.3.0.dev0` remains UNRELEASED. A version bump is not
qualification. Follow [AGENTS.md](../AGENTS.md) and the
[release gate](ROADMAP.md#release-gate).

## Authority and release scope

Routine safe, zero-incremental-cost merges and honestly scoped engineering-preview
releases have standing owner authorization under `RW-PLAN-2026-10-24`; no additional
human opinion or ceremonial signoff is needed. New billing/paid credits, expanded
credentials/permissions or sensitive disclosure require the relevant safety/cost
decision. Do not create a publishing credential or widen its scope silently.

An engineering preview may disclose that independent scientific accuracy is not
established. A release claiming measured research improvement additionally needs
its frozen protocol/evaluation gates. Disabled PDF/custody capabilities stay disabled
and documented. Lack of evidence is not repaired by owner or model confidence.

## Environment

Use a real, clean Git checkout with Git on PATH and a supported Python version.
A source ZIP can run the software but lacks the Git index needed by the release
selector. Create and activate an isolated environment:

```text
python -m venv .venv
```

On macOS/Linux use `source .venv/bin/activate`; on Windows PowerShell use
`.venv\Scripts\Activate.ps1`. From the repository root install:

```text
python -m pip install 'setuptools>=68'
python -m pip install -e '.[dev]'
```

The gate calls `pip wheel --no-build-isolation`; an editable build does not prove
setuptools is installed in the active environment. Setup needs already provisioned
packages or an approved package route. It does not authorize paid infrastructure.
The later offline gate fetches no dependencies.

## Prepare and regenerate the manifest

1. Update current docs, changelog, package/citation metadata and affected generated
   schemas/examples when their meaning changes. Keep frozen evidence unchanged.
2. Review exact intended paths and redistribution rights; exclude secrets, private
   source/correspondence, reserved data, caches and unrelated agent work.
3. Stage reviewed paths with `git add -- PATH...`, replacing the placeholder with
   actual paths. Never use blanket staging to collect a workspace.
4. Regenerate and stage the tracked manifest:

```text
python -c "from tools.make_release import write_checksums; write_checksums()"
git add -- CHECKSUMS.sha256
git diff --cached --check
git diff --cached --stat
```

The allowlisted Git-index selector rejects selected unstaged changes, unresolved
entries, links, unsafe portable names and collisions. Root agent entry points are
part of the source inventory, as are docs and provider pointers. Untracked/ignored
files are not release inputs. Do not remove CHECKSUMS.sha256 to make a gate pass.

## Qualify

Use focused regressions during editing, then the final gates:

```text
python -m ruff check .
python -m coverage run -m pytest -q
python -m coverage report
python -m coverage report --include='researchwitness/*.py' --fail-under=90
python benchmarks/run_synthetic.py
python validation/mvp_real/run_validation.py
python tools/quality_gate.py
```

The quality gate checks source hashes, schema drift, trusted-core primitives,
compilation, synthetic conformance, historical replay, repeat wheel builds,
clean offline installation and installed CLI behavior. Source ZIP reproducibility
and documentation contracts are tested. Inspect platform-specific skips; do not
count a skipped boundary test as real qualification.

Commit one coherent reviewed change and manifest. A PR requires the nine
`Python 3.11–3.13 / ubuntu-latest, windows-latest, macos-latest` checks,
`Release gate` and CodeQL `Analyze Python` at the exact proposed commit. Inspect
`Dependency evidence` and its dated advisory/license results too; unavailable
advisory data is not evidence of no vulnerabilities. Use only authorized CI with
known zero incremental cost or an explicit project spending authorization.

Do not rerun identical successes without a reason. After source changes, qualify
the new exact head. Preserve main protection and all scientific/security boundaries.
After merging, inspect the new main CI and CodeQL. The PR success is not itself
post-merge evidence. Record the exact commits, checks and limitations in the receipt.

## Build and publish scoped artifacts

With staged intended files and a consistent manifest, use a fresh external directory:

```text
python tools/make_release.py --output-dir ../researchwitness-review-artifacts
```

Review source ZIP/wheel inventories, sizes and hashes. The builder does not upload
anything. Compare two builds within the recorded toolchain; do not claim identical
bytes across untested environments. Test installed workflows outside the checkout.

Publish only through an already authorized safe zero-cost release route, with an
exact tag/commit, changelog, checksums, known limitations and reproducibility steps.
If permissions or billing are unknown, leave verified artifacts and record the
specific blocker instead of expanding authority. No author/case accusation is
included in a software release. Do not bundle private custody or licensed full text.

## Tagging policy

- `0.x`: bounded research/engineering previews with explicit incomplete coverage.
- `1.0`: requires justified stable API/protocol and documented empirical scope.

The plan revision and informal "v4" vision are not package versions. Preserve
protocol compatibility or explicitly version breaking changes. A scientific result
may be negative or inconclusive; release wording must reflect it without suggesting
arbitrary-paper certification, human approval or automatic contact authority.
