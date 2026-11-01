# RW-MATH-02: strictly source-bound candidate formalizations

**Scope:** an optional installed, offline *controlled-markup* compiler and exact
replay tool. This is a narrow engineering slice adjacent to RW-06, **not** full
RW-06 readiness: RW-01/RW-02 and original scientific evidence dependencies remain
open. Version `0.3.0.dev0` stays UNRELEASED.

## What it can and cannot do

Given user-supplied, independently byte-pinned UTF-8 text containing an exact
`RW-MATH-BEGIN v1` block, this compiler extracts only the marked mathematical
statement, records its original UTF-8 byte span, compiles a deterministic bounded
real-valued linear/bilinear optimization model, and binds its canonical bytes to
the full source and selected block. The claim is **a candidate**, not a certified
reading of the surrounding paper. The source, exact model and claim candidate
are re-derived before any mathematical certificate or exact feasible point is
accepted. Original source bytes are **never** rewritten.

Supported outcomes are separate:

- `source_bound_model_candidate_only`: recognized block and compiled model;
  **no mathematical proof** supplied or accepted.
- `candidate_formalization_and_math_bound_replayed`: the exact certificate
  proves the **specified mathematical model** satisfies the source-block upper
  bound; it does not establish source origin, interpret unmarked surrounding
  prose, or prove an empirical/scientific proposition.
- `formal_model_upper_refuted_by_exact_point`: the exactly checked feasible
  point violates the source-block upper bound **for the formal model**; no
  automatic finding that a publication is erroneous.
- Unsupported syntax, absent/ambiguous markers, invalid pins, partial proofs,
  invalid points and unsupported contexts fail closed, not as a weaker claim.

**This is not an arbitrary-PDF or free-form-article parser.** An AI-generated
candidate is untrusted data until it matches the exact deterministic source
block and constraints. An invented source block can still receive a valid proof;
cryptographic hashes prove continuity with the supplied bytes, not publisher
origin, citation accuracy, scientific meaning, or permission to redistribute.

## Exact supported grammar (v1)

Exactly seven lines, including start and end markers, with LF or CRLF terminators:

```text
RW-MATH-BEGIN v1
domain: bounded_real
variables: x[0,1]; y[0,1]; z[0,1]
maximize: z
constraints: x + y == 1; z == x*y
upper_bound: 1/4
RW-MATH-END
```

The domain line means **all real assignments within the declared closed
intervals that satisfy every constraint**. The claimed bound is universally
quantified over these assignments. Units, external experimental context and
additional source assumptions are **not** inferred. Each variable has one
unique lowercase ASCII name and two exact finite rational bounds. There are at
most 12 variables and 32 constraints; each block is at most 4 KiB. Distinct
blocks are selected by an explicit zero-based `--block-index`, and all strict
block markers (up to 16) are counted. An invalid, orphaned, or nested marker
prevents successful selection. Source size is capped at 1 MiB. Offsets are
zero-based, half-open **byte** indices in the unchanged UTF-8 source.

Expressions support integer literals, unary `+`/`-`, rational division by a
**nonzero constant**, parentheses, addition/subtraction and multiplication by
rational constants. Every objective is affine. A constraint uses one of `==`,
`<=`, `>=`; the only non-affine form is explicit `output == factor * factor`,
with distinct output and declared inputs (the two factors may be the same).
Write `constraints: none` when there are no extra constraints beyond bounds.
The upper bound must be a rational constant expression, never a variable or
an approximation. All arithmetic lowers to reduced canonical `Fraction`
strings, without float conversion.

Python's `ast` is used **only to parse syntax**, with a small checked whitelist;
there is no `eval`, `exec`, code invocation or dynamic import. Comments, `#`,
floats, approximate symbols, arbitrary function calls, powers, indexing,
attributes, boolean expressions, chained/strict inequalities, negation and
unmarked textual assumptions are unsupported. The parser rejects unsupported
trailing characters instead of accepting an earlier valid prefix.

A quote may be nested in a larger UTF-8 file, but no claim is made that the
text outside the selected explicit block supports, qualifies or negates that
block. Source versions, mathematical units, correction lineage and readers'
interpretation of surrounding prose remain **separate unresolved obligations**.

## Proof strategy hints are not source assumptions

An optional separately pinned JSON hints file affects *only* proof search or
valid mathematically sound derived bounds, never the model's original feasible
region or objective. The v1 schema has exactly:

```json
{"schema_version":"rw-source-claim-hints.v1","partition":{"variables":["x"],"grid":2},"derive":[{"variable":"y","equality_index":0}]}
```

`partition.variables` names existing variables, sorted in declaration order;
`grid` is power-of-two at most 1024. `derive` names an already declared equality
row and a variable with a nonzero coefficient in that row. The existing exact
verifier checks all generated mathematical constraints and derived bounds. A
missing hints file means the first non-fixed variable with a one-box partition
and no equality-derived tightening. Hints cannot add populations, constraints,
source facts, or claim trust. The candidate stores a canonical hints hash; an
explicit hints file also requires a separately supplied hash at replay.

## Reproducible source -> mathematical certificate flow

Work in a trusted, quiescent local directory. Generate SHA-256 pins independently
and retain them *outside* the files they attest; do not copy a digest from a
potentially untrusted bundle and mistake that for origin authentication.

```text
python -m researchwitness.source_claim_workflow compile \
  --source examples/source-claim-v1/bilinear.txt \
  --expected-source-sha256 SOURCE_SHA256 \
  --hints examples/source-claim-v1/bilinear-hints.json \
  --expected-hints-sha256 HINTS_SHA256 \
  --output-model NEW-model.json --output-candidate NEW-candidate.json
```

This creates **new** canonical JSON files without overwrite. The ordinary
`researchwitness.exact_optimization` verifier remains responsible for proof
mathematics. For a synthetic example, the old independent development fixture
`tools.optimization_examples.bilinear_half()` supplies a known valid exact
certificate (and `linear_resource()` supplies the other one). In real operation,
a prover or bounded proposal tool must produce the matching proof; an ordinary
source claim does **not** automatically have a certificate.

```text
python -m researchwitness.source_claim_workflow verify \
  --source SOURCE.txt --expected-source-sha256 SOURCE_SHA256 \
  --hints HINTS.json --expected-hints-sha256 HINTS_SHA256 \
  --model MODEL.json --expected-model-sha256 MODEL_SHA256 \
  --candidate CANDIDATE.json --expected-candidate-sha256 CANDIDATE_SHA256 \
  --certificate PROOF.jsonl --expected-certificate-sha256 PROOF_SHA256
```

The verifier first re-parses the exact source span, regenerates the candidate
and model, requires their canonical byte-for-byte equality, then reads and
checks **every** certificate leaf and partition against the pinned model. The
certificate's claimed upper bound must match the exact source-block bound;
substituting a looser but mathematically valid bound is refused. File reads use
existing regular-file/single-link/no-follow safeguards and size caps. Verification
returns only sanitized digests, offsets, mathematical status and unresolved
scientific-provenance flags; no original source quotation is copied to the
report or GitHub.

Alternatively, an **exact feasible counterexample** needs no global proof:

```text
python -m researchwitness.source_claim_workflow refute \
  --source SOURCE.txt --expected-source-sha256 SOURCE_SHA256 \
  --model MODEL.json --expected-model-sha256 MODEL_SHA256 \
  --candidate CANDIDATE.json --expected-candidate-sha256 CANDIDATE_SHA256 \
  --point POINT.json --expected-point-sha256 POINT_SHA256
```

Add the two hints arguments whenever the candidate was built using an explicit
hints file. The point file is a canonical JSON array of rational strings in
variable declaration order. The existing `verify_point` checks every variable
bound, every constraint and every product before the claim can be refuted.
An objective value equal to the upper bound does **not** refute it.

The checkout retains a compatibility CLI entry:
`python -m tools.source_claim_workflow`. The installed wheel's equivalent
`python -m researchwitness.source_claim_workflow` needs no third-party runtime
dependency and does not include the optional SciPy certificate producer.

## Engineering acceptance and limits

Positive synthetic fixtures are a tight bilinear bound (`1/4`) and a signed
linear allocation bound (`11`). A third synthetic claim `x <= 1/2` on
`0 <= x <= 1` is **refuted**, with exact witness `x=1` and margin `1/2`.
Adversarial tests cover malformed/duplicate/Unicode markers, changed source
bytes, CRLF byte offsets, ambiguous arithmetic, comments, negation, generated
model changes, candidate/proof/point external pins, mismatched claim upper
bounds, invalid proof branches, invalid feasible points, no overwrite, and
normal vs optimized Python mode. They do **not** measure detection rates on
unseen research papers.

Outside the grammar: natural-language interpretation, PDF extraction, source
rights/licences, publisher authenticity, true real-world work-family identity,
new-paper discovery accuracy, human-scientific adjudication, and protected
custody. The legacy original-source evidence gate remains 0/13; other planned
RW-06 components remain blocked by RW-01/RW-02 as recorded in the execution
ledger. The owner does not require external researchers for this internal
mathematical verification lane; their absence must not be mislabeled as
independent scientific review.
