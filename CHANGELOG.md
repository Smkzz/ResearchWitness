# Changelog

## 0.3.0.dev0 — verifier-wave integration candidate — unreleased

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
