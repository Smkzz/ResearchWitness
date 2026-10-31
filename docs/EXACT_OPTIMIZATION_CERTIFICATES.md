# RW-MATH-01: reusable exact optimization certificates

**Scope:** optional installed mathematical checker, source-independent and offline.
Package version remains `0.3.0.dev0`, UNRELEASED. This does not change the ten
existing case-verifier families, JATS reports, historical studies or custody gates.

The owner approved a parallel mathematical-certificate work package on 31 October
2026. It does not require external researcher recruitment or communication. AI
engineering review is disclosed as such; it is not independent human validation.
The blocked original-source/empirical evaluation packages retain their status.

## What is proved

For a supplied, byte-pinned finite bounded real model, the checker proves a
**global upper bound on a linear objective subject to linear constraints and
explicit bilinear equalities**. The checker reconstructs every relaxation from
that model; it does not trust a solver's objective, a success flag or a supplied
matrix. A second, separately authored implementation checks the same model with
integer-scaled arithmetic and a different partition algorithm.

The supported statement is not an automatic claim that a paper is correct or
wrong. The mathematical model, its correspondence to a source, any source rights,
and the scientific meaning of the assumptions are separate. In particular, an
A020-specific source-to-relaxation adapter is not a generic paper parser.

An upper bound does not establish attainment or feasibility. A separate exact
point check can establish a lower bound; equal certified lower/upper values
establish the optimum of the supplied model. If all leaves are proved empty,
report model infeasibility instead of an invented numerical optimum.

## Mathematical acceptance argument

The supplied model has finite rational bounds `L <= x <= U`, inequalities
`A x <= b`, equalities `E x = f`, products `x[w] = x[i] x[j]`, and objective
`c0 + c.x`. On each parameter box, exact equality interval propagation may
narrow variable bounds, but cannot exclude a feasible point. For every product,
append the four McCormick inequalities in this fixed order:

```text
-w + Lx*y + Ly*x <= Lx*Ly
-w + Ux*y + Uy*x <= Ux*Uy
 w - Lx*y - Uy*x <= -Lx*Uy
 w - Ux*y - Ly*x <= -Ux*Ly
```

These inequalities contain every true product on the current box. Repeated
operands, such as `w=x*x`, accumulate coefficients rather than overwrite them.
The product output cannot alias either input in this first schema.

For exact rational `lambda >= 0` and arbitrary rational `nu`, calculate

```text
r = c - lambda*A - nu*E
B = c0 + lambda*b + nu*f + sum_j max(r[j]*L[j], r[j]*U[j])
```

For every feasible point, `c0+c.x <= B` follows by multiplying the inequalities
by nonnegative weights, adding the equalities and bounding the residual over
its box. No strong duality or solver correctness is assumed. The residual term
is essential: rounded multipliers need not cancel the objective exactly.

Every leaf must have `B <= claimed_upper` or an exactly verified interval
contradiction `L[j] > U[j]`. A point interval `L[j] == U[j]` is **not** empty.
The maximum of all nonempty-leaf bounds is the returned global upper bound.
There is no arbitrary submitted `infeasible` flag, omitted failure or unchecked
pruned branch.

## Complete partition, not equal volume

The selected parameter coordinates are normalized to the integer grid
`[0, grid]^d`. The canonical binary tree always bisects the longest **grid**
width, breaking ties by the lowest dimension. Every submitted box must be a
node of this tree, and the leaves must form a complete, nonoverlapping cover
apart from shared boundary faces.

The installed checker traverses the canonical tree from the root and verifies
exact set equality with all supplied leaves. It limits visits to `2*N-1`.
The separate reference checker derives each leaf's binary path and merges
siblings from the bottom up. Neither checker accepts a volume total as a
substitute for structural coverage. Tests include an equal-volume overlap/hole.

## Versioned data format

Model JSON has exactly these fields:

```json
{
  "schema_version": "rw-exact-bilinear-model.v1",
  "bounds": [["0", "1"], ["0", "1"], ["0", "1"]],
  "objective": {"coefficients": [[2, "1"]], "constant": "0"},
  "inequalities": [],
  "equalities": [{"coefficients": [[0, "1"], [1, "1"]], "rhs": "1"}],
  "products": [[0, 1, 2]],
  "bound_derivations": [[1, 0]],
  "partition": {"variables": [0], "grid": 2}
}
```

This example is `max z` with `x+y=1` and `z=x*y`. It makes no assertion about
A020 or another publication. Its optimum is exactly `1/4`.

All rational literals are **canonical strings** in Python Fraction notation:
`"0"`, `"-2"`, `"3/7"`; not floats, `"2/2"`, `"0/1"` or `"-0"`.
Sparse vectors are sorted unique `[index, nonzero_coefficient]` lists. Missing
entries mean zero, not omitted constraints. Partition variable IDs are sorted
and distinct. A derivation `[target, row]` refers to a nonzero target coefficient
in the actual equality row; the interval rule handles either sign and intersects
with current bounds. Derivations run once in the declared order.

Certificate JSONL begins with exactly:

```text
schema_version = rw-exact-bilinear-certificate.v1
model_sha256 = SHA-256 of the exact model file bytes
claimed_upper = canonical rational string
leaf_count = positive integer
```

Each subsequent line has `kind`, `lower`, `upper`, and, for a `bound` leaf,
`lambda` and `nu`. `lambda` entries are strictly positive sparse multipliers,
`nu` entries can have either sign. An `empty` leaf has no multipliers. Row indices
refer to supplied inequalities first and then the generated product rows in
product/order sequence. Equality indices refer only to supplied equalities.
All lines must end in LF; there are exactly `leaf_count` records and no blanks.

## Installed use and source-checkout examples

The **installed checker has no third-party runtime dependency**:

```text
python -m researchwitness.exact_optimization --model MODEL.json --certificate PROOF.jsonl --expected-model-sha256 MODEL_SHA256 --expected-certificate-sha256 PROOF_SHA256
```

Both expected pins must be obtained from a separately retained trusted record.
A self-reported embedded hash alone is not an external pin. The successful
report appears only after complete parsing, all leaf/coverage checks and the
hash of the exact consumed proof bytes. Failure returns exit 2, never success.

From the source checkout, generate six synthetic example pairs into a **new**
directory:

```text
python -m tools.optimization_examples --output-dir ../math-examples
```

The resulting `pins.json` gives the exact model/proof byte identities. The
examples cover a bilinear simplex, signed linear allocation with nonzero
residual, a strict empty branch, a repeated product operand, a negative equality
orientation and a two-dimensional coverage control. Use those generated files
with the installed checker above. The reference implementation is a development
API: `tools.exact_optimization_reference.reference_verify(model, header, leaves)`.
It does not perform file acquisition or verify external byte pins; the caller
must do so before supplying parsed objects.

## Optional untrusted candidate generator

`tools.propose_exact_optimization` is checkout-only. It can use **already
provisioned SciPy** to propose dual weights for the declared mathematical model.
SciPy is not added to the package or default development dependencies. No
provider/model API, paper parser, network request or paid compute is invoked.

```text
python -m tools.propose_exact_optimization --model MODEL.json --expected-model-sha256 MODEL_SHA256 --claimed-upper 1/4 --output NEW_PROOF.jsonl --max-nodes 255 --max-seconds 30
```

The model is pinned before search. Rationalized numerical multipliers are
checked exactly before a leaf can close. Otherwise the canonical box is split.
Any solver failure, budget exhaustion or unresolved minimum-grid leaf is
**inconclusive**, not evidence that the claim is false. The full exact checker
runs before the certificate is emitted. Output is exclusive-create; existing
files are not overwritten. No partial proof is saved on an inconclusive search.
A finite rationalized solver point counts only after exact bounds, equations,
inequalities and products are checked. Search does not guarantee finding one.

## Limits and trust boundary

| Limit | Installed verifier |
|---|---:|
| Model / proof bytes | 2 MiB / 64 MiB |
| JSONL line | 256 KiB |
| Variables / parameter dimensions | 128 / 8 |
| Grid | power of two, at most 1024 |
| Supplied + generated constraint rows | 1024 |
| Products / leaves | 128 / 32768 |
| Model nonzeros including product allowance | 16384 |
| Rational numerator / denominator literal | 30 decimal digits each |
| Intermediate rational numerator / denominator | 4096 bits each |
| Estimated leaf arithmetic work | 40,000,000 |
| JSON depth / node count per object | 16 / 100,000 |

The reference checker has additional 2048-bit common-denominator and 200-million
dense-work caps. It may refuse a mathematically valid proof outside its resource
envelope. Both paths fail closed rather than truncate arithmetic. These finite
caps are not a formal wall-clock denial-of-service guarantee.

Files must be regular, single-link files in a trusted, quiescent directory.
Symlinks, hard links, special files, duplicate JSON keys, nonfinite/float values,
booleans used as indices, out-of-range indices and unknown fields are rejected.
The core accepts no compressed or executable proof inputs. It hashes the same
stream it consumes, uses no-follow/nonblocking flags where available, and checks
file identity. It is not a portable secure filesystem sandbox against an
attacker controlling parent directories, mounts, Python, the OS or local code.

## Source containment and explicit non-goals

A bilinear certificate proves the supplied model, not an arbitrarily rewritten
scientific claim. In particular, an adapter that replaces square roots by
rational tangents or introduces absolute-value penalty variables must separately
justify that its bounded relaxation contains every original feasible lifted
point. Unsupported auxiliary bounds can invalidate this source/model bridge
even when the generic certificate is perfectly valid. The A020 private replay
preserves this obligation and does not claim an automatic source compiler.

This work does **not** establish general paper-discovery accuracy, a sealed
benchmark, a new A020 optimum, a proof-assistant kernel theorem, original PMC
capture, independent human review or a released ResearchWitness product.
