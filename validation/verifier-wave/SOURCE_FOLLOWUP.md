# Frozen-screen source follow-up: backward heat

This note checks the source wording for the `backward-heat-2023` row in the
frozen [`../screening-15.json`](../screening-15.json). It does not edit that
screen, replay the PDE theorem, or change the representability classification.

The official [SIAM erratum](https://epubs.siam.org/doi/10.1137/22M1534882)
states that the original Theorem 1.3 is invalid and that the related Theorems
1.2, 1.4, and 5.1 require revision. Its abstract says the claimed Lipschitz
stability in an `L¹` norm is replaced by weaker results involving `H⁻²`; the
light-sheet fluorescence microscopy result is revised to logarithmic stability
in the natural Lebesgue norms or Lipschitz stability in `H⁻²`.

Section 3 gives the counterexample summarized in the frozen row. It defines
compactly supported oscillatory data `g_k(y) = sin(k y)` on `[-π, π]`, zero
outside. The erratum computes `||g_k||₁ = 4` for all positive integer `k`,
then bounds the squared full-space `L²` norm of the heat solution by a constant
times `e^(−k²t) + 1/k`. At fixed positive time this bound tends to zero as `k`
increases. The frozen statement that the initial `L¹` norm stays fixed while
the heat solution can decay therefore matches the erratum's example.

The short screen description is accurate at that level, though it omits the
precise observed norm and the corrected theorem's `H⁻²` formulation. This is a
wording limitation, not evidence of a contradiction. The case remains
`UNSUPPORTED` for ResearchWitness because the product does not verify PDE
solution operators, the norm estimates, or the theorem's quantified premises.
No paper-level error or scientific-consequence judgment follows from this
source note.

The erratum page cites the original article as DOI
[`10.1137/20M1374183`](https://doi.org/10.1137/20M1374183). The source page was
checked on 2026-10-07. The frozen screen's contents and SHA-256 remain unchanged.
