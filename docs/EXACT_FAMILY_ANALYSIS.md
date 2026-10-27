# RW-04E: exact family-level analysis on exposed development receipts

**Status:** engineering diagnostics only. The implementation is intentionally
incapable of establishing a scientific breakthrough, authenticating a source,
proving reviewer independence, accessing sealed material or declaring a
confirmatory evaluation complete.

This follows [RW-04D's prospective analysis choices](RESEARCH_STUDY_REGISTRATION.md)
and the [benchmark protocol](BENCHMARK_PROTOCOL.md). The CLI in
`tools.exact_family_analysis` replays all five existing RW-04C benchmark
inputs and validates the independently hash-pinned RW-04D *draft* declaration.
It reuses existing source/work family receipt counts; it does not trust a
caller-supplied summarized contingency table.

## Two numerical endpoints

1. **Positive-work-family detection:** use `candidate_only` successes and
   `baseline_only` successes from the full eligible paired positive-family
   population. Among the discordant families (`d = wins + losses`), the
   conditional one-sided exact null tail is
   `P(Binomial(d, 0.5) >= wins)`. If `d = 0`, `p = 1`.
   Compare the **exact integer** tail strictly below the draft's allocated
   primary alpha and independently require the candidate-minus-baseline
   observed family detection gain to meet the prespecified practical threshold.
   No cell/row is incorrectly promoted into an independent family.

2. **Negative-work-family false alarm:** *any emitted alarm*, including a
   rejected certificate, is an alarm event. For every eligible negative
   family, derive the candidate one-sided exact Clopper–Pearson upper endpoint
   at tail `safety_alpha / 2` and the baseline exact lower endpoint at the
   same tail. Bonferroni's union argument makes the **difference**
   `U_candidate - L_baseline` a conservative one-sided harm upper bound.
   The required condition is that this upper bound be no greater than the
   draft's maximum allowed increase. Positive and negative endpoints have
   separately budgeted familywise alpha (combined at most 0.05).

All binomial comparisons use integer arithmetic. Confidence-bound endpoints
are found by outward bracketing on a 40-bit dyadic grid; the reported 12-place
decimal strings are rounded **outward**. The bound is never inward-rounded to
manufacture a favorable threshold comparison. The deterministic scoring cap is
2,048 declared families per endpoint; a larger input remains unassessed.

## Quantitative feasibility: a concrete design gap

For the example's safety alpha of `1/40 = 0.025`, Bonferroni tail per
marginal bound is `1/80 = 0.0125`. If *both* arms emit **zero** alarms and
no negative data are missing, baseline's exact lower bound is zero and
candidate's exact upper bound is

`U = 1 - (0.0125)^(1/n)`.

With 15 independent negative families, `U = 0.253332352...`. With 85,
`U = 0.050246930...`; with 86, `U = 0.049677423...`. Thus **86 eligible,
independent negative work families are necessary** to satisfy the example's
5-percentage-point safety margin **in that zero/zero-alarm scenario**. The
old v1.3 minimum of 50 negative *relationships* across 15 works is not enough
to make this safety assertion by itself. It is not a universal 86-family
sample size: a nonzero baseline alarm rate, different assumptions, missing
families, selection dependence or different margins change the bound.

At primary alpha `0.025`, six candidate-only discordant wins and zero
baseline-only discordant wins yield exact `p = 1/64 = 0.015625`; five
wins yield `p = 1/32 = 0.03125`, which fails that alpha. Neither
example establishes power: a proper power model needs expected discordance
and effect size, adequate positive-family numbers and actually independent
families, specified before confirmatory exposure.

## Fail-closed restrictions

- Missing/incomplete or eligible unresolved families make **both** statistical
  endpoints inconclusive. The scorer does not analyze only favorable complete
  cases or silently promote unresolved cases to negatives.
- Actual declared counts must meet all preregistered positive-family,
  negative-family and negative-relationship minima, separately from the
  statistical thresholds.
- Both arms' exact implementation commitments and resource budgets must match
  the validated registration. Every source/run/protocol must match its external
  pin and the same registered work schedule.
- Entire input registry, source interpretation, certificate acceptance, family
  grouping and reviewer labels remain *supplied declarations*. A synthetic
  numerical pass is explicitly
  `met_on_unverified_development_data`, **never an approval of scientific
  superiority**. It is not a real data sample or protected holdout.
- Results include the exact input/report commitments, counts, omissions,
  zero-spend scope, display rounding method, and explicit FALSE flags for
  source authenticity, family independence, protected custody and scientific
  performance.

## Offline reproducibility

Use permitted local **development** files and separately preserved SHA-256
commitments. The CLI makes no network requests, uses only Python standard
library and existing checkout tools, and does not write output files except
the redirected JSON:

```text
python -m tools.exact_family_analysis \
  --registration PRIVATE_study_draft.json \
  --registry PRIVATE_registry.json \
  --baseline-protocol PRIVATE_baseline_protocol.json \
  --baseline-run PRIVATE_baseline_run.json \
  --candidate-protocol PRIVATE_candidate_protocol.json \
  --candidate-run PRIVATE_candidate_run.json \
  --expected-registration-sha256 PRIOR_STUDY_SHA256 \
  --expected-registry-sha256 PRIOR_REGISTRY_SHA256 \
  --expected-baseline-protocol-sha256 PRIOR_BASELINE_SHA256 \
  --expected-candidate-protocol-sha256 PRIOR_CANDIDATE_SHA256
```

Private source text, paper identities, raw review notes and unlicensed
material do not belong in Git or CI. The public tests contain only invented
families. An actual confirmatory study additionally needs qualified custody,
external pre-outcome protocol anchoring, independent labels and an analysis
power justification. The old RW-04D registration remains *draft only*.
