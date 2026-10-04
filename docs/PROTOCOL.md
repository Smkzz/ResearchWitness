# ResearchWitness v1 protocol

ResearchWitness v1 is an offline protocol for checking a supplied witness against a supplied mathematical formalization and preserving the exact inputs that produced the result.

The protocol does **not** certify that the formalization faithfully represents a publication. That boundary is explicit in every report.

## 1. Case bundle

A case directory contains:

- `case.json` — the structured verification target;
- one or more manifested source artifacts;
- a text artifact containing the quoted source anchor;
- a correction-status evidence artifact;
- a witness JSON artifact;
- optional supplemental artifacts.

Only manifested files participate in the bundle digest and private export.

## 2. `case.json`

The v1 top-level fields are:

```text
schema_version
case_id
artifacts
source
claim
witness_artifact
unresolved_objections
disclosure
```

Reviewer identities, reviewer votes, approval flags and contact authorization are intentionally absent.

### Source

`source` records:

```text
artifact
text_artifact
identifier
version
capture_status
correction_check
```

`capture_status` is contextual metadata:

- `synthetic`
- `captured`
- `unverified`

It is never promoted to authenticated provenance.

`correction_check` records a date, one of `unchecked | none_found | present`, and a manifested evidence artifact. Its age/status becomes a context flag rather than changing the mathematical result.

### Claim

A claim contains:

- an atomic identifier;
- the natural-language statement;
- a narrow scope string;
- explicit assumptions;
- explicit excluded implications;
- a byte-offset source quote anchor;
- an allowlisted formalization.

The anchor is verified against the supplied text bytes. It does not authenticate the publication.

### Witness

`witness_artifact` points to checker-specific JSON. A witness cannot override the target bound or formalization supplied by the claim.

### Finite PMF arithmetic

`finite_pmf_bound` formalizations support two exact operations over an explicitly declared finite categorical sample space. The sample space is the Cartesian product of `domains`; it may contain at most 256 states across at most 8 variables. The witness lists distinct positive-mass atoms using exact rational strings. Unlisted states have probability zero, and the listed masses must sum exactly to one.

For an event probability, `event` is a union of partial assignments. An empty event list denotes the empty event, while an empty assignment in the list denotes the whole sample space. Overlapping clauses count each atom once. `relation` is `at_most` or `at_least`; equality satisfies either bound and therefore produces no refutation.

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

For an expected payoff, `payoffs` must assign an exact rational value to every state in the declared sample space exactly once. The checker sums `probability × payoff` over the supplied PMF. Both operations validate all PMF masses and arithmetic exactly; neither makes an observation-to-distribution inference.

The reported result is scoped to arithmetic over that supplied finite PMF and formalization. Empirical validity, sampling assumptions, population probabilities and broader generalized conclusions remain outside the checker.

## 3. Formalization results

All checkers return one of:

```text
REFUTED_FOR_FORMALIZATION
NO_REFUTATION_AT_WITNESS
INCONCLUSIVE_INTERVAL
```

The package-level `decision` maps these to:

```text
FORMALIZATION_COUNTEREXAMPLE_VERIFIED
NO_REFUTATION_AT_WITNESS
INCONCLUSIVE_INTERVAL
```

`FORMALIZATION_COUNTEREXAMPLE_VERIFIED` means the checker established a strict contradiction for the exact supplied formalization/witness pair.

It does not mean:

- the paper is false;
- the global optimum is known;
- every version of the source contains the same claim;
- the broader theorem fails;
- an author should be contacted;
- misconduct occurred.

For that reason every report contains:

```text
paper_error_established: false
external_actions: OUT_OF_SCOPE
```

## 4. Context flags

Context is reported separately from arithmetic. Examples include:

```text
BUNDLE_NOT_EXTERNALLY_PINNED
SOURCE_CAPTURE_UNVERIFIED
SYNTHETIC_SOURCE
FUTURE_CORRECTION_CHECK
STALE_CORRECTION_CHECK
CORRECTION_STATUS_UNCHECKED
CORRECTION_PRESENT
EMPTY_CORRECTION_EVIDENCE
OPEN_OBJECTION
```

A context flag cannot change a valid arithmetic counterexample into a non-counterexample. Conversely, exact arithmetic cannot clear a source-interpretation objection.

## 5. Digests

### Subject digest

`subject_sha256` commits to the verification question and its direct inputs:

- schema/case identity;
- source metadata;
- claim text, scope, assumptions, exclusions, anchor and formalization;
- witness artifact identity/hash;
- correction-status evidence identity/hash;
- unresolved objections.

Supplemental manifested artifacts do not change the subject digest.

### Bundle digest

`bundle_sha256` commits to the complete `case.json`, including the full artifact manifest.

A caller may preserve this value outside the bundle and later pass it as `--expected-bundle-sha256`. This detects a coherent rewrite after the pin was created.

Neither digest authenticates the original source.

## 6. Exports

`pack` writes a deterministic private ZIP containing only:

- manifested artifacts;
- canonical `case.json`;
- canonical `report.json`.

Unrelated files in the case directory are ignored. Existing output files are not overwritten.

Equal entries are written with sorted names, fixed metadata and `ZIP_STORED` compression mode.

## 7. Timeline protocol

The optional timeline is a separate hash-chained object bound to the case subject.

Supported event kinds:

```text
INQUIRY_RECORDED
AUTHOR_POSITION_RECORDED
CORRECTION_NOTICE_RECORDED
REVISION_WITNESS_RECHECK
CASE_WITHDRAWN
CASE_REOPENED
```

These are records, not authenticated facts. In particular:

- an author-position event is not proof;
- a correction notice is not proof;
- an old witness ceasing to refute a revision is not proof that the revision is globally correct.

The revision result vocabulary is intentionally narrow:

```text
OLD_WITNESS_STILL_REFUTES_REVISION
OLD_WITNESS_NO_LONGER_REFUTES_REVISION
REVISION_CHECK_INCONCLUSIVE
```

## 8. Extending the protocol

A new checker belongs in v1 only if it can produce a deterministic, bounded, machine-checkable result with explicit scope. General LLM judgments may help create candidate bundles but cannot become trusted-core proof primitives.
