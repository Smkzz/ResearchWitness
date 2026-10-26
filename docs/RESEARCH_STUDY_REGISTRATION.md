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

## Next packages

RW-04: implement declared baseline source/certificate replay, independent
source-backed labels and an actual, prejustified statistical test/power
plan with missingness and clustering rules. RW-03: protect custody execution
with separately qualified real isolation. RW-05: curate an actually untouched,
source-pinned set under that isolation. RW-10/RW-11: freeze one candidate,
run one registered evaluation and produce permitted aggregates. A
negative/inconclusive outcome is valid research; no new scientific
breakthrough is claimed by building the registration template.
