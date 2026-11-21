# Paired development comparison (RW-04C)

This tool compares two *declared* development result ledgers under the same
externally pinned registry, scheduled works and identical declared per-work
resource limits. It uses the existing strict receipt scorer for each arm.
The default mode does not execute a checker or revalidate source evidence.
Neither mode authenticates scientific labels, guarantees work-family independence
or measures general research precision/recall.

## Inputs and usage

Supply five local JSON files:

- one development-exposed or synthetic `rw-development-registry.v1`;
- `rw-development-protocol.v1` and `rw-development-run.v1` for each arm;
- separately preserved external SHA-256 commitments to the registry and each
  protocol, established before inspecting comparison outputs.

Run `python -m tools.paired_development_comparison --help` for exact flags.
Example form with user-supplied paths and external pins:

```text
python -m tools.paired_development_comparison --registry /path/registry.json --baseline-protocol /path/baseline-protocol.json --baseline-run /path/baseline-run.json --candidate-protocol /path/candidate-protocol.json --candidate-run /path/candidate-run.json --expected-registry-sha256 HASH --expected-baseline-protocol-sha256 HASH --expected-candidate-protocol-sha256 HASH
```

The output is canonical ASCII JSON with one LF. No files are overwritten.
Malformed, mismatched, unpaid-resource or protected-mode submissions fail closed.

## Interpretation

Work families, not rows/versions, are paired units. The shared registry supplies
declared labels, but their authenticity is not established here. A positive family
counts as detected only with an accepted source-supported matching-target receipt.
A negative-family alarm counts at *emission*, even when its certificate is
rejected or the work fails. No-alarm failure, timeout, abstention and missing
receipt are **unknown**, never confirmed clean negatives.

The report gives known paired outcomes and logical lower/upper bounds that include
all unknown families. These are NOT confidence intervals. It deliberately
produces no superiority p-value, trusted scientific accuracy, sealed-holdout
qualification or empirical discovery claim. A completed matrix of declared
results is not a completed independent research study.

## Replay-bound aggregation (RW-04K)

Supplying `--baseline-evidence-root`, `--candidate-evidence-root`,
`--expected-baseline-run-sha256` and `--expected-candidate-run-sha256`
(all four or none) switches the report to
`rw-development-paired-comparison.replay-bound.v1` with
`aggregation_evidence: replay_verified_only`. Each arm's accepted receipts are
replayed with the [RW-04I adapter](DEVELOPMENT_ARTIFACT_REPLAY.md) against that
arm's own, distinct evidence root and externally pinned run hash.

- A family outcome counts only when replay evidence supports it: a positive
  family is detected only by a replayed accepted formal refutation whose
  declared target and source correspondence also match; a negative family has
  an alarm only through a replayed accepted refutation (a verified false alarm).
- Every other eligible family stays in the denominator as **unverified**
  (unknown in the logical bounds): declared non-detections, clean negatives,
  abstentions relabelled as completions, rejected alarms and accepted receipts
  whose bundle is missing, substituted, forged or non-refuting. Per-arm
  replay counts, stable unverified codes and the number of declared-known
  outcomes left unverified are reported.
- The legacy declaration-only summaries are kept beside the counted ones as
  `declared_*_not_counted`, so the effect of excluding unreplayed declarations
  is visible but cannot improve any counted diagnostic.
- This accepted-only profile cannot verify a completed non-detection or clean
  negative, so its replay-bound reports typically remain `incomplete`.
- Pin, evidence-root, case-collision and byte-budget failures still fail closed.
  Labels, targets and source-correspondence fields remain declarations that
  can only demote a replayed refutation.

Without the evidence arguments the report is the unchanged declaration-only
`rw-development-paired-comparison.v1` with `aggregation_evidence:
declaration_only`.

## Frozen-arm replay (RW-04L)

Add `--replay-frozen-arms` **and** all four replay arguments to the paired or
exact analysis CLI. This selects the separate
`rw-development-paired-comparison.frozen-arm-replay.v1` profile; it never falls
back to declaration-only or accepted-only replay.

Before seeing outcomes, pin the two distinct local implementations, the registry
and each arm protocol separately. Obtain the implementation commitments with
`python -c "from tools.development_artifact_replay import frozen_implementation_pins; print(frozen_implementation_pins())"`.
Use the chosen commitments in the protocols and study draft. Each binds its named
arm, the checkout replay/compiler/checker and input helper bytes, and Python
version/implementation/platform metadata. A changed pin or unknown arm is
refused; replay needs a trusted matching checkout/runtime, not supplied code.

- `box-midpoint` evaluates the exact midpoint of the independent closed
  intervals. `box-objective-corner` uses the upper endpoint where the objective
  coefficient is positive and the lower endpoint elsewhere. Both run exactly
  one verified point on the same registered source and under the same declared
  budget. The midpoint can miss a true formal violation.
- Supply the exact registered bytes as `WORK_ID/source.txt` in each arm's
  distinct root, using portable work IDs. The one explicit RW-MATH-02 block
  must compile with default hints to a supported affine box with no additional
  constraints. Its block hash must match the registered interpretation pin.
  Use `marked-claim` as the target ID for positive works; the probe reads
  neither the label nor target. The run pin covers the completed receipt.
- Replay regenerates the result, not just the arithmetic behind a submitted
  alarm. A strict exceedance requires an accepted receipt and hashes of the
  canonical exact compiler candidate and exact point array. Existing
  source-correspondence and target checks still apply to positive detections.
  A no-alarm counts only if **every** member of that family shows a verified,
  completed no-alarm. Missing, rejected, mismatched, unsupported and
  budget-exceeded outcomes do not become known non-alarms.
- The per-arm replay cap is 128 receipts and 32 MiB of source bytes, with
  existing per-file and parser limits and zero provider calls. Re-execution
  exceeding the declared per-work elapsed limit does not count as completed.
  This is bounded local computation, not an OS sandbox or historical timing
  attestation.

The report separates accepted refutations from replayed/unverified non-alarms.
Replay demonstrates what the pinned computation returned, not whether the
historical run took place, whether the registered labels are true, or whether
the narrow marked block faithfully represents a scientific claim.

## Limitations and next steps

Resources are compared from supplied declarations, not attested measurements.
Original-source and certificate verification must be independently implemented
and replayed before scientific claims. RW-05 requires separately authorized
protected custody and source-reviewed labels; RW-10 needs a preregistered
statistical analysis with appropriate independence, power, stopping and effect
thresholds. Do not tune after the holdout is exposed or silently reuse
developer-exposed cases as protected material.
