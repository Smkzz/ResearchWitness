# ResearchWitness

[![CI](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml)

**Agent-oriented, deterministic evidence capsules for scientific claim verification.**

ResearchWitness is an open-source Python tool for the QEH-style workflow: a research agent identifies a narrow, testable claim and proposes a counterexample; ResearchWitness independently replays the formalized claim with an allowlisted deterministic verifier, binds the result to source/evidence bytes, and produces a scoped evidence capsule.

It is intentionally **not** an AI that declares whole papers wrong. A positive result means only that the supplied witness contradicts the supplied formalization.

**Development candidate:** `0.3.0.dev0` · unreleased · Python 3.11+ · runtime dependencies: none · Apache-2.0

## Status

This branch is an **unreleased verifier-wave candidate**, not a public release. The frozen 15-corrigendum screen remains unchanged. Its post-wave mechanism review classifies 2/15 as fully representable, 2/15 as mechanism-only, 1/15 as partial, and 10/15 as unsupported; only two screen entries have committed runnable fixtures. This is not a 15-paper discovery benchmark, and no sealed holdout has been evaluated. Unsupported mathematics fails closed.

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

## Deterministic verifier plugins

The `0.3.0.dev0` integration candidate allowlists ten checker families. Each registry entry includes the schema version, a concise input contract, exact resource bounds, what a positive witness proves and excludes, and an inline replay example with its source-checkout bundle path:

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
