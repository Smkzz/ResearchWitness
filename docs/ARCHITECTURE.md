# Architecture

ResearchWitness separates flexible candidate preparation from deterministic
evidence replay. See [project status](PROJECT_STATUS.md) for integrated versus
unmerged functionality.

```text
source / paper
    -> research agent: claim, source/version, proposed witness, objections
    -> intake.py: bounded reads, byte anchors, canonical witness and manifest
    -> private evidence bundle
    -> capsule.py + checkers.py: bounded deterministic verification
    -> product.py: JSON/HTML presentation, readiness and local inquiry draft
```

## Trusted verifier boundary

The trusted verification path is deliberately small: `strict.py`, `arithmetic.py`,
`checkers.py` and `capsule.py`. It contains no network client, LLM, optimizer,
arbitrary source-code execution or paper-code runner. It evaluates only supported
structured inputs under explicit work budgets.

`intake.py` is a preparation/convenience layer; its output remains an explicit
bundle which can be inspected and replayed independently. Quote positions use
zero-based byte offsets into supplied source bytes, not decoded-character indices.
`product.py` formats results and applies workflow policy without changing the
mathematical verdict.

## Installed core and source-checkout tools

The wheel installs `researchwitness*`, packaged schemas and capability data,
with no external runtime dependencies. The separate `tools/` programs run from
a source checkout after `python -m pip install -e '.[dev]'` in its activated
environment. Their schema validation uses the optional `jsonschema` dependency.

- `tools.research_audit` produces bounded JATS/PDF extraction reports and
  source-bound comparisons. Every finding remains unreviewed; arithmetic
  matches or candidates do not establish scientific error or source authenticity.
- JATS table aids track operands, headers, groups and source spans. Unsupported
  weighting, missingness or scope can force abstention. Conditional calculations
  retain their assumptions rather than asserting a guessed denominator.
- Metadata discovery is a separate networked operation through restricted
  managed-proxy/host/rate/redirect controls. Windows managed discovery remains
  unavailable pending a reviewed ACL ownership guard.
- PDF extraction requires a separately reviewed pinned image and qualified
  Docker isolation. It has no host Poppler fallback. Real runtime qualification
  has not been established by synthetic/mock tests.

This source-tool path does not install the `researchwitness.paper_audit`
architecture in the separate unmerged PR #6–#12 stack. The #12 custody worker
has its own security and authority boundary and is not approved by PR #13.
See [OFFLINE_RESEARCH_AUDIT.md](OFFLINE_RESEARCH_AUDIT.md) and
[SECURITY.md](../SECURITY.md).

## Verifier plugins

Kinds are allowlisted by `checkers.KINDS`. A checker must accept only bounded
structured data, use deterministic semantics, state exactly what the witness
proves and excludes, fail closed on unsupported inputs, enforce a work budget,
and avoid importing or executing case-supplied code.

Finite-field enumeration and finite-PMF checks use small exact engines, not a
general AI judge. Finite PMFs do not infer empirical populations. A rational AST
is evaluated at a supplied point, not proved globally. A modular certificate
checks the encoded system, including composite moduli, not the correctness of
its interpretation. [PROTOCOL.md](PROTOCOL.md) and the runtime `capabilities`
output contain the supported contracts.

## Command and contact readiness semantics

Successful execution is not necessarily a refutation: exit 0 can report
`NO_REFUTATION_AT_WITNESS`, and a structurally valid intake need not provide a
counterexample. Inspect the actual verdict and readiness fields separately.

`READY_FOR_USER_REVIEW` is a conservative draft-readiness state, never permission
to contact an author. Missing counterexamples, unsupported capture assertions,
unclear/stale/present corrections and unresolved objections block readiness.
No sending occurs. Owner acceptance of an AI-assisted **OSS engineering review**
does not satisfy independent scientific adjudication or protected evaluation.
