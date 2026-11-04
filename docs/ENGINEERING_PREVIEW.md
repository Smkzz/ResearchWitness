# ResearchWitness 0.3.1 engineering preview

**Scope:** installable, offline, zero-runtime-dependency engineering preview.
**Publication state:** this checked-out version is a **release candidate** until
its actual distribution is created, verified and delivered. A version number,
repository branch or successful CI job is not itself a GitHub Release or PyPI
publication. Python 3.11–3.13 is the tested runtime range; later Python versions
are not yet qualified.

## Installation

Obtain the wheel and its separately retained SHA-256 from the same release
record. Confirm the digest **before** using the wheel. The public build
contains no licensed scientific full texts, unpublished correspondence, user
credentials or private evidence bundles.

On macOS / Linux:

```text
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-index --no-deps researchwitness-0.3.1-py3-none-any.whl
python -m researchwitness --version
```

On Windows PowerShell:

```text
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --no-index --no-deps researchwitness-0.3.1-py3-none-any.whl
python -m researchwitness --version
```

A local wheel is supplied; `--no-index --no-deps` prevents package-index access.
It does **not** download Python, pip, or the wheel. No background service,
Docker, GPU or online account is required to verify supported cases.

## First run without any scientific source files

```text
python -m researchwitness demo --output first-demo
```

This creates `first-demo/intake/` and `first-demo/bundle/`, then writes
`first-demo/demo-result.json`. The result includes an explicit **synthetic**
source label, a formally verified counterexample, a bundle digest and
`paper_error_established: false`. The contact gate returns `NOT_READY`.
This is a test of software execution, not an allegation against a paper.

To verify the same evidence with an independently retained digest:

```text
python -m researchwitness verify first-demo/bundle --as-of 2026-10-04 --expected-bundle-sha256 DIGEST_FROM_DEMO_RESULT
```

The directory must be fresh. The demonstration refuses to overwrite existing
files and makes no network call. It creates only synthetic examples using
installed package data. It does not contact any author or authenticate a source.

## Supported installed workflows

| Capability | Supported scope |
|---|---|
| `researchwitness capabilities --json` | List ten bounded deterministic verifier families, with limits |
| `researchwitness scaffold`, `validate-intake`, `audit`, `verify` | Agent/investigator-provided formalization, deterministic proof and evidence bundle |
| `researchwitness report`, `pack`, `timeline` | Escaped offline report, curated private ZIP and version-bound history |
| `researchwitness audit-jats`, `replay-jats` | Offline JATS count/percentage review and explicitly enabled narrow source-mapped checks; unreviewed arithmetic candidates |
| `python -m researchwitness.exact_optimization` | Exact rational upper-bound certificates for bounded linear/bilinear models |
| `python -m researchwitness.source_claim_workflow` | Strictly marked UTF-8 mathematical claims, exact source→model replay and formal counterexamples |
| `python -m researchwitness.prose_math`, `.prose_attribution` | Conservative literal-sentence checks and self-declared context; no author-intent authentication |

Use the source's actual copyright/redistribution terms; do not treat a file
hash as independent provenance authentication. Raw sources, local reports and
witnesses can contain confidential research. Store bundles privately and share
only after an explicit content/licence review.

## Source-only optional PMC original-envelope pilot

The 0.3.1 **source ZIP** includes `tools/pmc_oai_jats_pilot.py` and
its tests. This is intentionally **not installed into the Python wheel**:
it imports checkout-only `tools` modules and must run from an extracted
0.3.1 source checkout on genuine, permission-cleared, separately retained
original PMC OAI-PMH bytes. The script makes no network request. See
[the exact OAI/JATS protocol](PMC_OAI_JATS_ONE_SHOT.md). No real original
PMC11845954 response has been acquired or scientifically adjudicated.

## Unsupported / unqualified

- Automatically interpreting arbitrary journal PDFs or proving every paper.
- Certifying experimental conclusions, publisher/source authenticity, or real
  paper errors from a formal mathematical counterexample alone.
- Reporting general accuracy, precision/recall or independent researcher validation.
- Running protected source-custody workloads, unqualified PDF execution or
  external author contact; the installed core makes no network requests.
- Reconstructing the historically unavailable 13 Europe PMC original XML files
  or actual original PMC OAI-PMH transfer envelopes. The corresponding real-paper
  study and scientific qualification remain blocked.

For the state of those dependencies, see [project status](PROJECT_STATUS.md),
[scientific study readiness](../validation/SCIENTIFIC_EVALUATION_READINESS.md),
[original source recovery](HISTORICAL_SOURCE_RECOVERY.md) and
[PMC acquisition protocol](PMC_PILOT_LEDGER.md). The available software preview
is distinct from the unfinished ResearchWitness *research evaluation*.

## Reproducibility and support boundaries

Development acceptance uses the committed source archive allowlist and SHA-256
manifest, GitHub Actions 3 OS × 3 Python matrix, CodeQL, synthetic conformance,
historical MVP replays, deterministic wheels and clean offline wheel install.
Do not reuse a successful CI receipt for later changed code without a new run.

When reporting a suspected defect, include the version/commit, declared proof
kind and sanitized status/error code. Never attach confidential manuscripts,
patient data, credentials, unlicensed full text or protected review labels.
See [security and trust boundaries](../SECURITY.md) and [release process](RELEASING.md).
