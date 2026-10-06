# ResearchWitness

[![CI](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml)

**Offline paper screening, evidence-linked reviews, and bounded deterministic claim verification.**

ResearchWitness is an open-source Python workbench for limited automated screening and structured human review of research papers. `paper-audit` checks explicit sample-count contexts, selected Markdown table percentages, and one narrow sample-exclusion sentence pattern. Reviewers can also record observations across ten review areas, preserve exact source quotes and supporting evidence, and replay a narrow formalized claim with an allowlisted deterministic verifier when a supported checker exists. The broad review ledger organizes observations; the verifier establishes only the exact bounded result it replays.

It is intentionally **not** an AI that declares whole papers wrong. A positive result means only that the supplied witness contradicts the supplied formalization.

**Development candidate:** `0.4.0.dev0` · unreleased · Python 3.11+ · runtime dependencies: none · Apache-2.0

## Status

This branch is an **unreleased development candidate**, not a public release. It builds on the verifier-wave integration, whose frozen 15-corrigendum screen remains unchanged. That mechanism review classifies 2/15 as fully representable, 2/15 as mechanism-only, 1/15 as partial, and 10/15 as unsupported; only two screen entries have committed runnable fixtures. A new source-pinned paper-audit development set rediscovers 3/4 selected documented issues and produces no candidates on 5 selected negative controls. Those papers and corrections were visible during detector work, so this is an exploratory development result, not a sealed or generalization benchmark. The archived qualification report predates these updates; current validation and limits are in [`docs/VALIDATION.md`](docs/VALIDATION.md).

Use it to verify **explicit formalization/witness pairs**, not to infer that an entire paper, author, or research program is wrong.

See [`docs/VALIDATION.md`](docs/VALIDATION.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## MVP product loop

```text
paper / source text
       |
       v
research agent
  - extracts one atomic claim
  - searches for a witness
  - records assumptions/objections
       |
       v
agent intake JSON
       |
       v
ResearchWitness
  - prepares immutable evidence bundle
  - routes to deterministic verifier
  - replays witness exactly
  - hashes source + evidence
  - preserves unresolved objections
       |
       +--> JSON evidence report
       +--> private deterministic ZIP
       +--> static HTML report
       +--> contact readiness: READY_FOR_USER_REVIEW / NOT_READY
       +--> conservative author-inquiry draft (user review required)
```

ResearchWitness never sends mail, publishes accusations, infers misconduct, or authorizes contact.

## Why this split exists

LLMs and research agents are good at flexible tasks such as reading papers, reconstructing claims, proposing attacks, searching for counterexamples, and noticing inconsistencies. They are not proof certificates.

ResearchWitness therefore treats the agent as an **untrusted investigator** and the checker as a **small deterministic replay layer**. The useful output is not “the AI says this paper is wrong,” but something like:

```text
FORMALIZATION_COUNTEREXAMPLE_VERIFIED

paper_error_established: false
contact_readiness: READY_FOR_USER_REVIEW
```

The second line matters as much as the first.

## Quick start

This development candidate is not published on PyPI. From a source checkout, install the package locally and inspect its agent interfaces:

```bash
python -m pip install .
researchwitness --version
python -m researchwitness capabilities --json
python -m researchwitness schema intake
python -m researchwitness scaffold finite_map_fixed_point --output work/fixed-point
python -m researchwitness validate-intake work/fixed-point/audit.json
```

`scaffold` creates a synthetic, editable example for one supported checker. Its source is marked `synthetic`, its correction search is `unchecked`, and it carries an unresolved objection. Replace those fields with source-pinned research material before treating the intake as a research case. `validate-intake` checks local artifact availability, quote anchoring, checker semantics, and witness validity without creating a bundle. The intake JSON Schema is also available at [`schemas/intake.schema.json`](schemas/intake.schema.json) and through `researchwitness schema intake` after installation.

The easiest MVP workflow is `audit` using an agent-prepared intake file:

```bash
python -m researchwitness audit audit.json \
  --output evidence/my-case \
  --html evidence/my-case.html \
  --as-of 2026-10-04
```

The command:

1. reads the declared source and correction-search evidence;
2. anchors the claim quote to the supplied source bytes;
3. canonicalizes the witness;
4. builds a strict evidence bundle;
5. routes the formalization to the matching verifier;
6. emits the deterministic report plus contact-readiness state.

You can later replay the capsule without the intake layer:

```bash
python -m researchwitness verify evidence/my-case --as-of 2026-10-04
```

Create a deterministic private evidence ZIP:

```bash
python -m researchwitness pack evidence/my-case \
  --as-of 2026-10-04 \
  --output my-case-evidence.zip
```

Render a standalone report:

```bash
python -m researchwitness report evidence/my-case \
  --as-of 2026-10-04 \
  --output report.html
```

If all MVP context gates are clean, a conservative draft can be generated:

```bash
python -m researchwitness contact-draft evidence/my-case \
  --as-of 2026-10-04 \
  --output author-inquiry.txt
```

This produces a draft only. The output explicitly requires user review and does not establish a paper-level error.

## Agent intake format

A research agent writes a small `audit.json` next to the source files it used:

```json
{
  "intake_version": "0.1",
  "case_id": "example-claim",
  "source": {
    "identifier": "doi:...",
    "version": "v1",
    "text_file": "source.txt",
    "capture_status": "captured",
    "correction_check": {
      "checked_on": "2026-10-04",
      "status": "none_found",
      "evidence_file": "correction.txt"
    }
  },
  "claim": {
    "id": "eq-22",
    "statement": "...",
    "scope": "...",
    "assumptions": ["..."],
    "excluded_claims": ["..."],
    "quote": "exact quote present in source.txt",
    "formalization": {"kind": "..."}
  },
  "witness": {"kind": "..."},
  "unresolved_objections": []
}
```

If the quote appears more than once, the agent must provide `quote_offset`. ResearchWitness will not silently guess which occurrence was intended.

See [`prompts/AGENT_PROTOCOL.md`](prompts/AGENT_PROTOCOL.md) for the preparation rules.

## Broad paper review

The single-claim `audit` command is for claims that fit one of the deterministic checkers. The `paper-audit` command runs the narrow automatic numeric screens described below. For a wider review, `review-scaffold` creates a multi-area ledger for source/citation integrity, internal consistency, mathematics and logic, statistics, data integrity, methods, code reproducibility, figures/tables, interpretation, and ethics/reporting. Those ten areas organize human review; they are not ten automatic detectors.

### Limited automatic paper screening

`paper-audit` accepts UTF-8 text or Markdown. Born-digital PDF extraction is available with the optional `paper` extra:

```bash
python -m pip install '.[paper]'
python -m researchwitness paper-audit paper.pdf \
  --identifier doi:10.example/paper \
  --source-version v1 \
  --output screening/paper
```

The command preserves the original input, writes extracted text, and creates JSON and static HTML reports. It reports contextual differences between explicit `n=` / `N=` counts, recomputes count/percentage cells only when a Markdown pipe table has an explicit same-column denominator, and checks one explicit “Of the X participants … excluded … Finally, Y participants were included” pattern. All outputs remain review candidates: separate groups or stages can have different counts, table rows can use smaller missing-data denominators, and exclusions may overlap or omit a flow step. A clean result covers only these patterns. The screens do not check statistical tests, confidence intervals, citations, equations, units, methods, code, figures, conclusions, or corrections, and they do not authenticate the source.

Text and Markdown are preserved byte-for-byte and must be UTF-8. PDF extraction uses optional `pypdf` (BSD-3-Clause) in a separate worker, performs no OCR, and may be partial or unavailable. The worker has a 20-second wall timeout, a 15-second CPU limit, and a 768 MiB address-space limit where POSIX limits are supported; it is process isolation, not an OS sandbox. The report records page and extracted-text offsets, not precise PDF layout coordinates. Resource limits are 32 MiB per source, 500 PDF pages, 16 MiB total PDF extracted text, 512 KiB per extracted page, 1,000,000 scanned lines, 512 Markdown headings, 512 count markers, 100,000 Markdown table cells, and 64 KiB per scanned line. Source identity, version, and authenticity remain unverified. See [`schemas/paper-audit.schema.json`](schemas/paper-audit.schema.json) for the report contract.

The [synthetic sample](examples/paper-audit/paper.md) reports `n = 20` at recruitment and `n = 18` after exclusions. The updated screen describes these as a possible study-stage difference instead of an error candidate. Run it to inspect the report:

```bash
python -m researchwitness paper-audit examples/paper-audit/paper.md \
  --identifier synthetic:paper-audit --source-version fixture-v1 \
  --output work/paper-audit
```

The source-pinned development corpus, scoring definitions, per-paper JSON reports, and exact-hash retrieval/runner tools are in [`validation/paper-audit-wave-1/`](validation/paper-audit-wave-1/). The corpus contains four correction-backed positives and five selected negative controls; it has no sealed holdout and does not establish cross-field performance.

Start from a UTF-8 text capture of the exact paper version:

```bash
python -m researchwitness review-scaffold \
  --source-file paper.txt \
  --identifier doi:10.example/paper \
  --source-version v1 \
  --output review/paper
```

The command copies the source bytes into `review/paper/paper.txt` and creates `review.json` with every review area marked `not_reviewed`. Record methods and limits per area, then add findings with an exact paper quote, location, rationale, and local evidence files. Candidate observations stay unverified. A finding may link to an existing checker bundle with `formalization_replay` or a summary input with `tabular_summary_replay`; validation reruns the linked check and records its precise result, while still setting `paper_error_established` to `false`.

Validate the ledger and optionally render an offline report:

```bash
python -m researchwitness validate-review review/paper/review.json \
  --html review/paper/report.html
```

The review JSON Schema is available at [`schemas/review.schema.json`](schemas/review.schema.json) and through `researchwitness schema review`. `validate-review` checks all ten areas, source quote anchors, local evidence paths and hashes, and any linked formalization or summary replay. For a summary replay, the report also records hashes for the linked summary input and any referenced CSV/TSV file in the finding's evidence map. `all_areas_accounted_for: true` means only that the ledger has no area left unreviewed or unsupported; it does not prove that all errors were found or that no error exists. See [`prompts/PAPER_REVIEW_PROTOCOL.md`](prompts/PAPER_REVIEW_PROTOCOL.md) for the cross-domain review procedure.

The [synthetic arithmetic-discrepancy ledger](examples/paper-review-ledger/) replays a mean mismatch over supplied values and keeps source-to-data alignment unverified:

```bash
python -m researchwitness validate-review examples/paper-review-ledger/review.json
```

## Deterministic verifier plugins

The `0.4.0.dev0` integration candidate allowlists ten checker families. Each registry entry includes the schema version, a concise input contract, exact resource bounds, what a positive witness proves and excludes, and an inline replay example with its source-checkout bundle path:

1. **Scalar/radical comparison** — exact rationals plus certified square-root enclosures.
2. **Polynomial upper-bound witness** — exact rational polynomial evaluation in a bounded domain.
3. **Rational-expression upper-bound witness** — exact evaluation of a closed bounded rational AST at one in-domain point; it does not prove a global inequality.
4. **Binary UC functional** — the QEH-derived finite independent-source regression checker.
5. **Finite-field polynomial solution-count residue** — exhaustive prime-field enumeration with a hard work budget.
6. **Finite-field quadratic/quartic residue rule** — additionally classifies a parameter by power-residue class and tests the resulting count-residue rule.
7. **Finite self-map fixed-point conclusion** — exactly determines whether an explicit finite map has a fixed point; theorem premises remain separate.
8. **Finite graph chromatic lower bound** — checks a supplied proper coloring and refutes a claimed lower bound when that coloring uses fewer colors; no chromatic-number search is performed.
9. **Finite PMF bound** — exactly computes an event probability or expected payoff over a bounded finite state space and compares it with a rational bound.
10. **Modular linear-system certificates** — verifies a solution vector or a left-annihilator certificate for a system over a bounded composite or prime modulus.

The rational-expression grammar and exact evaluation limits are documented in [`docs/EXPRESSION_DSL.md`](docs/EXPRESSION_DSL.md). It evaluates only a supplied point and does not establish a global inequality.

The graph checker accepts simple undirected graphs with 1–256 vertices and 0–8,192 edges. It verifies a supplied proper coloring in O(V+E) time; it does not search for an optimal coloring. Replay the synthetic path-graph example with:

```bash
python -m researchwitness verify examples/graph-chromatic-lower-bound --as-of 2026-10-04
```

The finite PMF checker establishes arithmetic facts only for the supplied distribution. It does not validate empirical data or extend a result to a population or broader scientific claim. Replay its synthetic example with:

```bash
python -m researchwitness verify examples/finite-pmf-probability --as-of 2026-10-04
```

Run the modular certificate example with `python -m researchwitness verify examples/modular-linear-system --as-of 2026-10-04`. Its left-annihilator certificate proves that `2x = 1 (mod 6)` has no solution, contradicting the supplied formalization.

Unsupported mathematics is rejected rather than approximated into a misleading scalar check. Every family has a synthetic replay bundle under [`examples/`](examples/), and `capabilities --json` includes a copy of its formalization and witness.

```bash
python -m researchwitness capabilities --json
```

returns the current machine-readable capability list. Synthetic examples exercise software behavior; they do not establish new historical-paper coverage.

The capability output also lists an empirical summary check outside the proof-family registry and a separate `paper_screens` section for candidate-generation heuristics. Agents must not present a paper-screen candidate as a verifier result. `check-summary` recomputes count, sum, mean, median, minimum, maximum, and sample/population variance from one numeric column supplied as exact values or read from a local CSV/TSV file (up to 2 MiB and 4,096 records). File inputs select a unique header name or zero-based column index, declare missing-value markers and a reject/drop policy, and produce a source-file hash plus included/missing record numbers in 1-based logical record order. Integers, rational strings, and finite decimals are parsed exactly. The checker processes all rows in order; it does not apply arbitrary filtering, grouping, weighting, or transformations. Inputs also declare the data source and any claimed transformation, which is recorded but not executed. Use an explicit tolerance for rounding (for example, `1/20` for a value rounded to one decimal place). A mismatch is limited to the selected supplied column and reported number; the check cannot authenticate data provenance, establish that the values came from the cited paper, or confirm that the analysis used the same inclusion rules. The [`summary-check` JSON Schema](schemas/summary-check.schema.json) and `researchwitness schema summary-check` describe its input.

```bash
python -m researchwitness check-summary examples/paper-review-ledger/summary-check.json
```

The example review links this check as a `tabular_summary_replay`, so the multi-area report reruns the calculation and records its exact result.

## Real-paper validation

The committed executable historical fixtures cover the 2007 elliptic-curve corrigendum over `F_29` and the 2012 finite-map conclusion:

- elliptic-curve `c=4`: 40 points, `0 mod 8` versus expected `4 mod 8`;
- elliptic-curve `c=7`: 20 points, `4 mod 8` versus expected `0 mod 8`;
- modular-metric fixed point: the explicit swap on `{0,1}` has no fixed point, while the unencoded premise remains an open objection.

The earlier `0.2.0` validation notes also describe network-reliability `K3` and QTT-Tucker mechanisms, but their runnable fixtures are absent from this recovered source tree. They are not counted as freshly reproduced cases in this candidate.

The historical cases intentionally return `NOT_READY` for contact when a published correction is already known or source alignment remains unresolved.

The previous frozen 15-paper screen is a mechanism-level coverage map, not an end-to-end discovery benchmark. Several corrigenda still require continuous probability/integration, PDE analysis, infinite-index arguments, database semantics, or domain-specific proof logic. See the candidate-specific coverage review under [`validation/verifier-wave/`](validation/verifier-wave/) for which screen entries are executable in this tree.

See [`validation/`](validation/) and [`docs/VALIDATION.md`](docs/VALIDATION.md).

## Contact readiness

`READY_FOR_USER_REVIEW` means only:

- the supplied formalization has a deterministic counterexample;
- source capture is declared `captured`;
- the correction search is recent and recorded as `none_found`;
- no unresolved objection is present;
- no known correction is recorded.

It **does not** mean:

- ResearchWitness authenticated the publication;
- the formalization is necessarily the only correct reading of the paper;
- the whole paper is wrong;
- an author should automatically be contacted;
- misconduct occurred.

`author_contact_authorized` is always `false`.

## Evidence integrity

A strict evidence bundle binds:

- source snapshot bytes;
- exact claim quote + byte offset;
- formalization;
- witness;
- correction-search evidence;
- unresolved objections;
- SHA-256 hashes of manifested artifacts.

`subject_sha256` commits to the actual verification question. `bundle_sha256` commits to the complete manifested bundle.

An externally stored bundle hash can later detect a coordinated rewrite:

```bash
python -m researchwitness verify evidence/my-case \
  --expected-bundle-sha256 <trusted-sha256>
```

## Security model

The deterministic verifier:

- performs no network access;
- executes no paper code;
- imports no bundle code;
- invokes no optimizer;
- rejects duplicate JSON keys and JSON floats;
- bounds JSON, artifact and mathematical workloads;
- rejects symlinks, hard links, FIFOs and traversal paths;
- uses exact rationals wherever possible.

Read [`SECURITY.md`](SECURITY.md) for the complete threat model.

## Contributing

Bug reports and bounded deterministic verifier proposals are welcome. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md), and the repository issue forms. Security-sensitive reports follow [`SECURITY.md`](SECURITY.md).

## Development

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python benchmarks/run_synthetic.py
python validation/mvp_real/run_validation.py
python tools/quality_gate.py
```

The verifier has no runtime dependencies outside Python's standard library.

## Current product boundary

The MVP deliberately does **not** bundle an LLM provider or paid API. The intended user is a research agent/harness that can read literature and produce the structured intake. This keeps the OSS core model-agnostic and usable with subscription-based agent workflows.

The next product step is broader verifier coverage and a frozen discovery benchmark on unseen historical corrections—not a larger marketing surface. See the public [`roadmap`](docs/ROADMAP.md).

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).
