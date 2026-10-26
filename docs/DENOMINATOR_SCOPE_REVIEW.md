# Denominator scope: development-source reviewer packet (RW-01J)

**Status:** checkout-only engineering development capability, not a scientific
truth label, publisher authentication, isolated custodian or statistical
benchmark. All bundled demonstrations/tests are synthetic and exposed.

## Why

The existing JATS percentage detector identifies numerical relationships and
potential denominator source facts. Original-byte offsets and a correct
percentage calculation cannot establish whether a reported denominator
matches the scientific population, group, timepoint, analysis set or
percentage base. The prior RW-01I trace already makes alternative source
facts visible without adjudicating them.

This tool creates a **reviewer-facing packet** from RW-01I source facts and
original XML anchors, without the detector's selected denominator, arithmetic
result, status or numeric preference. Facts are ordered by original XML position,
not by a detector priority. A packet still exposes the printed numbers and only
relations discovered by the existing detector; it is therefore **not**
independently complete or a truly blinded scientific research corpus.

Two separately supplied reviewer submissions can then be checked for complete
coverage, source-fact IDs and stated scope dimensions. Agreement remains a
declaration, never independent scientific truth or reviewer-authenticated
independence.

## Offline workflow: private files

Use a developer-exposed or properly licensed source whose complete original
SHA-256 has been independently retained. **Do not commit real source content,
private packets or reviewer statements to the public repository.**

From the repository checkout:

    python -m tools.denominator_scope_review --action prepare --source PATH_TO_SOURCE.xml --expected-source-sha256 ORIGINAL_SOURCE_SHA256 > PRIVATE_packet-envelope.json

    python -m tools.denominator_scope_review --action reconcile --source PATH_TO_SOURCE.xml --expected-source-sha256 ORIGINAL_SOURCE_SHA256 --packet PRIVATE_packet-envelope.json --expected-packet-sha256 PACKET_SHA256_FROM_PREPARE --review-a PRIVATE_review-a.json --review-b PRIVATE_review-b.json > PRIVATE_reconciliation.json

The prepare command emits an envelope with fields `packet` and
`packet_sha256`. **Supply that entire envelope** to reconcile. Save the
digest outside this output before relying on either review. A hash alone
neither authenticates source origin nor proves when a review occurred.
This program prints to stdout/stderr only; it does not download, run
models, contact authors, alter original source or spend money.

### Reviewer submission

An input review JSON must have exactly these top-level fields:

- `schema_version` = `rw-development-denominator-scope-annotation.v1`,
  `packet_sha256`, a reviewer-supplied `reviewer_id`,
  `review_method` (one of `manual_source_reading_declared`,
  `ai_assisted_development`, `synthetic_demonstration`),
  Boolean `independence_declared`, and `rows`.
- `rows` contains **one entry in packet order for every discovered relation**,
  including unsupported/absent fact cases. Each row has `relation_id`,
  `decision` (`same_scope_proposed`, `different_scope_proposed` or
  `unresolved`), `selected_fact_id` or null, `basis_fact_ids`, a
  five-field `scope_dimensions` object and a substantive rationale
  of 35–600 characters.
- The five dimensions are `population`, `group`, `timepoint`,
  `analysis_set` and `percentage_base`. Each value must be one of
  `explicitly_same`, `explicitly_different` or `unstated`.
  A same-scope proposal must declare **all five explicitly same**.
  Different-scope requires at least one explicitly different. Missing
  source facts cannot support a positive or negative assessment; they
  must be unresolved. Only captured fact IDs can be cited.
- Reviewer display names and independence declarations are **self-reports**,
  not proof of authorship, separate reading, qualifications or isolation.
  A reviewer must independently inspect the original cited source and
  provide actual scope reasoning; this tool cannot establish that they did.

Example **unresolved** row shape (repeat for every packet relation):

    {
      "relation_id": "REPLACE_WITH_ACTUAL_PACKET_RELATION_ID",
      "decision": "unresolved",
      "selected_fact_id": null,
      "basis_fact_ids": [],
      "scope_dimensions": {
        "population": "unstated",
        "group": "unstated",
        "timepoint": "unstated",
        "analysis_set": "unstated",
        "percentage_base": "unstated"
      },
      "rationale": "Synthetic example only; scientific source scope was not established."
    }

The suite at `tests/test_denominator_scope_review.py` generates complete
synthetic A/B submissions for all three relationships in the developer
fixture. Do **not** attribute those fictional records to human reviewers.

## Decision semantics and fail-closed behavior

The reconciler requires an externally pinned source digest and packet
digest, recreates the packet from original source bytes, then checks all
review rows and citation IDs. Missing/extra/duplicate annotations, invented
facts, invalid JSON keys, stale pins and unsupported reviewer data are
rejected rather than repaired. Numeric correspondence is **never used**
to choose a scientific denominator.

Per relation, it emits one of:

- `DECLARED_CONCORDANCE_NOT_AUTHENTICATED` — matching structured opinions,
  not authenticated independence or scientifically correct scope.
- `BOTH_DECLARED_UNRESOLVED` — two explicit abstentions.
- `IDENTICAL_REVIEW_RECORDS_REQUIRE_INDEPENDENCE_CHECK` — word-for-word
  copied rows, even under different claimed reviewer names.
- `REVIEWER_DISAGREEMENT_OR_INCOMPLETE` — opinions or scope dimensions differ.
- `VISIBLE_BASE_CONFLICT_REQUIRES_ADJUDICATION` — competing printed
  denominator values, overriding even concordant opinions.

The entire output retains `scientific_truth_established: false`,
`reviewer_independence_authenticated: false`,
`source_origin_authenticated: false` and
`protected_custody_qualified: false`. Source fact IDs and spans are
structural references, **not proof that citations mean what the reviewer
claims**. Same fact with different population interpretation remains
unresolved, not a winner chosen by an arithmetic match. Missing relationships
from the detector are not silently counted as negative examples.

## Real-evidence qualification still missing

To create research-grade development labels, a separate authorized process
must capture legally usable original-source/version records, publication
and correction history, work-family exposure, and reviewer modality.
Genuinely separate qualified reviewers must substantively inspect full
context, including methods, changing populations, missingness, footnotes,
alternative denominator bases and conflicting evidence. An independent
adjudicator must resolve disagreements with recorded reasons; copied AI
persona output is not independence. Never copy protected material into
developer fixtures. A later supervised, sealed confirmatory evaluation
requires distinct RW-03/RW-05 authority and evidence.

**No new real independently reviewed corpus is supplied in RW-01J.**
The larger legacy denominator resolver stays separate until actually
labelled development comparisons show its applicability and harms.
See [source trace](JATS_DENOMINATOR_TRACE.md),
[development benchmark](BENCHMARK_PROTOCOL.md) and
[agent plan](EXECUTION_STATE.json).
