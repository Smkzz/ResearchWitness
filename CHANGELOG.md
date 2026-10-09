# Changelog

## 0.4.0.dev0 — paper-audit empirical development wave — unreleased

- Added an optional local-first upload interface with local reports, coverage, source-bound replay/export, cancellation, retry, retention limits and explicit local-data deletion. This interface is not a custody boundary; its browser/API route still needs a real-browser qualification.
- Added an offline custody-worker v5 source contract, versioned schemas and synthetic evidence store. It remains a development artifact; no reserved evidence or Wave 3 run is qualified.
- Added package qualification tools for deterministic clean zipapp and wheel builds, with offline synthetic workflow checks. This candidate has not received final hosted checks or Windows custodian qualification.

- Expanded source-native JATS paper coverage with per-paper, per-detector, per-operand, and per-table accounting; direct-cell ratios; conservative sample-flow and PRISMA prose adapters; crude unadjusted 2×2 odds-ratio checks; and an experimental SD/SE/n screen. Added explicit detector boundaries and report coverage explanations. These checks remain candidate-only and do not establish paper-level errors.
- Added a post-hoc development replay and aggregate-only source-validation summaries. Public artifacts omit individual source bindings, hashes, arithmetic, and candidate records. The replay is not a holdout; the source-mapped percentage targets use development data, while flow, PRISMA, 2×2, rates, and cross-section discrepancies remain unsupported as correction-backed mechanisms where their strict contracts do not fit.
- Expanded `paper-audit` with contextual `n`/`N` count screening, Markdown table count/percentage recomputation, and a bounded explicit exclusion-flow arithmetic screen. Every paper-level output remains a human-review candidate; no findings are promoted to paper errors.
- Added source-section and local-context cues, possible study-stage and row-denominator notes, rounding tolerance, and richer anchored HTML/JSON reports.
- Moved optional `pypdf` extraction into a separate worker with fixed arguments, no shell, wall/CPU/address-space limits where supported, and explicit parser/resource failure outcomes. This is process isolation, not a sandbox.
- Added source-pinned development corpus tooling and a report-only evidence set. On four selected correction-backed positives the screens rediscovered three issues; four surfaced candidate items matched those corrections. No candidates were emitted on five selected negative controls. These are development-set results, not an independent or sealed evaluation.
- Added Markdown/JATS renderer and exact-hash Europe PMC retrieval tooling. Full articles and PDFs are not committed; source/version hashes and short report anchors are preserved.
- Added regression and malformed/oversized/encrypted/timeout PDF worker tests, schema v0.2, capability updates, and static review of the isolated worker call path.

This candidate has no sealed holdout and does not support arbitrary-paper correctness claims or cross-disciplinary performance claims.

## 0.3.0.dev0 — verifier-wave integration candidate — unreleased

- Added `paper-audit` for bounded UTF-8 text/Markdown and optional born-digital PDF extraction, preserving source bytes and reporting conflicting explicit `n=` / `N=` markers as human-review candidates only. No paper-level correctness or rediscovery claim is made.
- Added a report JSON Schema, output and extraction limits, page/byte anchors, partial-scan outcomes, and installed-wheel command smoke checks.
- Added a multi-area review ledger for broad paper audits; exact quote anchors and evidence-file hashes are checked, while unverified reviewer observations stay separate from deterministic checker replays.
- Added an exact tabular-summary checker for bounded rational data columns and explicit rounding tolerances; it does not authenticate data provenance or source alignment.
- Added bounded CSV/TSV column extraction for summary checks, recording source-file hashes, selected record numbers, and explicit missing-value handling. Linked review reports include the summary input and data-file hashes in the finding evidence map. Filtering and transformations are not executed.
- Added bounded rational-expression, finite-graph coloring, finite-PMF probability/expectation, and modular linear-system verifiers.
- Added per-family exact resource contracts and replayable synthetic examples to `capabilities --json`.
- Added agent-intake JSON Schema, packaged schema access, synthetic `scaffold`, and read-only `validate-intake` CLI commands.
- Fixed multiline intake values from reshaping generated contact drafts by rendering claim and scope as quoted blocks and normalizing subject fields to one line.
- Preserved the frozen 15-case screen and added a separate post-wave representability review; no sealed holdout or new-paper discovery evaluation is claimed.
- This development candidate is not a published release. See `docs/ROADMAP.md` for the release gate.

## 0.2.0 — 2026-10-04 — MVP research preview

### Product workflow

- Added `audit` intake flow for research agents.
- Added automatic evidence-bundle construction and unique quote anchoring.
- Added machine-readable `capabilities` output for verifier routing.
- Added static offline HTML evidence reports.
- Added conservative `READY_FOR_USER_REVIEW` / `NOT_READY` contact-readiness policy.
- Added author-inquiry draft generation; sending remains outside the product.

### Verifier coverage

- Retained scalar/radical, polynomial and QEH binary-UC checkers.
- Added bounded finite-field polynomial solution-count residue verification.
- Added quadratic/quartic power-class + point-count residue verification.
- Added finite self-map fixed-point conclusion verification.
- Added hard finite-field enumeration/work budgets.

### Validation

- Replayed previous network-reliability and QTT real-paper validation cases without regression.
- Added end-to-end MVP historical validation for the 2007 elliptic-curve corrigendum (`p=29,c=4` and `c=7`).
- Added the 2012 modular-metric fixed-point counterexample as a conclusion-only case with the unverified theorem premise preserved as an objection.

### Scope

ResearchWitness still certifies only supported formalization/witness relationships. `paper_error_established` remains false and `author_contact_authorized` remains false.

## 1.0.0-internal — 2026-10-04

Internal pre-MVP deterministic-core qualification artifact. It was never recommended as a broadly validated public research-verifier release; the public preview line was reset to `0.2.x` after real-paper coverage testing.
