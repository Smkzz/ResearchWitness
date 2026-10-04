# ResearchWitness

[![CI](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml/badge.svg)](https://github.com/Smkzz/ResearchWitness/actions/workflows/codeql.yml)

**Agent-oriented, deterministic evidence capsules for scientific claim verification.**

ResearchWitness is an open-source Python tool for the QEH-style workflow: a research agent identifies a narrow, testable claim and proposes a counterexample; ResearchWitness independently replays the formalized claim with an allowlisted deterministic verifier, binds the result to source/evidence bytes, and produces a scoped evidence capsule.

It is intentionally **not** an AI that declares whole papers wrong. A positive result means only that the supplied witness contradicts the supplied formalization.

**Research Preview:** `0.2.0` · Python 3.11+ · runtime dependencies: none · Apache-2.0

## Status

ResearchWitness is a **research preview**. Its deterministic core is release-qualified, but verifier coverage is intentionally incomplete: the frozen 15-corrigendum screen currently has 2/15 faithfully encoded mechanisms, 2/15 important mechanism/conclusion-only cases, 1/15 partial case, and 10/15 unsupported cases. Unsupported mathematics fails closed.

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

From a source checkout:

```bash
python -m researchwitness capabilities
```

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

## Deterministic verifier plugins in the MVP

The MVP allowlists seven checker families:

1. **Scalar/radical comparison** — exact rationals plus certified square-root enclosures.
2. **Polynomial upper-bound witness** — exact rational polynomial evaluation in a bounded domain.
3. **Rational-expression upper-bound witness** — exact evaluation of a closed bounded rational AST at one in-domain point; it does not prove a global inequality.
4. **Binary UC functional** — the QEH-derived finite independent-source regression checker.
5. **Finite-field polynomial solution-count residue** — exhaustive prime-field enumeration with a hard work budget.
6. **Finite-field quadratic/quartic residue rule** — additionally classifies a parameter by power-residue class and tests the resulting count-residue rule.
7. **Finite self-map fixed-point conclusion** — exactly determines whether an explicit finite map has a fixed point; theorem premises remain separate.

The rational-expression grammar and exact evaluation limits are documented in [`docs/EXPRESSION_DSL.md`](docs/EXPRESSION_DSL.md).

Unsupported mathematics is rejected rather than approximated into a misleading scalar check.

```bash
python -m researchwitness capabilities
```

returns the current machine-readable capability list.

## Real-paper validation

The MVP was replayed against historical correction mechanisms. Important examples include:

- a 2025 network-reliability corrigendum: exact `K3` counterexample reproduced with margin `5/64`;
- a QTT-Tucker erratum: non-orthogonality mechanism reproduced with exact squared residual `1/64`;
- the 2007 elliptic-curve corrigendum over `F_29`: the MVP independently enumerates the curves, classifies `c`, and obtains:
  - `c=4`: quadratic non-quartic, **40 points**, `0 mod 8` versus expected `4 mod 8`;
  - `c=7`: quartic residue, **20 points**, `4 mod 8` versus expected `0 mod 8`;
- the 2012 modular-metric fixed-point erratum: the explicit swap on `{0,1}` is confirmed to have no fixed point, while the unencoded modular-metric premise remains an open objection.

The historical cases intentionally return `NOT_READY` for contact when a published correction is already known or source alignment remains unresolved.

The earlier frozen 15-paper screen remains useful: the MVP is **not yet a general theorem verifier**. Several corrigenda still require graph semantics, continuous probability/integration, PDE analysis, infinite-index arguments, database semantics, or domain-specific proof logic.

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

`author_contact_authorized` is always `false` in the MVP.

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
