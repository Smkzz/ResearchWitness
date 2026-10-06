# MVP architecture

ResearchWitness separates flexible research-agent work from deterministic evidence replay.

```text
paper file (unverified capture)
    |
    v
paper_audit.py (untrusted ingestion + narrow heuristic)
    |- preserves original bytes + SHA-256
    |- extracts UTF-8 text / optional isolated born-digital PDF text
    |- records page and byte anchors
    |- screens contextual n/N differences, selected table percentages, and one explicit sample-flow pattern
    v
screening report (candidate only; no paper-level verdict)
    |
    +--> review.py: multi-area human review ledger
    +--> explicit intake + capsule/checkers: scoped deterministic replay

source / claim / data
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

The trusted verification path is intentionally small: `strict.py`, `arithmetic.py`, `checkers.py`, `statistics.py`, and `capsule.py`. It has no network access, arbitrary code execution, optimizer, LLM client or paper-code runner. `statistics.py` recomputes bounded exact descriptive summaries from inline exact values or one column extracted from a local CSV/TSV file, and checks declared rounding tolerances. File extraction hashes the source bytes and records selected and missing data records; arbitrary analysis transformations are not applied.

`paper_audit.py` is outside the proof boundary. It preserves a local source file, adds local context around explicit lower-case `n` and upper-case `N` markers, recomputes selected count/percentage cells in Markdown pipe tables, and screens one explicit exclusion-flow sentence pattern. Its flags remain candidates. It cannot infer that statements share a population, that a table header is the denominator for every row, or that listed exclusions are disjoint and complete.

Optional `pypdf` extraction runs in a separate worker process with a fixed argument vector, no shell, a wall timeout, a source/page/text cap, and POSIX CPU/address-space limits where supported. This provides process separation and resource controls, not an OS sandbox: the worker has the same user and filesystem permissions, and the limits are not a formally complete denial-of-service defense. Extraction performs no OCR. A partial or unavailable extraction cannot produce a clean-scan decision.

`intake.py` is a convenience layer for agents. Its output is still an explicit bundle that can be inspected and replayed independently.

`product.py` is presentation/workflow policy. It does not change mathematical verdicts.

`review.py` is a separate, non-proof paper-review ledger. It records coverage across ten review areas, binds exact quotes and local evidence files, and can replay an existing formalization bundle or the tabular-summary checker. Agent-reported candidates remain explicitly unverified. A completed ledger does not establish that the review found every error or that an unflagged paper is correct. A linked formalization replay must use the exact same source bytes and quote offset as the review record; matching metadata alone is insufficient.

## Verifier plugins

Verifier kinds are allowlisted by `checkers.KINDS`. Each checker must:

1. accept only bounded structured data;
2. have deterministic semantics;
3. state exactly what its witness proves;
4. fail closed on unsupported inputs;
5. enforce a computational work budget;
6. avoid importing or executing case-supplied code.

The finite-field and finite-PMF plugins demonstrate the intended direction: broaden semantic coverage using small exact engines rather than one general “AI judge.” The PMF plugin handles finite event probabilities and expected payoffs over a declared categorical state space; it does not infer a distribution from data or extend the arithmetic result to a population.

The rational-expression checker uses a closed JSON AST for exact rational arithmetic. It can check rational-function witnesses such as quotients at one bounded point, while making no claim about the expression elsewhere in the domain.

The modular linear-system checker verifies either an exact solution or a left-annihilator certificate, including over composite moduli. It checks only the supplied certificate and encoded system.

## Contact readiness

The product layer can label a case `READY_FOR_USER_REVIEW`, but never `authorized`. It blocks when the counterexample is absent, the source is not captured, correction status is unclear/stale/present, or objections remain.

This keeps the original QEH product loop while avoiding a fake human-review requirement.
