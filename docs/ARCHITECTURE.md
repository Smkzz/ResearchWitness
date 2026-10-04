# MVP architecture

ResearchWitness separates flexible research-agent work from deterministic evidence replay.

```text
source / paper
    |
    v
research agent (untrusted preparation)
    |- claim extraction
    |- source/version capture
    |- correction search
    |- counterexample search
    |- assumptions + objections
    v
audit.json + source artifacts
    |
    v
intake.py
    |- strict file reads
    |- unique quote anchoring
    |- canonical witness
    |- evidence manifest + hashes
    v
private evidence bundle
    |
    v
capsule.py + checkers.py
    |- strict schema / resource bounds
    |- deterministic verifier routing
    |- exact or bounded arithmetic
    |- subject/bundle/core digests
    v
scoped verification report
    |
    +--> product.py: static HTML
    +--> product.py: contact readiness
    +--> product.py: conservative draft (user review only)
```

## Trusted verifier boundary

The trusted verification path is intentionally small: `strict.py`, `arithmetic.py`, `checkers.py`, and `capsule.py`. It has no network access, arbitrary code execution, optimizer, LLM client or paper-code runner.

`intake.py` is a convenience layer for agents. Its output is still an explicit bundle that can be inspected and replayed independently.

`product.py` is presentation/workflow policy. It does not change mathematical verdicts.

## Verifier plugins

Verifier kinds are allowlisted by `checkers.KINDS`. Each checker must:

1. accept only bounded structured data;
2. have deterministic semantics;
3. state exactly what its witness proves;
4. fail closed on unsupported inputs;
5. enforce a computational work budget;
6. avoid importing or executing case-supplied code.

The finite-field and modular linear-system plugins demonstrate the intended direction: broaden semantic coverage using small exact engines rather than one general “AI judge.” The modular linear-system checker verifies either an exact solution or a left-annihilator certificate, including over composite moduli.

## Contact readiness

The product layer can label a case `READY_FOR_USER_REVIEW`, but never `authorized`. It blocks when the counterexample is absent, the source is not captured, correction status is unclear/stale/present, or objections remain.

This keeps the original QEH product loop while avoiding a fake human-review requirement.
