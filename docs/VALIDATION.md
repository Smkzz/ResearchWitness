# Validation — ResearchWitness MVP and development candidate

**Historical MVP qualification:** 2026-10-04 · **Development continuation:** 2026-10-06

The `0.2.0` MVP material below is a preserved historical record. The unreleased `0.3.0.dev0` development candidate has since added review-ledger, tabular-summary, and paper-screening workflows. The archived [`validation/verifier-wave/qualification.json`](../validation/verifier-wave/qualification.json) predates those changes and must not be treated as qualification for the current source tree.

This document separates software qualification from scientific coverage. Passing the engineering suite does not mean ResearchWitness can verify arbitrary research papers.

The current gate is intended to qualify software behavior, not scientific coverage. It does not measure cross-domain detection precision/recall or establish exhaustive paper correctness. The summary checker proves only arithmetic agreement or mismatch for the exact supplied values or extracted CSV/TSV column and declared rounding tolerances. The automatic paper screen only searches for conflicting explicit `n=` / `N=` integer markers; candidate flags require human scope review.

## Current development candidate scope

The candidate now has a broad review ledger, bounded exact tabular-summary checker, and `paper-audit` ingestion/screening command. The current gate includes their tests, generated schemas, package contents, and installed-command smoke checks. Text/Markdown inputs are preserved byte-for-byte; optional `pypdf` extraction supports born-digital PDFs without OCR. The PDF parser runs locally in-process and is not an OS sandbox. Input/output limits do not guarantee that every parser-internal operation is bounded.

The paper screen's tests include synthetic positive and negative controls, byte-anchor checks, oversized-line/incomplete-scan behavior, optional-parser absence, and a generated two-page PDF. These are software fixtures, not real-paper discovery evaluations. The historical MVP cases exercise deterministic formalizations, not the paper-text screen. No independent source-pinned discovery corpus or sealed holdout is available, so discovery recall, false-positive rate on real papers, and cross-field performance remain unmeasured.

The initial state for this continuation was already dirty at commit `f5e0b98b48b3b63feedc3d210890f008a2508b9f`; the first baseline's test and gate results therefore describe that dirty tree, not the clean commit. The recorded baseline is [`validation/development-start-2026-10-06.json`](../validation/development-start-2026-10-06.json).

## Engineering qualification

The updated offline quality gate passed on 2026-10-06 using Python 3.12.14: **348 tests passed**, the synthetic verifier suite matched **500/500**, and **3/3 historical MVP fixture runs** matched (two unique frozen-screen entries). The gate also passed source checksums, all generated schemas, capability-example/frozen-screen drift, compilation, static scanning, two byte-identical wheel builds, a clean no-network wheel install, and installed CLI smoke checks for intake, review, summary, and paper screening. The reproducible wheel SHA-256 was `8a20100908d379581872a3acb15bc8e111f88e2d9b08d9a6e331a284b3045f47`; runtime dependencies remain empty. The archived gate output remains the older verifier-wave record; rerun the command below to qualify a later tree.

The `paper-audit` smoke input is explicitly synthetic. It surfaces differing count values that describe recruitment and post-exclusion samples, which may both be correct. No real-paper count-marker anomaly was rediscovered or evaluated in this run.

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
