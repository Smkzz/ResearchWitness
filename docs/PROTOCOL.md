# ResearchWitness v1 protocol

This offline protocol checks a supplied witness against a supplied mathematical
formalization and preserves the exact inputs. It does not certify correspondence
to a publication or scientific applicability. [The development plan](DEVELOPMENT_PLAN.md)
does not silently change this protocol or the runtime result vocabulary.

## 1. Case bundle

A case contains `case.json` plus manifested source artifacts, source-quote text,
correction-status evidence, witness JSON and optional supplementary artifacts.
Only manifested artifacts participate in the artifact inventory and private export.
The core does not execute source/case code or contact external services.

## 2. case.json

Top-level v1 fields are `schema_version`, `case_id`, `artifacts`, `source`, `claim`,
`witness_artifact`, `unresolved_objections` and `disclosure`. Reviewer votes, approval
flags and contact authorization are intentionally absent. Autonomous agent authority
belongs to [AGENTS.md](../AGENTS.md), not to a proof primitive in this schema.

### Source

`source` records `artifact`, `text_artifact`, `identifier`, `version`, `capture_status`
and `correction_check`. Capture is `synthetic`, `captured` or `unverified`: contextual
metadata, never authenticated origin. Correction status records a date, `unchecked`,
`none_found` or `present`, and manifested evidence. Age/status affects context,
not the mathematical verdict.

### Claim and witness

A claim has an atomic ID, statement, narrow scope, explicit assumptions/exclusions,
a zero-based UTF-8 byte-offset quote anchor and allowlisted formalization. Anchor
matching does not authenticate the source or verify its scientific interpretation.
`witness_artifact` references checker-specific JSON; it cannot override the target
bound/formalization supplied by the claim. See [EXPRESSION_DSL.md](EXPRESSION_DSL.md)
for closed rational AST evaluation at one in-domain point and its work limits.

### Finite PMF arithmetic

`finite_pmf_bound` supports exact probability or expectation for an explicit finite
categorical sample space: the Cartesian product of at most 8 variable domains and
at most 256 states. Witness atoms are distinct positive masses written as exact
rationals; absent states have zero mass, and the total must equal one.

An event is a union of partial assignments. Empty event list means empty event;
an empty assignment means the entire space. Overlap counts once. `at_most`/`at_least`
bounds include equality, which does not refute either bound.

```json
{
  "kind": "finite_pmf_bound",
  "operation": "probability",
  "domains": {"coin": ["H", "T"], "weather": ["sun", "rain"]},
  "event": [{"coin": "H"}, {"weather": "sun"}],
  "relation": "at_most",
  "bound": "2/3"
}
```

Expected payoff requires a rational payoff for every state exactly once and sums
mass times payoff. These checks validate supplied finite arithmetic, not inference
from observations, empirical distributions or population/generalized conclusions.

## 3. Formalization results

Checker results are `REFUTED_FOR_FORMALIZATION`, `NO_REFUTATION_AT_WITNESS` or
`INCONCLUSIVE_INTERVAL`. Package decisions map the first to
`FORMALIZATION_COUNTEREXAMPLE_VERIFIED` and preserve the other two names.
A positive establishes a strict contradiction for that formalization/witness only.

It does not establish a false paper, known global optimum, unchanged source versions,
a failed broader theorem, contact authority or misconduct. Reports always retain:

```text
paper_error_established: false
external_actions: OUT_OF_SCOPE
```

Completed evaluation can return no refutation. An unsupported interpretation must
not be reduced to an unrelated supported check to manufacture a positive.

## 4. Context flags

Context includes `BUNDLE_NOT_EXTERNALLY_PINNED`, `SOURCE_CAPTURE_UNVERIFIED`,
`SYNTHETIC_SOURCE`, `FUTURE_CORRECTION_CHECK`, `STALE_CORRECTION_CHECK`,
`CORRECTION_STATUS_UNCHECKED`, `CORRECTION_PRESENT`, `EMPTY_CORRECTION_EVIDENCE`
and `OPEN_OBJECTION`. Context does not invalidate exact arithmetic; arithmetic
does not clear a source-interpretation objection. AI consensus cannot clear either.

## 5. Digests

`subject_sha256` binds schema/case identity, source metadata, claim/scope/assumptions/
exclusions/anchor/formalization, witness identity/hash, correction-evidence identity/
hash and objections. Unrelated supplementary artifacts do not change it.
`bundle_sha256` binds complete `case.json`, including the artifact manifest.
A separately preserved `--expected-bundle-sha256` pin detects later coherent changes;
neither digest authenticates the original evidence or makes it true.

## 6. Exports

`pack` writes a deterministic private ZIP containing manifested artifacts and
canonical `case.json`, `report.json` and `contact-readiness.json`. Generated root
filenames and directory-prefix collisions, including case variants, are reserved.
Unrelated files are ignored; existing ZIP outputs are not overwritten. Entries use
sorted names, fixed metadata and ZIP_STORED compression. Aggregate artifact limits
and shared intake/export validation apply before prepared outputs are created.
Do not manifest private material merely because the exporter can package it.

## 7. Timeline protocol

The separate hash-chained timeline binds to the case subject. Event kinds are
`INQUIRY_RECORDED`, `AUTHOR_POSITION_RECORDED`, `CORRECTION_NOTICE_RECORDED`,
`REVISION_WITNESS_RECHECK`, `CASE_WITHDRAWN` and `CASE_REOPENED`. These are recorded
assertions, not authenticated facts. An author's position or correction notice is
not proof. An old witness ceasing to refute a revision is not global correctness.

Revision verdicts remain `OLD_WITNESS_STILL_REFUTES_REVISION`,
`OLD_WITNESS_NO_LONGER_REFUTES_REVISION` and `REVISION_CHECK_INCONCLUSIVE`.
Recording an event does not send any message or authorize external action.

## 8. Extending the protocol

New checkers must remain deterministic, bounded, explicitly scoped and machine-
checkable. General model judgments may propose bundles but cannot become trusted
proof primitives. Changes need versioned compatibility decisions and regressions;
a plan or broader agent autonomy does not itself change installed schema semantics.
