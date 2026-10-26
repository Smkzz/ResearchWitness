# ResearchWitness

[![CI](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml)

**Open-source research verification with reproducible, source-linked evidence.**

The installed core verifies narrowly defined claims after an investigator or agent
supplies a formalization and possible counterexample. The installed JATS audit
extracts supported count/percentage relationships and records arithmetic candidates
or explicit abstentions. Separate checkout tools retain guarded metadata discovery
and scientific-development comparisons. ResearchWitness does **not** autonomously
fact-check any paper, authenticate publisher origin, establish misconduct or certify
conclusions.

**On main:** `0.3.0.dev0` · **UNRELEASED** · Python 3.11+ · CI tests Python
3.11–3.13 on Ubuntu, Windows and macOS · no installed runtime dependencies · Apache-2.0.

## Agent start and development plan

Every development agent starts with **[AGENTS.md](AGENTS.md)**, then
[the current status](docs/PROJECT_STATUS.md), [the development plan](docs/DEVELOPMENT_PLAN.md)
and [the execution ledger](docs/EXECUTION_STATE.json). The active plan is
`RW-PLAN-2026-10-24`: consolidate existing implementations, establish a benchmark,
add source-bound claim proposals and bounded adversarial search, then measure them.
The plan revision and informal "v4" vision are not package versions or implemented
features. [Continuation instructions](prompts/CONTINUE.md) resume the same queue.

Agents make ordinary technical choices, review and qualified merges autonomously.
Only new safety-sensitive authority or actual unauthorized money use needs a human
decision. Evidence and security gates remain mandatory; missing scientific evidence
is not replaced by an opinion. Default incremental spending authorization is EUR 0.

## Status

**Latest verified implementation main (2026-10-26):**
`659adf299a3efc4322cb5781337454b507e77ac6`. PRs
[#24](https://github.com/Smkzz/ResearchWitness/pull/24),
[#25](https://github.com/Smkzz/ResearchWitness/pull/25),
[#26](https://github.com/Smkzz/ResearchWitness/pull/26) and
[#27](https://github.com/Smkzz/ResearchWitness/pull/27)
integrated bounded source-mapped table projection, prospective study
**draft** validation with reviewed statistical declarations, and a
restricted explicit sample-flow helper. [Main CI](https://github.com/Smkzz/ResearchWitness/actions/runs/40314090213)
and [CodeQL](https://github.com/Smkzz/ResearchWitness/actions/runs/40314090186)
passed. No tagged release, independent scientific evaluation, PDF/custody
qualification or power-justified frozen study is claimed.

PR [#13](https://github.com/Smkzz/ResearchWitness/pull/13) merged on 2026-10-16, followed
by documentation #17 and intake/export consistency #18. The observed pre-plan main
is `242abaa2b5fe1f064ac10f14ae88e9bdfc825c1a` (2026-10-17), with passing main CI/CodeQL.
See [project status](docs/PROJECT_STATUS.md) for exact receipts; this is not a claim
that an untested later head passed. No tagged release or PyPI publication is claimed.

The internal 10-category engineering assessment used owner-accepted AI review,
not an independent human audit, security certification or scientific evaluation.
[Its report](docs/OSS_QUALITY_FINAL.md) is a pinned record. PR #6-#12 remains a separate
unmerged paper-audit/UI/custody stack. Real PDF extraction and Windows managed
metadata acquisition remain unavailable until their boundaries are qualified.
Scientific Wave 3 and sealed confirmatory evaluation have not run.

## Current MVP loop

```text
paper and source material
    -> investigator / research agent: claim, assumptions, proposed witness
    -> structured intake with source anchors
    -> deterministic verification and evidence bundle
    -> JSON report, optional HTML and reproducible private ZIP
```

The long-term source-to-discovery goal is broader than this implementation.
Candidate discovery, source interpretation and mathematical verification are
different jobs. `FORMALIZATION_COUNTEREXAMPLE_VERIFIED` proves something about the
supplied formalization/witness; `paper_error_established` remains `false`.
Unsupported inputs are rejected or abstained on, not guessed into a positive.

## Quick start

Install from source; this candidate is not advertised as available on PyPI.
You need Python 3.11+ and Git on PATH:

```text
git clone https://github.com/Smkzz/ResearchWitness.git
cd ResearchWitness
python -m venv .venv
```

Activate with `source .venv/bin/activate` on macOS/Linux or
`.venv\Scripts\Activate.ps1` in Windows PowerShell, then:

```text
python -m pip install .
python -m researchwitness --version
python -m researchwitness capabilities --json
python -m researchwitness schema intake
```

From the repository root run this **synthetic** example:

<!-- docs-smoke: core -->
```text
python -m researchwitness verify examples/counterexample --as-of 2026-10-04
```

Expected: exit 0, `FORMALIZATION_COUNTEREXAMPLE_VERIFIED` and
`paper_error_established: false`. The fixed date makes the fixture replayable;
it is not the capture date of a new research finding.

### Exit codes and interpretation

Exit 0 means evaluation completed, not that an error was found.
`NO_REFUTATION_AT_WITNESS` is a valid result; `validate-intake` may return
`valid: true` with that witness status. Inspect verdict, source context and readiness
separately. Malformed core inputs normally exit 2 with `INVALID`; argument errors
also exit 2 and may show argparse usage. JATS/PDF audits exit 0 for completed
processing (including abstentions), 2 for unsupported/failed extraction, and the
comparison's `--require-no-regression` exits 3 for its development-gate failure.
None establishes paper-level truth or contact authority.

### Prepare a case, replay and export

Use fresh output directories:

```text
python -m researchwitness scaffold finite_map_fixed_point --output work/fixed-point
python -m researchwitness validate-intake work/fixed-point/audit.json
python -m researchwitness audit work/fixed-point/audit.json --output work/fixed-point-bundle --as-of 2026-10-04
python -m researchwitness verify work/fixed-point-bundle --as-of 2026-10-04
python -m researchwitness report work/fixed-point-bundle --as-of 2026-10-04 --output work/fixed-point-report.html
python -m researchwitness pack work/fixed-point-bundle --as-of 2026-10-04 --output work/fixed-point-evidence.zip
```

The scaffold is synthetic, with an unchecked correction search and unresolved
objection; do not remove objections to present it as real evidence. Report/draft
parent directories must exist. The deterministic ZIP needs a new output filename.
Packing includes only manifested artifacts and reserved generated metadata, not
an entire directory. Intake/verification/export share bounded validation.

## Installed JATS review (development scope)

The distribution now includes the existing bounded JATS percentage detector without
loading network-discovery tools. It produces unreviewed arithmetic candidates, not a
whole-paper conclusion, misconduct allegation or author-contact authorization.
Use a new output directory (create the parent first):

```text
researchwitness audit-jats examples/synthetic-jats/article.xml --document-id synthetic-jats --output-dir out/installed-jats
researchwitness replay-jats out/installed-jats --expected-manifest-sha256 <manifest-sha256-from-audit>
```

Add --include-structure to audit-jats to include a source-mapped table model
(headers, spans, row labels, footnotes and denominator cues) within the same
private JSON bundle. This does NOT resolve ambiguous populations or adjustment
scope. See [JATS table model](docs/JATS_TABLE_PROJECTION.md).

The bundle stores original XML, structured JSON, escaped offline HTML, and a SHA-256
manifest. Replay re-extracts from the preserved source and checks the exact report.
Save the manifest hash externally if later coherent modification must be detected.
The synthetic example includes one match, one candidate and one abstention.
PDF/OCR and independent scientific evaluation remain unqualified.

## Agent intake format

The agent supplies `audit.json` beside referenced source files. Schemas are available
through `python -m researchwitness schema intake` and
[schemas/intake.schema.json](schemas/intake.schema.json). Record exact source/version,
capture assertion, correction evidence, one atomic claim, assumptions/exclusions,
quote, formalization, witness and unresolved objections. Follow
[the investigation protocol](prompts/AGENT_PROTOCOL.md).

`quote_offset` is a **zero-based byte offset into original source bytes**, matching
the UTF-8 quote, not a character index. Supply it when the quote repeats. A source
hash or quote match establishes byte consistency, not publisher authenticity.

## Deterministic verifier plugins

`capabilities --json` lists ten bounded families with contracts, limits and examples:

| Family | Scope of the supplied witness |
|---|---|
| Scalar/radical comparison | Exact rational comparison with certified square-root enclosures. |
| Polynomial upper-bound witness | Polynomial evaluation at a supplied bounded-domain point. |
| Rational-expression upper-bound witness | Exact closed rational AST evaluation at one point, not a global inequality. |
| Binary UC functional | QEH-derived finite independent-source regression check. |
| Finite-field polynomial solution-count residue | Exhaustive enumeration under a hard work budget. |
| Quadratic/quartic residue rule | Parameter residue classification and point-count check. |
| Finite self-map fixed-point conclusion | Fixed points of an explicit finite map; theorem premises stay separate. |
| Finite graph chromatic lower bound | A supplied proper coloring refutes a larger lower bound; no optimal search. |
| Finite PMF bound | Event probability/expectation for a supplied distribution, not population inference. |
| Modular linear-system certificate | A supplied solution or left-annihilator certificate for the encoded system. |

The graph checker accepts 1–256 vertices and at most 8,192 edges. See
[EXPRESSION_DSL.md](docs/EXPRESSION_DSL.md), [PROTOCOL.md](docs/PROTOCOL.md) and
[synthetic examples](examples/). Unsupported mathematics is not approximated into
an unrelated scalar check. Future certificate extensions follow RW-08.

## Source-checkout research-audit tools

The wheel installs `researchwitness`, not `tools/`. From the **repository root** in
the activated environment install optional development dependencies:

```text
python -m pip install -e '.[dev]'
```

These include `jsonschema`; a core-only install is not sufficient for source tools.

### Offline JATS audit

Use the invented local fixture without a network request:

<!-- docs-smoke: jats -->
```text
python -m tools.research_audit audit examples/synthetic-jats/article.xml --document-id synthetic-jats --format jats --json-output out/synthetic-jats/audit.json --markdown-output out/synthetic-jats/audit.md
```

Expected: two tables, three relationships, one arithmetic match, one mismatch
candidate and one abstention. `4/50` is `8.00%`; one fixture row prints `8.10%`.
The other table lacks an explicit denominator. All findings stay `unreviewed`,
scientific error `not_established`, and provenance `unverified_local`.

The command creates JSON/Markdown directories and repeats identical outputs
idempotently; different existing reports are not overwritten. Use fresh outputs
when inputs/code change. Own permitted sources need honest provenance assertions.
See [OFFLINE_RESEARCH_AUDIT.md](docs/OFFLINE_RESEARCH_AUDIT.md) for limits and comparison.

### Public metadata discovery

The separate collector retrieves leads through approved HTTPS services and inherited
managed proxy controls, not paper full text. Rate/response/redirect limits remain;
access denial is not bypassed by a different route. Windows discovery remains blocked
pending ACL qualification, separately from installed-core Windows support. Follow
[SCIENTIFIC_CANDIDATE_REVIEW.md](docs/SCIENTIFIC_CANDIDATE_REVIEW.md). Development-discovered
cases never become untouched holdouts merely by being reviewed later.

### PDF aid

Real PDF extraction is **not qualified**. It needs a reviewed SHA-256-pinned minimal
Poppler image and real Docker isolation/resource/cleanup evidence. There is no host
fallback. Mock tests do not lift the gate. See
[PDF_SANDBOX_QUALIFICATION.md](docs/PDF_SANDBOX_QUALIFICATION.md); do not use developer
aids on protected evaluation material.

## Research protocol draft (offline)

The checkout tool `python -m tools.research_preregistration` validates a
prospective **study draft** with study/arm commitments, work-family sampling
rules, primary detection and negative false-alarm endpoints, alpha allocation,
resource caps, zero incremental spend and no interim sealed looks. A synthetic
example is in `examples/synthetic-study-registration/draft.json`. See
[the preregistration guide](docs/RESEARCH_STUDY_REGISTRATION.md).
It neither runs a study nor verifies statistical power/independent custody.

## Real-paper validation and benchmark

The executable historical fixtures include a 2007 elliptic-curve corrigendum over
`F_29` and a 2012 finite-map conclusion. These three replay cases are development
reproductions, not untouched discoveries. Earlier 0.2.0 notes also mention cases
whose runnable bundles are absent from the recovered tree; they are historical
claims, not freshly reproduced evidence. The frozen 15-case mechanism screen is
not an end-to-end paper benchmark. See [validation assets](validation/) and
[the historical record](docs/VALIDATION.md).

The v1/v2 percentage studies remain developer-exposed, with their failures and
adjudication limits preserved. They establish no independent general precision/
recall. [BENCHMARK_PROTOCOL.md](docs/BENCHMARK_PROTOCOL.md) specifies future measurement;
it is not an already frozen or completed evaluation.

## Contact readiness

`READY_FOR_USER_REVIEW` is the unchanged legacy draft-readiness result. It requires
a verified formalization counterexample and conservative context gates; it does
not authenticate the source, resolve all possible interpretations or authorize
contact. `author_contact_authorized` stays `false`. For an eligible bundle,
`python -m researchwitness contact-draft BUNDLE --as-of YYYY-MM-DD --output inquiry.txt`
creates a local draft. An agent may prepare it autonomously; sending remains outside
this software and needs a separate safety decision. The synthetic scaffold stays
`NOT_READY` intentionally. Never remove its objections to manufacture eligibility.

## Evidence integrity and security

Bundles bind source bytes/quote offsets, formalization, witness, correction evidence,
objections and manifests. `subject_sha256` commits to the verification question;
`bundle_sha256` to the bundle. A separately trusted expected-bundle hash detects
later byte changes, not original truth. The core has no network, LLM, optimizer,
paper-code execution or dynamic loading. It rejects/bounds unsafe JSON, paths/links,
special files, excessive inputs and work. Read [SECURITY.md](SECURITY.md) for local
process, quiescent-directory and source-origin assumptions.

## Development

Use a real Git checkout with Git on PATH and the activated environment. The release
gate uses `--no-build-isolation`, so install its backend explicitly:

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

Follow [CONTRIBUTING.md](CONTRIBUTING.md) and [RELEASING.md](docs/RELEASING.md) for
reviewed staging, checksum regeneration, exact-head checks and qualified releases.
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and issue templates apply. Do not post private
material or sensitive security reports publicly. Current capabilities are indexed
in [PROJECT_STATUS.md](docs/PROJECT_STATUS.md); historical evidence stays unchanged.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
