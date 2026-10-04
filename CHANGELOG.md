# Changelog

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
