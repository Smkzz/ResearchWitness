# Roadmap

ResearchWitness is deliberately growing verifier breadth before growing marketing or automation surface.

## Current local branch — 0.3.0.dev0 integration candidate (unreleased)

- Agent-prepared structured intake.
- Multi-area paper-review ledger covering citations, internal consistency, mathematics, statistics, data, methods, code, figures/tables, interpretation, and ethics/reporting. Reviewer candidates are not automatically verified.
- A bounded `paper-audit` screen for conflicting explicit `n=` / `N=` integer markers in UTF-8 text, Markdown, or optional born-digital PDF extraction. It reports candidates only and does not infer that counts share a scope.
- Exact univariate tabular-summary check for count, sum, mean, median, minimum, maximum and variance, with explicit rounding tolerances and bounded local CSV/TSV column extraction.
- Deterministic evidence capsules and replay.
- Ten bounded verifier families: scalar/radical, polynomial, rational-expression, binary UC, finite-field residue, quadratic/quartic residue rule, finite-map fixed point, finite-graph coloring, finite-PMF bounds, and modular linear-system certificates.
- Machine-readable capability contracts, one replayable synthetic bundle per family, agent-intake JSON Schema, scaffold, and read-only intake validation.
- Offline HTML / JSON reporting and deterministic evidence export.
- Historical corrected-paper replay cases.
- Conservative contact-readiness output; no external actions.
- No unseen historical-corrigenda holdout has been run; this candidate is not release-qualified.

## Next validation gate

Freeze the verifier code and establish whether the added families improve historical coverage. Keep the 15-case screen immutable and report mechanism-level representability separately from end-to-end rediscovery. Build an independent public-source development corpus and sealed holdout before using discovery recall or false-positive rates as release claims.

The remaining gate work is:

1. recover or build source-pinned runnable artifacts for the 13 frozen-screen entries without committed fixtures;
2. create independent development and sealed holdout sets with source/version records and negative controls;
3. measure useful discovery coverage, unsupported rate, false formalization counterexamples, scope errors, and repeatability;
4. decide whether the modular verifier wave merits a 0.3.0 research preview.

Do not tag or publish `0.3.0` until the exact public commit passes the engineering and scientific gates.

## Next empirical milestone

Run a frozen **unseen historical-corrigenda discovery benchmark** with independent research agents. The deterministic verifier must remain unchanged during an evaluation wave. Report unsupported cases and source-interpretation failures rather than silently excluding them.

The broad review ledger is an observation and coverage layer, not a general error detector. The automatic paper scan currently covers only explicit count-marker conflicts; it has no measured discovery precision or recall. The exact tabular checker covers univariate summaries over supplied tabular data. Use benchmark results to prioritize further deterministic checkers for recurring, source-grounded failure mechanisms, including prose/table count reconciliation, code-parameter reconciliation, and citation-to-claim support. Keep each detector narrow, replayable, and explicit about what its result does not establish.

Metrics of interest include:

- known-error rediscovery;
- false formalization counterexamples;
- scope/interpretation errors;
- unsupported-case rate;
- reproducibility of evidence capsules;
- cost and agent effort per defensible case.

## Later

Potential adapters include paper retrieval, code-vs-paper consistency, and proof-assistant/certificate integrations. They should remain outside or below the trust boundary unless their outputs are independently machine-checkable.

Automatic public accusations, researcher scoring, misconduct inference, and automatic author contact are not roadmap goals.
