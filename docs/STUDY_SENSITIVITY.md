# RW-04H: hypothetical endpoint-dependence and missingness sensitivity

**Status:** source-free development planning utility. No new research source, empirically
estimated probabilities, sealed benchmark, independent reviewer or scientific
performance claim is supplied. RW-01O #35 / RW-01Q #50 remain evidence-blocked.

The RW-04G example gave **rounded hypothetical** positive-endpoint pass probability
`0.8028` and negative safety pass probability `0.4217`. Its joint `~0.3385`
implicitly assumes independence between the endpoint events. Without that
assumption, the exact Fréchet bounds are:

`max(0, P(A)+P(B)-1) <= P(A and B) <= min(P(A), P(B))`

For the rounded illustrative marginals this is **0.2245 to 0.4217**, rather
than one certified joint-power value. Even these marginals are **not estimates**
from independently reviewed development articles.

## A separately stated retention model

Assume only for planning that each enrolled positive (or negative) work family
is retained independently with a specified within-stratum probability. Given
`n` enrolled and `k` required complete families, the exact binomial tail
`P(Binomial(n, retention) >= k)` is calculable as a rational number. A minimum
bounded enrollment can guarantee a specified marginal quota probability. To
guarantee **joint completion of both quotas without assuming independence
between strata**, allocate the target failure probability evenly using the
union bound, then compute the smallest enrollment satisfying each allocation.

For the *illustrative*, **invented** 10% missing-per-family rate, requiring
129 complete positive and 86 complete negative families and a lower bound
of 95% on both quotas being met:

| Stratum | Minimum complete | Enroll (independent within-stratum retention assumed) | Marginal quota chance |
|---|---:|---:|---:|
| Positive | 129 | **152** | 98.335% |
| Negative | 86 | **102** | 97.541% |

The Fréchet/union lower bound on reaching both quotas is **95.876%**. This
is an enrollment *completion* probability, **not** the statistical power
of ResearchWitness nor the probability of satisfying its scientific gates.
The observed enrollment needed may be much higher if loss is clustered,
selective by outcome, or larger than invented. These quota probabilities cannot
be multiplied by endpoint success without much stronger, unverified assumptions.

## Offline reproducible invocation

```sh
python -m tools.study_sensitivity \
  --positive-pass 0.8028 --safety-pass 0.4217 \
  --positive-target 129 --safety-target 86 \
  --positive-missing 0.10 --safety-missing 0.10 \
  --joint-quota-confidence 0.95
```

This uses only bounded exact `Fraction` arithmetic (maximum 512 enrolled
families per stratum), reads no files/network, prints deterministic JSON and
returns `null` for a quota not feasible within the cap. Probability inputs are
literal decimal strings with up to six decimal places; no inferred source truth.

**Research gates unchanged:** independently adjudicated original permitted
sources, informed missingness/dependence estimates, separately frozen study
registration and qualified custody are prerequisites to empirical sample sizing.
An AI calculation is not independent scientific review. This scenario must not
be used to retroactively redefine RW-04G's published illustrative conditions.
