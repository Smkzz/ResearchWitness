# ResearchWitness

[![CI](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml)

**Open-source research verification with reproducible, source-linked evidence.**

ResearchWitness aims to make independent checking of scientific claims easier.
The installed core verifies narrowly defined claims after an investigator or
research agent supplies a formalization and a possible counterexample. Separate
source-checkout tools extract supported count/percentage relationships from JATS
XML and produce arithmetic candidates or explicit abstentions.

It does **not** autonomously fact-check an arbitrary paper, authenticate publisher
origin, establish misconduct, or certify a paper's conclusions.

**On main:** `0.3.0.dev0` · **UNRELEASED** · Python 3.11+ · CI tests Python
3.11–3.13 on Ubuntu, Windows and macOS · installed runtime dependencies: none · Apache-2.0.

## Status

PR [#13](https://github.com/Smkzz/ResearchWitness/pull/13) merged into `main` on
2026-10-16. Its post-merge CI and CodeQL passed. Merging is not a package release:
no PyPI publication or tagged GitHub Release is claimed for `0.3.0.dev0`.

The owner's internal ten-category engineering assessment accepts the disclosed
AI-assisted technical review. It is not an independent human audit, external
security certification, or scientific-performance evaluation. See
[project status](docs/PROJECT_STATUS.md) for the pinned merge/check identities,
[current engineering assessment](docs/OSS_QUALITY_FINAL.md) and
[roadmap](docs/ROADMAP.md) for pending research and integration work.

Real PDF extraction and Windows managed metadata discovery remain unavailable
until their documented isolation/ownership requirements are qualified. Sealed
holdout evaluation and scientific Wave 3 have not run. The separate PR #6–#12
paper-audit/custody stack is **not included** in the merged PR #13 implementation.

## What we are building

The long-term workflow is: paper → identify checkable claims → investigate
possible discrepancies → verify supported findings → return reproducible evidence
and uncertainty. Candidate discovery and deterministic verification are different
jobs. ResearchWitness keeps them separate rather than treating an AI opinion as
proof.

## Current MVP loop

```text
paper and source material
    -> investigator / research agent: claim, assumptions, proposed witness
    -> structured intake with source anchors
    -> deterministic verification and immutable evidence bundle
    -> JSON report, optional HTML report and reproducible private ZIP
```

A separate source-checkout path scans supported JATS tables for arithmetic
relationships. Neither path sends email or publishes findings. The installed
core can prepare a conservative inquiry draft; sending always remains outside
this software.

## Why this split exists

A result such as `FORMALIZATION_COUNTEREXAMPLE_VERIFIED` proves something about
the supplied formalization and witness. `paper_error_established` still remains
`false`: source authenticity, interpretation, assumptions and scientific impact
are separate questions. An unsupported input is rejected or leads to abstention,
not a guessed positive conclusion.

## Quick start

Install from a source checkout; this candidate is not advertised as available on
PyPI. You need Python 3.11+ and Git on PATH. From your chosen working directory:

```text
git clone https://github.com/Smkzz/ResearchWitness.git
cd ResearchWitness
python -m venv .venv
```

Activate on macOS/Linux with `source .venv/bin/activate`, or on Windows PowerShell
with `.venv\Scripts\Activate.ps1`. Then install the core:

```text
python -m pip install .
python -m researchwitness --version
python -m researchwitness capabilities --json
python -m researchwitness schema intake
```

Run this **synthetic** example from the repository root. The single-line command
works in Bash and PowerShell:

<!-- docs-smoke: core -->
```text
python -m researchwitness verify examples/counterexample --as-of 2026-10-04
```

Expected: exit 0, `decision: FORMALIZATION_COUNTEREXAMPLE_VERIFIED`, and
`paper_error_established: false`. The fixed date makes this fixture repeatable;
it is not the capture date for a new real research case.

### Exit codes and result interpretation

Exit 0 means the requested evaluation completed, **not** that an error was found.
For example, `NO_REFUTATION_AT_WITNESS` is a valid completed evaluation.
`validate-intake` can return `valid: true` with that `witness_status`. Inspect
`decision` or `witness_status`, the source/provenance fields and contact readiness
separately. Malformed core input normally exits 2 with `decision: INVALID` on
stderr; argument errors also exit 2 and may instead show argparse usage.

For JATS/PDF source audits, exit 0 means processing completed; inspect the counts,
findings and abstentions. Unsupported/failed extraction exits 2. The comparison
command with `--require-no-regression` exits 3 when its development gate fails.
None of these codes establishes scientific truth or author-contact authority.

### Create and inspect an intake

```text
python -m researchwitness scaffold finite_map_fixed_point --output work/fixed-point
python -m researchwitness validate-intake work/fixed-point/audit.json
```

Use a fresh output directory. The scaffold is synthetic, with an unchecked
correction search and an unresolved objection. Do not relabel it as real evidence.
To create and replay a bundle from this scaffold:

```text
python -m researchwitness audit work/fixed-point/audit.json --output work/fixed-point-bundle --as-of 2026-10-04
python -m researchwitness verify work/fixed-point-bundle --as-of 2026-10-04
```

The bundle can be inspected and replayed independently. The `audit` workflow
checks declared source/correction files, quote anchors, witness semantics and
hashes. It does not independently authenticate where the source came from.

### Reports and evidence export

Use a new output filename for the deterministic private ZIP; report/draft output
paths should be chosen deliberately and their parent directories must exist.

```text
python -m researchwitness report work/fixed-point-bundle --as-of 2026-10-04 --output work/fixed-point-report.html
python -m researchwitness pack work/fixed-point-bundle --as-of 2026-10-04 --output work/fixed-point-evidence.zip
```

`contact-draft` is available only when conservative readiness checks pass. The
synthetic scaffold above intentionally remains `NOT_READY`. Do not remove its
objections to present it as a research finding. With a genuinely eligible bundle,
`python -m researchwitness contact-draft BUNDLE --as-of YYYY-MM-DD --output inquiry.txt`
writes a draft requiring user review; it never sends mail.

## Agent intake format

A research agent supplies `audit.json` beside the referenced source files.
The complete schemas are available through `python -m researchwitness schema intake`
and [schemas/intake.schema.json](schemas/intake.schema.json). The intake records
source identifier/version, capture assertion, correction-search evidence, one
atomic claim, assumptions, exclusions, exact quote, formalization, witness and
unresolved objections. See [the agent protocol](prompts/AGENT_PROTOCOL.md).

If a quote occurs more than once, provide `quote_offset`: a **zero-based byte
offset into the original supplied source bytes**, matching the UTF-8 encoded
quote. It is not a character offset; a multibyte prefix changes the relationship
between the two. ResearchWitness does not silently choose a repeated occurrence.

## Deterministic verifier plugins

`capabilities --json` describes ten bounded checker families and their exact
input contracts, limits, proof scope and synthetic replay examples:

| Family | What the supplied witness can establish |
|---|---|
| Scalar/radical comparison | Exact rational comparison with certified square-root enclosures. |
| Polynomial upper-bound witness | Evaluation of a polynomial at a supplied bounded-domain point. |
| Rational-expression upper-bound witness | Exact evaluation of a closed rational AST at one point, not a global inequality. |
| Binary UC functional | The QEH-derived finite independent-source regression check. |
| Finite-field polynomial solution-count residue | Exhaustive enumeration under an explicit hard work budget. |
| Quadratic/quartic residue rule | Parameter residue classification and the associated point-count check. |
| Finite self-map fixed-point conclusion | Whether the explicit finite map has a fixed point; theorem premises remain separate. |
| Finite graph chromatic lower bound | A supplied proper coloring refutes a larger claimed lower bound; no optimal-coloring search. |
| Finite PMF bound | Exact event probability or expectation of a supplied finite distribution, not population inference. |
| Modular linear-system certificate | A supplied solution or left-annihilator certificate over the encoded modular system. |

The graph checker supports 1–256 vertices and up to 8,192 edges. Rational-expression
syntax and budgets are in [EXPRESSION_DSL.md](docs/EXPRESSION_DSL.md). Every family
has a replayable [synthetic example](examples/). Unsupported mathematics is not
approximated into a misleading scalar check.

## Source-checkout research-audit tools

The wheel installs `researchwitness`, not `tools/`. From the **repository root**,
in the activated environment, install the optional development dependencies:

```text
python -m pip install -e '.[dev]'
```

These include `jsonschema` for the source-tool contracts. A core-only
`python -m pip install .` is not sufficient for this workflow. Source-tool
commands below remain outside the trusted verifier core.

### Offline JATS audit

Try the bundled invented fixture without retrieving any real paper:

<!-- docs-smoke: jats -->
```text
python -m tools.research_audit audit examples/synthetic-jats/article.xml --document-id synthetic-jats --format jats --json-output out/synthetic-jats/audit.json --markdown-output out/synthetic-jats/audit.md
```

Expected: two tables, three relationships, **one arithmetic match, one mismatch
candidate and one abstention**. `4/50` is `8.00%`; the fixture deliberately prints
`8.10%` once. Its other table has no explicit denominator, so calculation is
withheld. Every finding remains `unreviewed` with scientific error
`not_established`; provenance is `unverified_local`.

The command writes JSON and Markdown, creates output directories, and makes no
network request. Repeating identical inputs to the same output paths is allowed;
it refuses to replace different existing reports. Use a fresh output directory
when inputs or detector code change. Replace the fixture path and document ID
with your own permitted source to audit a real document, without changing the
provenance assertions unless supported by evidence.

For input limits, source-bound comparisons and conditional calculations, see
[OFFLINE_RESEARCH_AUDIT.md](docs/OFFLINE_RESEARCH_AUDIT.md).

### Public metadata discovery

The collector retrieves metadata leads through approved HTTPS services and the
inherited managed proxy; it does not retrieve full-text papers or prove that a
correction applies. It enforces rate, response and redirect boundaries and stops
on access/transport failure rather than switching routes. Windows managed
discovery is unavailable pending a reviewed ACL ownership guard; this does not
remove Windows support for the installed verifier core. Follow
[SCIENTIFIC_CANDIDATE_REVIEW.md](docs/SCIENTIFIC_CANDIDATE_REVIEW.md).
Developer-exposed discoveries never become untouched holdout evidence.

### PDF aid

Real PDF extraction is **not qualified**. It requires a reviewed SHA-256-pinned
local Poppler image and a qualified Docker isolation boundary. There is no host
Poppler fallback. Do not use it on protected evaluation material; synthetic runner
tests cannot establish real sandbox qualification. See
[PDF_SANDBOX_QUALIFICATION.md](docs/PDF_SANDBOX_QUALIFICATION.md).

## Real-paper validation

Committed historical executable fixtures include the 2007 elliptic-curve
corrigendum over `F_29` and a 2012 finite-map conclusion: `c=4` gives 40 points,
`c=7` gives 20, and the two-state swap has no fixed point while an unencoded
theorem premise remains an objection. The three replay cases are development
reproductions, not three untouched discoveries.

Earlier 0.2.0 notes mention network-reliability and QTT-Tucker mechanisms whose
runnable bundles are absent from this recovered tree. They are historical claims,
not freshly reproduced cases. The frozen 15-corrigendum screen is a mechanism map:
2/15 fully representable, 2 mechanism-only, 1 partial and 10 unsupported. It is
not a 15-paper end-to-end benchmark. See [validation assets](validation/) and the
[historical MVP record](docs/VALIDATION.md).

The recorded v1/v2 percentage experiments are developer-exposed; their sample
failures, partial reference census and adjudication limits remain unchanged.
No independent precision/recall estimate or general scientific correctness claim
follows from those experiments or from passing software tests.

## Contact readiness

`READY_FOR_USER_REVIEW` means a deterministic counterexample exists for the
supplied formalization, capture is asserted, correction evidence is recent and
reports none found, and unresolved objections are absent. It does not mean the
source is authenticated, the interpretation is uniquely correct, a whole paper
is false or a person should automatically be contacted.
`author_contact_authorized` is always `false`.

## Evidence integrity

Bundles bind source bytes, quote byte offsets, formalization, witness,
correction-search evidence, objections and SHA-256 manifests. `subject_sha256`
commits to the verification question; `bundle_sha256` commits to the bundle.
A separately trusted `--expected-bundle-sha256` pin detects changes to supplied
bytes, not whether the original evidence was true or authentically sourced.

## Security model

The core has no network, LLM client, optimizer, paper-code execution or arbitrary
bundle-code loading. It rejects or bounds duplicate JSON keys, floats, unsafe
paths and links, special files, oversized input and excessive mathematical work.
Read [SECURITY.md](SECURITY.md) for the trusted-local-process and quiescent-directory
assumptions, including what the implementation does not protect against.

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
and the issue templates. Report security-sensitive information privately using
[SECURITY.md](SECURITY.md); never upload credentials, private correspondence,
restricted manuscripts or protected evaluation records to public issues.

## Development

Use a real Git checkout with Git on PATH and the activated virtual environment.
The release gate uses `--no-build-isolation`, so install its declared backend
explicitly in that environment before qualification:

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

After editing selected files, follow [RELEASING.md](docs/RELEASING.md) to stage
intended changes and regenerate checksums before the release gate. Never use
blanket staging to collect caches or private research. CI checks supported
platforms, lint, coverage and reproducible artifacts. The whole-repository
coverage report is retained separately from the enforced verifier-core floor.

## Documentation and current product boundary

[Project status](docs/PROJECT_STATUS.md) separates current capabilities from
historical evidence. [The final quality assessment](docs/OSS_QUALITY_FINAL.md)
is the internal owner-accepted AI engineering review; [the initial audit](docs/OSS_QUALITY_AUDIT.md)
is explicitly historical. New changes require their own checks.

The long-term paper-to-report goal remains broader than the current implementation.
See [ROADMAP.md](docs/ROADMAP.md) for scientific evaluation and unmerged work.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
