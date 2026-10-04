# Validation — ResearchWitness 0.2.0 MVP

**Date:** 2026-10-04

This is the preserved qualification record for the `0.2.0` MVP. The unreleased `0.3.0.dev0` integration candidate has a separate, freshly generated record under [`validation/verifier-wave/`](../validation/verifier-wave/); do not apply this baseline's test count or wheel hash to that candidate.

This document separates software qualification from scientific coverage. Passing the engineering suite does not mean ResearchWitness can verify arbitrary research papers.

## Engineering qualification

The release gate runs offline and checks:

- unit, adversarial, malformed-input and differential tests;
- generated-schema drift;
- Python compilation;
- trusted-core static scan for network/dynamic execution primitives;
- 500 seeded synthetic conformance cases;
- real historical MVP replay cases;
- two deterministic wheel builds and byte equality;
- clean virtual-environment installation without network/dependencies;
- installed CLI smoke verification.

Run:

```bash
python tools/quality_gate.py
```

## Real-paper evidence carried into the MVP

### Earlier network-reliability and QTT-Tucker claims

The `0.2.0` notes record a `K3` network-reliability margin of `5/64` and a QTT-Tucker residual of `1/64`. The recovered source tree contains no runnable bundles, source excerpts, correction evidence, or tests for those claims. They are preserved as historical documentation only and are **not** fresh reproductions or counted in the candidate's executable validation. The frozen screen still marks their mechanisms as representable at the mechanism level.

### Elliptic curve over F_29

The MVP adds a finite-field verifier that does not merely accept the point count as input. It:

1. enumerates all affine `(x,y)` in `F_29^2` satisfying `y^2=x^3+cx`;
2. adds the point at infinity;
3. independently classifies nonzero `c` as quartic, quadratic non-quartic, or quadratic non-residue;
4. compares the exact point-count residue with the residue rule for that class.

Historical replay:

- `c=4`: quadratic non-quartic, 40 total points, `0 mod 8` vs expected `4 mod 8` → refuted;
- `c=7`: quartic residue, 20 total points, `4 mod 8` vs expected `0 mod 8` → refuted.

Both cases are known corrigenda, so the product-level contact gate correctly returns `NOT_READY`.

### Exact finite PMF arithmetic

The synthetic [finite-PMF probability example](../examples/finite-pmf-probability/) checks a four-state categorical PMF. It computes `P(coin = H or weather = sun) = 3/4`, counting the overlapping event clause once, and refutes the supplied `at_most 2/3` bound. Focused tests also replay exact expected payoffs and fail closed when PMF mass, domains, payoff coverage or the 256-state limit is invalid. This demonstrates only arithmetic over an explicit finite PMF; it supplies no empirical or population inference evidence.

### Modular-metric fixed-point counterexample

The finite-map plugin confirms that the explicit swap `0→1, 1→0` on `{0,1}` has no fixed point. It deliberately reports that the original theorem's modular-metric premise is **not established by this checker**. The fixture carries that gap as an open objection and returns `NOT_READY`.

Run the end-to-end historical MVP replay:

```bash
python validation/mvp_real/run_validation.py
```

## Historical coverage screen

The earlier frozen 15-corrigendum screen remains the correct warning against overclaiming. The MVP adds finite-field and finite-map coverage, but the committed runnable historical set is only the two elliptic parameter cases plus one finite-map conclusion case. Many other frozen-screen entries require semantics not present in the trusted core: graph invariants beyond supplied colorings, continuous probability/integration, PDE norms/asymptotics, infinite-index existence arguments, database-repair semantics, and other domain-specific logic.

ResearchWitness is therefore a **verification platform with extensible deterministic plugins**, not a general theorem prover.

## Contact-readiness validation

Tests enforce that:

- a deterministic counterexample alone does not establish a paper error;
- a known correction blocks readiness;
- an open objection blocks readiness;
- unverified/synthetic source context blocks readiness;
- the product never emits `author_contact_authorized=true`;
- author-inquiry drafting is refused when blockers remain;
- generated HTML escapes untrusted text.

## What is still unmeasured

The MVP does not yet provide a credible estimate of:

- autonomous discovery recall on unseen papers;
- false-positive rate of agent-produced source interpretations;
- false-contact rate in genuinely novel cases;
- coverage across scientific disciplines;
- researcher adoption or time saved.

The next empirical milestone is a frozen, unseen historical-corrigenda discovery benchmark using external research agents while keeping the deterministic verifier unchanged during the run.
