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

## Limitations and next steps

Resources are compared from supplied declarations, not attested measurements.
Original-source and certificate verification must be independently implemented
and replayed before scientific claims. RW-05 requires separately authorized
protected custody and source-reviewed labels; RW-10 needs a preregistered
statistical analysis with appropriate independence, power, stopping and effect
thresholds. Do not tune after the holdout is exposed or silently reuse
developer-exposed cases as protected material.
