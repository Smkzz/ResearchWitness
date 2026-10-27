# RW-04F: exact paired-power planning with a conservative safety feasibility gate

**Scope: development-only, hypothetical mathematics.** This tool does not
retrieve articles, authenticate research labels or publisher licences, freeze a
preregistration, estimate a model from observed studies, access a protected
holdout or declare a statistically powered real experiment. The study design
must be independently justified and frozen **before** any confirmatory result
exposure; separate custody and source-validation gates still apply.

This extends [RW-04E's exact endpoint diagnostic](EXACT_FAMILY_ANALYSIS.md)
without changing its acceptance rule, safety bound or previously frozen results.

## Inputs and model

Use the pinned RW-04D study *draft*, plus a strict versioned **invented**
assumption file with these fields:

- `schema_version: rw-development-power-scenario.v1`
- `partition: hypothetical_development_only`
- `candidate_only_positive_probability` and
  `baseline_only_positive_probability`: exact rational fractions for the two
  mutually exclusive discordant outcomes of one eligible **positive family**;
  their sum must be no more than one. All other paired outcomes have combined
  probability `1-a-b`.
- `target_primary_power`: exact fraction strictly between zero and one.
- `negative_joint_no_alarm_probability`: invented probability that **neither
  arm** emits an alarm for one eligible negative family. This is not an
  estimated marginal false-alarm probability, nor can it determine paired
  negative-harm-test power.
- Finite `max_positive_families` (at most 256) and
  `max_negative_families` (at most 2,048) bound exact computation.
- `assumptions_basis: invented_not_estimated_from_source` prevents accidental
  description of the example as observed research evidence.

The scenario is
[`examples/synthetic-study-registration/power-scenario.json`](../examples/synthetic-study-registration/power-scenario.json).
All examples use invented probabilities and artificial implementation hashes.

## Positive-family exact power

For each attempted independent family, let `a` be the candidate-only correct
detection probability and `b` baseline-only. Under the explicitly
**hypothetical independent-family** model:

```text
D ~ Binomial(n, a + b)
W | D=d ~ Binomial(d, a / (a + b))
```

For every `d`, compute the minimum winner count `W` satisfying **both**:

1. Exact one-sided null discordance tail
   `P[Binomial(d, 0.5) >= W] < primary_alpha`.
2. Observed practical improvement `(2W-d)/n >= minimum_practical_gain`.

Sum `P(D=d) P(W meets both criteria | D=d)` across `d = 0..n` using
`fractions.Fraction`, exact binomial coefficients and integers. The first
passing `n` is found by evaluating the complete sequence rather than
assuming discrete exact-test power increases monotonically with `n`.
Missing or unavailable source measurements have *not* been modelled here.

For illustrative `a = 0.25`, `b = 0.10`, `primary_alpha = 0.025`,
`minimum_practical_gain = 0.10` and target power `0.80`:

| Independent positive families | Hypothetical probability of passing both primary gates |
|---:|---:|
| 128 | 0.7992594458076103 |
| 129 | 0.8028103975131423 |

Thus **129** is the first sufficient positive-family count for those exact
assumptions. This is not a recommendation for real enrolment without
development-exposed estimates and sensitivity analyses.

## Negative-family zero/zero safety feasibility

RW-04E's preregistered Bonferroni Clopper-Pearson safety method, **when both
arms emit zero alarms**, has exact upper harm bound

```text
U(n) = 1 - (safety_alpha / 2) ** (1 / n).
```

Requiring `U(n) <= maximum_false_alarm_increase` is exactly equivalent to
`(1-margin)**n <= safety_alpha/2`. RW-04F evaluates the rational inequality,
not rounded logarithms, respecting the registered negative-family minimum.

At `safety_alpha=0.025` and margin `0.05`, the first feasible count is
**86 independent negative families**. This count **does not guarantee
adequate safety power**. Under the synthetic assumption that the probability
of **neither arm** emitting any false alarm on an independent negative family
is `0.98`, the probability of 86 completely silent families is only

```text
(0.98)**86 = 0.17597157031257069...
```

This zero/zero probability is a conservative lower-bound contribution to
safety success in that specific model; the actual safety-test pass probability
also depends on the **paired joint false-alarm distribution**, which this tool
does not know or calculate. It is scientifically incorrect to call 86 negative
families an 80%-powered safety plan. Even the illustrative **129 + 86 = 215**
total is a *scenario feasibility count*, **not** a qualified sample-size
recommendation or complete joint primary-and-safety power analysis.

## Private offline CLI

Preserve the original development-study declaration SHA-256 separately:

```text
python -m tools.power_feasibility \
  --registration examples/synthetic-study-registration/draft.json \
  --scenario examples/synthetic-study-registration/power-scenario.json \
  --expected-registration-sha256 EXTERNAL_SHA256_OF_CANONICAL_REGISTRATION
```

The result includes the input commitments, exact positive sample-search
result, zero/zero safety feasibility, hypothetical probability of silence,
outward **lower** 12-place decimal displays, explicit search bounds and
failure/null results when the thresholds cannot be reached. It always reports
`actual_sample_size_power_verified=false`,
`power_and_safety_jointly_verified=false`,
`registration_frozen_before_outcomes=false`,
`protected_data_accessed=false` and
`scientific_superiority_established=false`.

## Next step implemented by RW-04G

The [full paired negative alarm and joint-power model](JOINT_POWER_FEASIBILITY.md)
now computes the safety pass probability for *all four* assumed
within-family alarm patterns, not just the zero/zero special case.
Under the invented scenario its result is 42.17% negative safety
pass probability and **33.85% chance of passing both primary and
safety endpoints** for 129 positives + 86 negatives. This still does
not establish real independence, actual sample power, source labels,
scientific improvement or protected-data authority.

## Next rigorous study design and data gates

1. Obtain an authorized private, article-specific rights-cleared real-source
   development cohort and true observed source/version receipts via
   [RW-01O](https://github.com/Smkzz/ResearchWitness/issues/35). Two model
   personas and old benchmark labels are not independent adjudication.
2. Independently source-review positive discrepancy mechanisms, correct
   negative relationships, ambiguity, missingness and family-sharing
   assumptions. Count all attempted work families, not selected successful
   relationships.
3. Use **exposed development** outcomes only to estimate plausible paired
   detection discordances and the paired negative false-alarm distribution.
   Predeclare sensitivity ranges, independence/clustering assumptions,
   missingness effects, the desired *joint* primary/safety success probability
   and a feasible stopping/acquisition budget.
4. Independently freeze study protocol, candidate versions and source-family
   sampling **before** sealed evaluation. Do not retroactively make exposed
   cases new untouched holdouts.

A proven negative or inconclusive design is a valid outcome. No new scientific
breakthrough is claimed from planning probabilities.
