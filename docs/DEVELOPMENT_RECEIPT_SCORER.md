# Development receipt scorer - RW-04 initial slice

**Implemented:** `python -m tools.verification_benchmark`.  
**Not implemented:** candidate execution, certificate replay, protected custody,
confirmatory sampling, statistical significance, independent scientific adjudication.
The wider [benchmark protocol](BENCHMARK_PROTOCOL.md) remains a specification;
RW-04 is not complete.

## Purpose and trust

This offline source-checkout tool accounts for separately supplied development
registry/protocol/run declarations. It cannot authenticate who recorded them,
when the pins were created, whether labels/families are independent, whether a
certificate is valid, whether interpretation matches the source, or whether all
actual retries/resources were disclosed. Those are future trusted recording and
verification boundaries, not claims made by this scorer.

Output explicitly says `SUPPLIED_DECLARATIONS_NOT_REPLAYED`,
`DECLARED_FAMILIES_NOT_AUTHENTICATED` and
`scientific_performance_established: false`. Only `synthetic` and
`developer_exposed` registries are supported. Sealed/custody material and paid-run
accounting are refused in this first slice. It never calls a provider, follows a
URL, executes supplied code or writes output files. Protect private development
inputs and stdout; this tool is input validation, not a filesystem/custody sandbox.

## Runnable invented example

From the repository root, after normal source-development setup:

```text
python -m tools.verification_benchmark --registry examples/verification-benchmark/registry.json --protocol examples/verification-benchmark/protocol.json --run examples/verification-benchmark/run.json --expected-registry-sha256 d50970fb826edb1a9f9b1a2f6dbc1489c02ecf885bc7d179ffffcaf1e5281710 --expected-protocol-sha256 d8cbc176ba8d1bc14faa442fc604bb6e9869ce16da656514e00506ff84348713
```

All sources, labels, hashes, certificates and results in this example are invented.
It registers seven works in six declared families, including two versions in one
family. Two work receipts are deliberately missing. It reports recorded positive
family detection 1/2, observed negative-family alarms 1/2 and an alarm-completion
upper bound 2/2. These numbers test accounting, not research performance.

Completed accounting exits 0 even when the run is `incomplete`. Invalid inputs exit
2 with a stable JSON diagnostic on stderr and no scored result. Inspect ledger and
coverage completeness, not just the process exit code. Identical documents and pins
replay byte-identically. Keep genuine pins outside the outcome-producing process;
recomputing pins after inspecting results defeats the intended workflow.

## Input contract

All fields are required and unknown fields are rejected. Schemas are enforced by
bounded Python validators in the module; published JSON Schemas and runner adapters
are still RW-04 work. Each work has one atomic scored target; mixed positive/negative
or mixed eligibility within one family is unsupported rather than silently split.

**Registry (`rw-development-registry.v1`):** `schema_version`, `exposure`, `label_basis`,
`works`. Basis is `synthetic_construction` for synthetic inputs or `source_review`
for developer-exposed inputs; it remains an unverified declaration. Each work:
`work_id`, `family_id`, `source_sha256`, `interpretation_sha256`, `label`, `eligible`,
`exclusion_reason`, `target_id`. Labels are positive, negative or unresolved. Positive
labels need a target ID; other labels require null. Eligible records have null
exclusion reason; ineligible records require an explicit reason. Same source hash
across different declared families is rejected, but other hidden correlation cannot
be discovered from hashes.

**Protocol (`rw-development-protocol.v1`):** `schema_version`, `registry_sha256`,
`implementation_sha256`, `schedule`, `max_elapsed_ms`, `max_calls`,
`max_cost_micro_eur`. Schedule must contain every registered work exactly once,
including exclusions. Budgets are per work; time is positive and the current cost
cap is zero. This format supports one terminal receipt/work, not retries.

**Run (`rw-development-run.v1`):** `schema_version`, `registry_sha256`, `protocol_sha256`,
`implementation_sha256`, `results`. Each result: `work_id`, `source_sha256`,
`interpretation_sha256`, `status`, `alarm_emitted`, `candidate_sha256`,
`certificate_sha256`, `certificate_status`, `source_correspondence`, `target_id`,
`elapsed_ms`, `calls`, `cost_micro_eur`. Duplicate/unknown works are invalid.
Source/interpretation hashes must match the registry. Missing receipts are derived
as `missing`, not deleted from scoring.

Status is completed, abstained, failed, timeout, unsupported, source_unavailable,
budget_exceeded or not_attempted. An alarm requires a candidate hash. Accepted/
rejected certificate declarations require a certificate hash; not_checked requires
null. Source correspondence is supported, contradicted or unresolved. No-alarm
records cannot smuggle candidate/target/certificate acceptance. A work exceeding a
budget must say budget_exceeded and cannot earn detection credit.

## Scoring and completeness

Count each eligible family at most once. A recorded positive detection requires a
completed alarm with accepted certificate declaration, supported source-correspondence
declaration and matching registered target. An alarm on a negative counts even if
the certificate is rejected or processing failed. Thus hiding behind a rejected
certificate cannot remove false alarms.

Missing, failed, unsupported and abstained works remain in the registered family
denominators. Separate unresolved labels and ineligible families from resolved
positives/negatives. Keep receipt completeness separate from completed coverage.
A low observed alarm fraction with incomplete coverage is not evidence of specificity:
the report also gives a conservative completion upper bound for families without an
alarm but with unfinished coverage. The analogous detection bound is reported too.
These completion bounds are **not confidence intervals** and do not measure label
or interpretation uncertainty. Zero denominator yields null, never perfect accuracy.

## Canonicalization, bounds and next work

Commitments are SHA-256 of ASCII JSON using sorted object keys, separators `,`/`:`,
`ensure_ascii=True`, no nonfinite numbers and one terminal LF. Array order is significant
for commitments, although reordering records does not change counts. The supplied
registry/protocol must match externally provided expected pins, and run commitments
must match them and the declared implementation.

The CLI caps each regular single-link input at 8 MiB and rejects symlinks/FIFOs,
invalid UTF-8, duplicate keys, floats/nonfinite numbers, excessive nesting (16),
node count (200,000), scalar strings (4,096) and lists (10,000 works/receipts).
Identifiers are bounded ASCII; hashes are lowercase SHA-256. Counters must be actual
nonnegative integers, not booleans, and both individual/total counters are capped at
2^53-1. Limits apply jointly; reaching one may prevent reaching another maximum.
Direct Python callers already control their own process; hostile arbitrary Python
objects are not an advertised isolation boundary.

Next RW-04 work: a preregistering execution controller, typed adapters to actual
source audits/verifier replay, published schemas, separately controlled adjudication,
resource/certificate binding and a frozen statistical design. Do not use this slice
as evidence that those components exist or that the scientific gate passed.
