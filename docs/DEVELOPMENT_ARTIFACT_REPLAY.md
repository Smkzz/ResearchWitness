# RW-04I: evidence-bound replay of accepted development receipts

**Scope:** Optional checkout-only engineering tool, tools.development_artifact_replay.
No new discovery campaign, source acquisition, model API, paid provider, statistical
power simulation, scientific paper verdict or sealed evaluation is implied.
The existing receipt scorer and installed mathematical verifier are unchanged.
Version 0.3.0.dev0 remains UNRELEASED.

## Problem and corrected boundary

The RW-04A receipt scorer correctly describes certificate status and source
correspondence as **supplied declarations**. A reported accepted certificate
is therefore not evidence that the underlying mathematics was actually replayed.
This opt-in companion checks real evidence before issuing an audited development
score. Invalid or missing accepted evidence fails closed; there is no silent
fallback to declaration-only scoring.

Version one supports **exactly one kind** of accepted mathematical receipt:
one explicitly marked RW-MATH-02 bounded-real source claim, with a canonical
rational point whose exact objective **strictly exceeds** the claimed upper
bound. This is a *formalization-level refutation*. A proof of an upper bound,
a non-refuting point, a generic result from other checker families and an
unmarked prose sentence are not interchangeable and cannot pass this profile.

## Exact input binding

The caller supplies independently retained canonical SHA-256 pins for the
registry, protocol and **complete run**, plus a trusted quiescent evidence root.
RW-04A's schedule, completeness, cost, label and family checks execute first.
The accepted-work set is derived from those pinned run records, not filenames.

For every accepted receipt, the caller stores exactly these four regular files:

    EVIDENCE_ROOT/WORK_ID/source.txt
    EVIDENCE_ROOT/WORK_ID/candidate.json
    EVIDENCE_ROOT/WORK_ID/model.json
    EVIDENCE_ROOT/WORK_ID/point.json

File names are derived from the validated work identifier. No source-supplied
path is opened. Work identifiers must be distinct after case folding. The
root and each work directory must be plain directories; artifact reads reject
symlinks, hard links and nonregular files. An actually trusted, quiescent
parent directory is still necessary; this is not an OS isolation guarantee.

The registry work source hash binds the exact source bytes. The run candidate
hash binds the canonical candidate bytes. For **this profile only**, the run
certificate hash binds the canonical point array, not an upper-bound proof.
The canonical candidate itself binds the exact model bytes. The registry
interpretation hash must equal the full marked source-block hash; this
byte identity does **not** authenticate a reviewer's interpretation.

Only one complete marked block and default compiler hints are supported.
The source-claim compiler regenerates candidate and model, checks all byte
identities, and the installed exact verifier checks the point against the
original model. It must prove a **strictly positive rational violation**.
Equal or negative margins and model-invalid points are not accepted.

## Reproduce locally

Use a trusted directory with the evidence files above. Run:

    python -m tools.development_artifact_replay \
      --registry registry.json --protocol protocol.json --run run.json \
      --evidence-root PRIVATE_EVIDENCE_ROOT \
      --expected-registry-sha256 PIN_REGISTRY \
      --expected-protocol-sha256 PIN_PROTOCOL \
      --expected-run-sha256 PIN_RUN

The first three pins refer to the canonical documents as calculated by
verification_benchmark.commitment. Source, candidate, model and point hashes
refer to the exact raw bytes consumed. A digest held only by the artifact
producer does not prove pre-outcome timing, independent source origin, licence,
original publisher authenticity or scientific truth.

If any accepted receipt has a missing file, substituted model or candidate,
wrong source, forged acceptance, invalid point, ambiguous multiple blocks or
unsupported schema, the tool exits nonzero and prints **no audited score**.
The original declaration-only score remains available separately through
verification_benchmark, honestly labelled NOT REPLAYED.

## Outputs and statistical integrity

The reported original_development_score is exactly the RW-04A output.
Registered works/families, missing outcomes, abstentions, reported costs,
negative-family emitted alarms and logical bounds are never reclassified or
filtered to make the audit look better. A rejected or unchecked alarm still
counts as an emitted alarm in the underlying declaration-only score.

When no accepted record exists, status is no_accepted_records_to_replay:
this is not a claim that mathematical evidence was successfully verified.
For a successful replay each accepted work receives a checked source/model/
point digest chain and exact positive formal violation margin. The report
explicitly leaves independent interpretation, family independence, publisher
provenance, paper errors and protected scientific evaluation **unestablished**.

## Testing and remaining evidence gates

Synthetic-only acceptance includes valid positive refutation, invalid and
repinned points, missing artifacts, altered source and candidate, wrong
formalization, multiple marked blocks, mixed negative alarms, absent families,
external run pin changes, case-insensitive aliases, links, malformed JSON,
CLI failure and optimized-Python parity. No private paper bytes, candidate
labels or correspondence are published as test artifacts.

This bounded engineering step does not unblock RW-01O issue 35, RW-01Q
issue 50, licence decisions, independent source-context evidence or the
RW-03/RW-05 custody gates. Source-free hypothetical power models should not
be substituted for those missing empirical inputs.
