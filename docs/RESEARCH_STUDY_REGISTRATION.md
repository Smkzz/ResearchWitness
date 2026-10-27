# Research study preregistration draft — RW-04D

**Scope:** Research design declaration and engineering validation. The contract
does **not** freeze an experiment, verify statistical power, grant custody
access, authenticate labels, inspect a sealed holdout, buy services or certify
scientific improvement. No human opinion is required for routine protocol
design; independent protected data/safety gates remain mandatory.

## What is implemented

`tools.research_preregistration` validates a versioned, strict, bounded JSON
design declaration using the existing offline benchmark parser. The runtime
also verifies constraints that JSON Schema cannot establish alone: the two
arms' commitments differ; model and prompt hashes match their declared kind;
the exact paired test is preselected; primary+safety alpha allocations do not
exceed 0.05; source-family independence is an explicit selection rule;
declared resources and stopping rules are fixed; and protected identities
are absent from development records.

Synthetic example:

```text
python -m tools.research_preregistration examples/synthetic-study-registration/draft.json
```

The declaration is also described by
[the JSON Schema](../schemas/research-registration.v1.schema.json).
It emits one canonical, LF-terminated JSON receipt with a
`canonical_registration_sha256`. Re-running with
`--expected-registration-sha256 HASH` checks an externally retained
commitment. Hashes prove byte identity, not *when* the protocol was adopted.

The committed example is **pilot_only**, uses invented study IDs and
synthetic arm hashes, no paid API calls and no protected material. It is NOT
a confirmatory registration or an executable study. A validator receipt
always reports `VALID_DEVELOPMENT_DRAFT_NOT_SEALED`, even when
`designation` says `confirmatory_intended`; it is never a custody
qualification and does not certify sample size/power.

## Predeclared design obligations

Registration requires exact primary endpoint (eligible positive-work-family
detection) and separate safety endpoint (eligible negative-work-family false
alarm *emission*), complete work-family denominator accounting, selected
family-version grouping, source and license eligibility and exclusion rules,
two distinct implementation identities, allocated one-sided harm/primary
error levels and a practical effect threshold. Unknown/error/abstained work
must remain in reporting bounds, never disappear as clean negatives.

The current declaration uses:
- exact paired discordance for the positive-family comparison, with
  familywise preallocated alpha;
- one-sided negative-family harm bound at the separately allocated alpha;
- **one** confirmatory evaluation and **zero** interim sealed looks;
- explicit maximum development revisions and run invalidation rules;
- zero incremental authorized spending and no protected-data collection.

A statistical design has to specify a justified power/sample-size model,
assumptions about the baseline and discordant rates, how clustering and
multiplicity affect intervals, and how missing results will be handled.
This CLI validates that a written justification *exists*, **not** that its
mathematics or anticipated error rates are correct.

## Custody and scientific claims

The historical v1.3 legacy gate is at least one genuinely untouched
correction-backed positive and 50 independently source-reviewed correct
negative relationships across 15 independent works. A broader paired
research design normally needs more data, depending on effect and power;
meeting these minimums is not evidence of adequate study power.
Public or development-exposed sources cannot become untouched by
moving them into a different folder. Source identity, source license,
label adjudication, independent custody and scientific applicability
must be verified separately.

The current registration **must** say `not_qualified`,
`not_collected`, `identities_in_developer_ledger=false` and
`exclude_historical_and_developer_exposed`. Later sealed work needs
a separately authorized, isolated custodian and newly versioned state.
Do not put protected identities/labels in this public repository or
in external AI-provider prompts. Model agreement is not ground truth.

For actual pre-registration, deposit the canonical declaration digest
and protocol text with a genuinely independent timestamp/custodian
*before* confirmatory source selection or any output exposure, record
any deviations and never retune a used holdout. The present CLI does not
submit or timestamp externally, and the connected software has not
performed any sealed experiment.

## RW-04E: executable development-only numerical checks

The [exact family analysis](EXACT_FAMILY_ANALYSIS.md) executes the original
draft's selected exact paired positive test and conservatively outward-bounded
Clopper-Pearson negative-family harm constraint over declared RW-04C receipts.
It independently replays the declaration/paired inputs, not source truth,
sealed custody or chronological preregistration. A qualifying statistical
calculation on invented data always retains `scientific_superiority_established=false`.
Power and appropriate actual sample selection still require a separate
pre-outcome design. In the zero/zero-alarm case with alpha 0.025 and tolerated
5-point harm, at least 86 independent negative families are necessary, not
the 15-family historical legacy minimum.

## RW-04F: hypothetical family-level power calculation

[RW-04F](POWER_FEASIBILITY.md) binds a separately pinned RW-04D study
*draft* to a strict source-free invented probability scenario. It computes
exact unconditional positive-family discordance-test power with the
declared practical improvement constraint. The negative-family calculation
addresses **only** zero/zero false-alarm feasibility, not the actual
probability of passing the safety test with mixed alarm patterns. In the
illustrative scenario, the first 80%-powered positive size is 129
independent families; 86 zero/zero-safe negative families would be
silent together only about 17.6% of the time under the invented
0.98 per-family joint silence model. Combined power, empirical sampling
and independent custody remain unqualified; do not retroactively promote
this draft into a real preregistration.

## RW-04G: source-free full paired safety and combined power

The [joint study planner](JOINT_POWER_FEASIBILITY.md) uses RW-04D's
unchanged primary alpha, practical gain, Bonferroni Clopper-Pearson
safety alpha and harm margin. Four invented within-negative-family
alarm probabilities produce an **exact** paired marginal count
distribution. The primary and negative safety power computations
are combined only under an explicit invented cross-stratum
independence assumption. The original 129-positive/86-negative
illustration yields **33.85% combined** rather than 80% primary-only
success probability. This is a software model, not real scientific
power, an authenticated independent corpus or an actual preregistration.

## Next packages

RW-04: implement declared baseline source/certificate replay, independent
source-backed labels and an actual, prejustified statistical test/power
plan with missingness and clustering rules. RW-03: protect custody execution
with separately qualified real isolation. RW-05: curate an actually untouched,
source-pinned set under that isolation. RW-10/RW-11: freeze one candidate,
run one registered evaluation and produce permitted aggregates. A
negative/inconclusive outcome is valid research; no new scientific
breakthrough is claimed by building the registration template.

## Exact preregistered analysis choices (draft fields)

The draft's primary estimand is the candidate-minus-baseline **positive-family
successful detection rate**. Its one-sided test is the exact conditional paired
discordance test: among eligible positive families where *exactly one* method
succeeded, under the no-advantage null, candidate-only wins follow a Binomial
(n discordant, 1/2) tail. If there are no discordant families, there is no
primary evidence of improvement. Statistical significance must be below the
preallocated primary alpha **and** the observed family-level detection rate
improvement must meet the declared minimum practical gain.

The safety estimand is the candidate-minus-baseline **negative-family emitted
false-alarm rate**. The declared one-sided upper bound method uses a Bonferroni
union bound of exact Clopper–Pearson marginal binomial intervals: at each
preallocated safety alpha, take the candidate upper bound with tail alpha/2
minus the baseline lower bound with tail alpha/2. It is conservative and
requires independently sampled work families; dependence within a family is
handled by making the family the unit. It is not a substitute for genuine
source-backed labels. The bound must be *no greater than* the prespecified
maximum allowable increase, including zero. An unknown or incomplete data
stratum cannot be silently omitted; the preregistered missingness rule can
force an inconclusive result.

The success decision requires **both**: one-sided primary significance and
practical gain, **and** the safety upper bound within the declared margin.
These are specified algorithms and thresholds, not algorithms executed by this
draft validator. A later qualified statistical runner must implement and test
them independently against established references before scientific promotion.

The example's phrase “at most five percentage points” matches its safety
margin of 1/20. A safety margin of 1 is rejected as vacuous, although *any*
permitted margin still needs separate scientific justification and approval as
a justified design choice, not necessarily human opinion.

JSON Schema checks a structural subset. Python additionally rejects JSON
numeric 1.0 in integer slots, compares distinct arm commitments, constrains
fractions and alpha sums, and checks other field interactions not expressible
in standard JSON Schema without nonportable data-dependent extensions.
A schema-valid object is **not** valid for this plan unless Python validation
also passes. The receipt still remains draft-only, with zero evidence of actual
pre-outcome timestamping or sealed custody.
