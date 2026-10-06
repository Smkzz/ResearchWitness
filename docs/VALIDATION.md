# Validation — ResearchWitness MVP and development candidate

**Historical MVP qualification:** 2026-10-04 · **Paper-audit wave 1:** 2026-10-06

This document separates software qualification from scientific coverage. Passing the engineering suite does not mean ResearchWitness can verify arbitrary research papers.

The wave began from clean local commit `b66b4bfb7b9da3e7246f0b827315bf3287a09f28`. The exact state, prior gate results, and old synthetic CLI behavior are recorded in [`paper-audit-wave-1/development-start.json`](../validation/paper-audit-wave-1/development-start.json). The archived [`validation/verifier-wave/qualification.json`](../validation/verifier-wave/qualification.json) and the earlier [`development-start-2026-10-06.json`](../validation/development-start-2026-10-06.json) describe historical trees, not this candidate.

## Paper-audit development set

The source-pinned, **development-only** set contains four positive cases with public corrections and five selected negative controls. The cases were inspected during detector work; correction details are visible in `cases.json`. This is an exploratory development result, not a blinded benchmark. No sealed holdout was run because there was no independent custodian and the working environment was shared.

| Result | Development-set outcome |
|---|---:|
| Correction-backed issues rediscovered | 3/4 (75%) |
| Candidate items surfaced | 4 |
| Candidate items matching a documented correction | 4/4 (100% on this selected set) |
| Selected negative-control papers with candidates | 0/5 |
| False-positive candidates per selected negative paper | 0.00 |
| Possible scope/denominator notes | 17; not scored as errors |
| Positive cases unsupported by current screens | 1/4 (Spittal annualized-rate correction) |
| Candidates promoted to verified paper errors | 0 |
| Reports byte-identical across repeated runs | 9/9 |
| Source-text extraction failures in this Markdown/JATS run | 0/9 |

Detected cases:

- **J-EINSTEIN**, DOI [10.1186/s12959-015-0035-3](https://doi.org/10.1186/s12959-015-0035-3): the correction [10.1186/s12959-016-0085-1](https://doi.org/10.1186/s12959-016-0085-1) changes `2/71` from 2.9% to 2.8%. The paper's separate `1/78 = 1.4%` result is retained under a different definition and denominator.
- **Depressive symptoms and cardiovascular disease**, DOI [10.1001/jamanetworkopen.2019.16591](https://doi.org/10.1001/jamanetworkopen.2019.16591): the correction [10.1001/jamanetworkopen.2019.20603](https://doi.org/10.1001/jamanetworkopen.2019.20603) changes an exclusion from 1,841 to 484, reconciling the stated flow to 12,417 included participants.
- **Vitiligo repigmentation**, DOI [10.1111/jocd.16714](https://doi.org/10.1111/jocd.16714): the correction [10.1111/jocd.70179](https://doi.org/10.1111/jocd.70179) changes two `23/30` table percentages to 76.7%.

The **Spittal practitioner-notification rates** paper and its correction ([10.1186/s12916-016-0748-6](https://doi.org/10.1186/s12916-016-0748-6), [10.1186/s12916-018-1030-x](https://doi.org/10.1186/s12916-018-1030-x)) form the unsupported positive: the correction identifies an annualization error in adjusted rates that cannot be recomputed from the original paper alone.

Negative controls are Mehta et al. ([10.1001/jamanetworkopen.2024.13515](https://doi.org/10.1001/jamanetworkopen.2024.13515)), Knitza et al. ([10.1186/s13075-022-02809-7](https://doi.org/10.1186/s13075-022-02809-7)), Brown et al. ([10.1038/s41598-021-86008-5](https://doi.org/10.1038/s41598-021-86008-5)), Egilsson et al. daily ([10.2196/45414](https://doi.org/10.2196/45414)), and Egilsson et al. weekly ([10.2196/21432](https://doi.org/10.2196/21432)). They exercise changing analysis populations, screening/randomization/paired-sample counts, repeated measures, and row-specific denominators. They were selected as controls, not certified as error-free.

The original marker-only screen rediscovered none of the four correction-backed issues and emitted candidates on all five selected negative controls. The new scopes and arithmetic screens reduce those control flags and surface the three supported correction mechanisms. This does not establish similar precision or recall on other papers. The 17 possible scope notes have not been exhaustively adjudicated, and the negative controls cover a narrow clinical-study slice.

The corpus manifest pins Europe PMC JATS URLs, dates, versions, SHA-256 hashes, corrections, identifiers, and license notices. Full papers and PDFs are not checked in. Retrieval verifies the exact hash before writing a temporary snapshot. See [`paper-audit-wave-1/`](../validation/paper-audit-wave-1/), including per-paper JSON reports and the scoring/evaluation tools.

## Current screen scope and limits

`paper-audit` checks explicit `n`/`N` contexts, selected count/percentage cells in Markdown pipe tables, and one explicit exclusion-flow sentence. All outputs are review candidates. A separate smaller denominator may be legitimate; exclusion categories may overlap; a clean scan means only that these supported patterns surfaced no candidate. Statistical tests, confidence intervals, row/column totals, prose/table reconciliation, citations, code, figures, and known corrections remain unsupported.

The optional `pypdf` parser runs in a separate worker with a 20-second wall timeout, 15-second CPU limit, and 768 MiB address-space limit where supported. It is process isolation, not an OS sandbox, and performs no OCR. Synthetic tests cover valid multi-page, partial, encrypted, malformed, timeout, page-limit, and oversized-page-text inputs. Real corpus extraction used rendered JATS Markdown; PDF extraction accuracy on full papers remains unmeasured.

The engineering baseline before this wave was 348 passing tests, 500/500 synthetic conformance cases, and 3/3 historical MVP runs. Final qualification for this candidate is recorded below after the full gate.

## Engineering qualification

The offline quality gate passed for `0.4.0.dev0` on Python 3.12.14:

- **356 tests passed**.
- **500/500** synthetic conformance cases and **3/3** historical MVP fixtures matched.
- Trusted-core static checks, generated-schema and checksum checks, the frozen-screen review, and the checked-in paper-audit development-result consistency check passed.
- Two independently built wheels were byte-identical. The tested wheel SHA-256 was `83181729e901c5dc924e03eee4d3f545549f2a3b33766cb825ee139eba263e02`.
- A clean environment installed the wheel and passed CLI smoke checks for the agent, review, summary, and paper-audit commands.

This qualifies the development tree against its current engineering gate. It does not qualify the product for general research-paper review or represent a release.

Run the offline release gate:

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

This development set does not estimate discovery recall or candidate precision on unseen papers, coverage outside a small clinical-study sample, PDF extraction accuracy on real publisher layouts, false-contact rate, or researcher time saved. No candidate in this wave was promoted to a verified finding. The next empirical milestone is an independently custodied, sealed paper-audit evaluation with broader disciplines and extraction formats; see [`docs/ROADMAP.md`](ROADMAP.md).
