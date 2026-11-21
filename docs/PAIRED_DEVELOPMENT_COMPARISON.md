# Paired development comparison (RW-04C)

This tool compares two *declared* development result ledgers under the same
externally pinned registry, scheduled works and identical declared per-work
resource limits. It uses the existing strict receipt scorer for each arm.
It **does not execute a model or checker**, revalidate source evidence,
authenticate scientific labels, guarantee work-family independence or measure
general research precision/recall.

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
- Only accepted refutations have a replay profile. A completed non-detection
  or clean negative cannot yet be verified, so replay-bound reports are
  normally `incomplete`; unlocking that needs a separately reviewed replay
  profile for non-alarm outcomes (for example deterministic re-execution of a
  frozen arm), not a looser counting rule.
- Pin, evidence-root, case-collision and byte-budget failures still fail closed.
  Labels, targets and source-correspondence fields remain declarations that
  can only demote a replayed refutation.

Without the evidence arguments the report is the unchanged declaration-only
`rw-development-paired-comparison.v1` with `aggregation_evidence:
declaration_only`.

## Limitations and next steps

Resources are compared from supplied declarations, not attested measurements.
Original-source and certificate verification must be independently implemented
and replayed before scientific claims. RW-05 requires separately authorized
protected custody and source-reviewed labels; RW-10 needs a preregistered
statistical analysis with appropriate independence, power, stopping and effect
thresholds. Do not tune after the holdout is exposed or silently reuse
developer-exposed cases as protected material.
