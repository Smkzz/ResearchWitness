# Research Verification Benchmark: implementation specification

**Status:** proposed protocol specification; NOT a frozen experiment or a completed benchmark.  
**Plan:** `RW-PLAN-2026-10-24`, packages RW-04, RW-05, RW-10 and RW-11.

## Research question

At the same declared resource budget and false-alarm tolerance, does source-bound
claim compilation plus bounded adversarial search produce more independently
replayable, source-supported discrepancy findings than simpler frozen baselines?
Distinguish this question from synthetic checker correctness and general scientific
truth. No current score is supplied by this specification.

## Three separate evaluation tracks

1. **Certificate replay:** give a formalization and witness/certificate; measure
   sound acceptance, rejection of corrupt certificates, supported scope, resource
   bounds and deterministic replay. Synthetic mutation tests belong here.
2. **Source interpretation:** give captured source bytes; measure extracted coverage,
   omitted relationships, correct scope/operands, false formalizations, anchors,
   version matching and appropriate abstention against source-backed labels.
3. **End-to-end discovery:** give allowed source material without target labels;
   measure correction-backed/source-supported findings, false alarms, missed target
   relationships, acquisition failures, abstention and cost per defensible finding.

Do not aggregate these into an unexplained single accuracy number. A formally
correct witness for a mistranslated claim is a failure in tracks 2/3.

## Data partitions and labels

Partition at work-family level, conservatively grouping article versions,
corrections, supplements and identified shared datasets. Maintain development,
exposed demonstration and sealed confirmatory partitions. Existing v1/v2 cases,
old candidate investigations and their derivatives are development material.
Known previous custody deviations remain excluded as previously recorded.

Positive labels need the exact source/version, scope and independently checkable
error mechanism; a correction notice alone is insufficient. Negative labels need
explicit source-valid arithmetic/scope. Unresolved cases form a separately reported
stratum, not convenient negatives or silently discarded failures. Store provenance,
exposure, license, family and adjudication modality for each label.

An isolated custodian controls identities/labels. Separate agents in the same
workspace are not isolated. Tests must demonstrate forbidden reads/egress are
blocked before protected data is mounted. Developers get aggregate receipts only.
Do not claim public articles are absent from a model's training data: procedural
holdout isolation does not establish model-pretraining independence. Report this
limitation and include newer/publication-date strata where feasible. Redaction is
not a guarantee against memorization. Provider use must also satisfy data-use and
spending permissions before any sealed content is transmitted.

## Frozen baselines and ablations

Compare an exact pinned historical/current deterministic baseline, the integrated
deterministic implementation, source compiler without adversarial search, and
compiler plus bounded adversarial search. Use identical admissible inputs, resource
caps and scoring. An optional ordinary AI-screening arm uses a pinned model/prompt
only if actually available without unauthorized cost; record an unavailable arm.
Do not advertise a comparison to tools or models that were never executed.

Cache and hash nondeterministic proposal outputs, including model/version settings
and unavailable identifiers. Certificate replay must be deterministic even when
proposal generation is not. A repeat of a cached model response tests replay,
not independent live-model reproducibility.

## Measures and denominators

Record every attempted work, every acquired/eligible/parsed work, tables and
source-labeled relationships. Reconcile exclusions, missing sources, parser refusals,
unsupported mechanisms, completed checks, candidates, confirmed labels, unresolved
cases and timeouts. Count independent works/families separately from correlated
rows. Report conditional extraction/checking performance and whole-pipeline yield.

Primary measures are end-to-end detection of eligible positive works and the
false-alarm rate among independently supported negative works under a fixed
resource envelope. Also report relationship recall/precision where labels are
complete, source-correctness, abstention and coverage, elapsed time, calls/tokens,
compute and marginal cash cost. A partial reference census cannot support full
recall. Missing/failed inputs cannot simply disappear from the end-to-end denominator.

Predeclare interval estimation and paired comparison at work-family level;
account for clustering instead of treating thousands of rows as independent papers.
Use a deterministic resampling seed if resampling is used. Report the actual
sample size and uncertainty, including zero-event uncertainty. "Zero observed
false alarms" is never a universal zero-error claim.

## Prospective registration engineering

The [RW-04D registration validator](RESEARCH_STUDY_REGISTRATION.md) formalizes
an offline **draft** declaration and its canonical hash. Its companion
[JSON Schema](../schemas/research-registration.v1.schema.json) documents the
versioned contract; [the synthetic pilot](../examples/synthetic-study-registration/draft.json)
illustrates it without using real papers or sealed labels. The output
`VALID_DEVELOPMENT_DRAFT_NOT_SEALED` is **not** evidence of qualified custody,
pre-outcome public timestamping, power calculation, independent validation or
completed scientific evaluation. Only an independently held, time-anchored
declaration frozen before result access can later become an actual preregistration.

## Development-only exact statistical diagnostics

[RW-04E](EXACT_FAMILY_ANALYSIS.md) implements the selected positive-family
exact discordance test and conservative Bonferroni CP negative-family harm
bound on already exposed RW-04C receipt declarations. It requires the full
registered denominators, exact arm identities and equal resource budgets;
missing and unresolved eligible families yield inconclusive statistics.
Numerical thresholds alone do not authenticate records, evidence
independence, valid sampling power, qualified custody or scientific accuracy.
The example's legacy 15-work minimum cannot support a 5-point harm upper
bound with zero observed false alarms; 86 independent negative families
are required in that particular zero/zero scenario.

## Finite primary-power scenario diagnostics

The [RW-04F planner](POWER_FEASIBILITY.md) computes exact hypothetical
paired-positive family rejection power from two declared mutually
exclusive discordance rates; it does **not** establish power from synthetic
or source-unreviewed tests. The negative-family calculation gives only
the conservative zero/zero-alarm feasibility requirement and shows why
the probability of observing no alarms matters. Full paired negative
joint-alarm distribution, safety pass probability, missingness and work-family
dependence must be estimated on separately reviewed exposed development
data and justified *before* the confirmatory freeze. Do not count a
hypothetical 215-family total as a powered empirical protocol.

## Sampling and success gates to freeze before evaluation

The RW-04 agent must produce a versioned registration containing:

- primary endpoint, practical improvement threshold and tolerated false-alarm rate;
- expected baseline rates, paired/family-level analysis and a justified sample-size
  calculation or a clear pilot-only designation when evidence/resources are limited;
- eligible mechanisms, strata, source/license rules, family grouping and exclusions;
- development and confirmatory selection order, reserve policy and exposure history;
- per-case and total call/time/memory/spending limits, stopping rules and tie handling;
- hypotheses/ablations, confidence level, multiplicity handling and claim wording;
- exact baseline/candidate/protocol/model/prompt/certificate commitments;
- independent adjudication procedure, disagreement handling and custody permissions.

Choose these before confirmatory selection/output exposure, not after seeing a
favorable score. Unknown planning assumptions must be explicit. The legacy v1.3
minimum of one untouched eligible positive plus 50 accepted negative relationships
across 15 independent works is preserved for that qualification only; it does not
establish adequate power for the new comparative question. Do not inflate the
sample count with repeated rows or promise a fixed research conclusion.

## Running, failures and finite iteration

Development experiments have a declared maximum number of candidates and revisions.
Stop at the registered budget; select a candidate or document a null result.
Freeze that candidate before the custodian selects/runs the confirmatory frame.
No developer inspection of reserved case-level output, no tuning on interim results,
and no repeated holdout attempts until success. A needed protocol/candidate revision
uses a new registration and fresh eligible material after preserving the old result.

Record infrastructure invalidations, source failures and scientific failures
separately. Expose only permitted aggregates. An inaccessible source is not evidence
of correctness or absence of a correction. Once identities/labels/outputs have been
exposed, preserve that status even after filesystem cleanup.

## Completion and reporting

A completed benchmark can support improvement, no improvement or an inconclusive
comparison. Report all three honestly. Scientific promotion requires the predeclared
statistical and practical gates plus defensible source correspondence, not merely
green software tests. Export enough protocol/code/aggregate evidence for replay
without releasing private labels, protected identities or unlicensed full text.
