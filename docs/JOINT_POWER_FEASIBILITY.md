# RW-04G: full paired-negative safety and joint primary/safety power (hypothetical)

**Status:** a source-free, deterministic study-design aid, not a scientific
study or independent validation. It reuses the exact RW-04E registered
statistical decisions and the RW-04F positive-family power calculation, but
does not authenticate a single actual paper, research label, licence, family
independence, pre-outcome freeze or custodian. Both positive and negative
outcome probabilities in its scenario are explicitly *invented*.

## Why this matters

[RW-04F](POWER_FEASIBILITY.md) showed that 129 positive families could
achieve 80% **primary-test** power under one invented discordance model, and
86 negative families could meet the conservative harm margin *if both arms
emitted zero false alarms*. This does **not** guarantee 80% probability
of satisfying the **negative safety gate**, much less both gates together.

The [RW-04G engine](../tools/joint_power_feasibility.py) models all four
*paired* outcomes for a single eligible negative work family:

| Pair of arm outcomes | Invented example probability |
|---|---:|
| Neither arm alarms | 0.980 |
| Only candidate alarms | 0.005 |
| Only baseline alarms | 0.010 |
| Both arms alarm | 0.005 |

The two arms are **not** incorrectly assumed independent. Only distinct
work families within each stratum, and positive vs negative family strata,
are assumed independent for the hypothetical calculation.

## Exact methods

For `n` negative families, derive a bivariate distribution of candidate
alarm count `C` and baseline alarm count `B` from the polynomial

```text
(p_neither + p_candidate_only*x + p_baseline_only*y + p_both*x*y)^n.
```

The implementation expands these weights by a bounded four-transition
**integer dynamic program**; all probability inputs are exact rational
fractions, combined into a bounded common denominator. Every possible
`(C,B)` count pair remains accounted for.

At each feasible negative-family count pair, calculate the unchanged
RW-04E one-sided **Bonferroni Clopper-Pearson** marginal harm bound
`U_candidate(C)-L_baseline(B)` with the same outward 40-bit dyadic grid.
The scenario passes the safety gate when the conservative bound is no
more than the preregistered maximum false-alarm increase. Sum exact
bivariate probabilities for all passing count pairs. This yields a
**conservative lower bound on the hypothetical safety-pass probability**,
not a false-precision normal/Wald approximation.

Separately, use RW-04F's exact unconditional binomial-mixture primary
success probability with both the strict one-sided discordance alpha
and the declared practical gain threshold.

Finally multiply the positive and safety pass probabilities **only
under the explicitly hypothetical independence of positive and negative
family strata**. A realistic clustering/shared-dataset model or
unresolved/missing-case model may substantially reduce performance.

All decimal probabilities display 12 places **rounded downward**. The
joint-target check compares the exact rational value, never its display.
The maximum accepted example size is 256 positive and 200 negative
work families, with negative common probability denominator at most
10,000. Larger calculations are rejected, not approximated by invented
successes.

## Worked example — 215 *hypothetical*, distinct families

The checked-in synthetic scenario
[`joint-power-scenario.json`](../examples/synthetic-study-registration/joint-power-scenario.json)
uses `n_positive=129`, `n_negative=86`, candidate-only positive
discordance 0.25, baseline-only 0.10, primary alpha 0.025, practical
gain 0.10, safety alpha 0.025, safety margin 0.05, and the four
negative outcomes above.

| Probability calculated under the invented model | Result |
|---|---:|
| Primary detection **and** practical-gain gates | 80.2810% |
| Negative safety gate, accounting for all alarm patterns | 42.1702% |
| Negative zero/zero-alarm event alone | 17.5972% |
| Both primary and safety gates together | **33.8546%** |

Therefore the earlier figure **129 + 86 = 215 is not an 80%-powered
combined study**, even in this fairly favorable hypothetical model.
Using 128 negative families improves the modeled safety chance to
63.6909%, yet the combined chance with 129 positives is only
51.1318%. These are theoretical feasibility diagnostics, not actual
error-detection results or an empirical sample recommendation.

The calculation is meaningful precisely because it removes the
**incorrect shortcut of equating a zero-alarm minimum with study power**.
It does not itself discover research errors or eliminate the actual
source-label and custody bottleneck.

## CLI and source restrictions

Only an existing externally pinned RW-04D study *draft* and this
strict source-free scenario are accepted:

```text
python -m tools.joint_power_feasibility \
  --registration examples/synthetic-study-registration/draft.json \
  --scenario examples/synthetic-study-registration/joint-power-scenario.json \
  --expected-registration-sha256 EXTERNAL_PIN_OF_THE_DRAFT
```

No query, source ID, author, full text, label provenance claim or
protected-custody source is permitted as an extra scenario field.
All outputs retain `actual_sample_size_power_verified=false`,
`negative_joint_distribution_empirically_validated=false`,
`family_independence_verified=false`,
`protected_holdout_accessed=false` and
`scientific_superiority_established=false`.

A real scientific study must first curate permission-cleared original
PMC sources, independently source-review scope and positives/negatives,
preserve all unavailable and unresolved work families, and estimate
plausible positive discordance plus the four negative alarm rates on
*development-exposed* material. Actual power and uncertainty require
justified family sampling/clustering and missingness sensitivity,
followed by a genuine independently held pre-outcome protocol freeze.
Those gates remain open at
[RW-01O](https://github.com/Smkzz/ResearchWitness/issues/35) and RW-03/RW-05.
