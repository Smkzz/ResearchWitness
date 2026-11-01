# RW-MATH-03: conservative unmarked mathematical sentence screening

**Engineering scope:** Optional, offline mathematical development aid added on
1 November 2026. Package `0.3.0.dev0` remains **UNRELEASED**. This does not
complete RW-06, protected research evaluation or general scientific-paper
interpretation. RW-MATH-01's installed rational checker and RW-MATH-02's explicit
marked-block compiler retain their existing behavior.

## Motivation and exact trust boundary

Prior RW-MATH-02 can only compile explicitly marked seven-line blocks. The
new `researchwitness.prose_math` identifies a **very narrow literal English
sentence** even when it is embedded in otherwise unstructured UTF-8 text.
For a recognized sentence the new module constructs a bounded-real affine
model and uses `researchwitness.exact_optimization` to verify a single-box
rational upper-bound certificate and an exact attaining endpoint. It can thus
mathematically confirm or refute **the formalized sentence**, but it cannot
infer whether a scientific author asserted that sentence, quoted it as a false
example, corrected it elsewhere or relied on unparsed assumptions.

All candidate reports permanently include `surrounding_prose_adjudicated: false`,
`is_pub_claim_or_quotation_resolved: false` and `paper_error_established: false`.
The full-text source origin, publisher, peer-review status, licence/rights,
research independence, source-to-model applicability and scientific accuracy
remain **unverified**. A mathematical counterexample is *not* a publication
error finding. An empty result is *not* proof that a paper contains no errors.

## Precisely supported sentences

The following complete source lines are supported (spaces shown literally):

```text
For every real x in [0, 1], 2*x + 1 <= 3.
For all real x in [0,1], x <= 1/2.
For any real x in [-1,2] and real y in [0,3], 3*x+2*y+5 is at most 17.
For every real x in [0,1] and real y in [0,1] and real z in [0,2], x+y+z ≤ 4.
```

Grammar version `rw-unmarked-one-real-affine-universal.v1` (historical name;
the v1 implementation accepts **one to three independent bounded real
variables**):

- Sentence begins exactly with `For every`, `For all` or `For any`, then
  one to three `real name in [lower,upper]` declarations joined by the literal
  ` and `. The quantifier is universal over the Cartesian product of the
  explicitly declared **closed**, non-degenerate real intervals.
- Names are unique lowercase ASCII identifiers. Bounds and claimed upper
  values are canonical integer or reduced rational strings. An interval
  has lower strictly smaller than upper; a singleton domain is not in this
  grammar and is not silently expanded.
- The objective expression supports only the tested bounded AST subset:
  integer/rational constants, declared variables, exact rational affine
  arithmetic, parentheses and rational scaling/division. It never executes
  Python or uses floating point. All variable-by-variable products, powers,
  calls, arrays and variable denominators are unsupported.
- An assertion has a single `<=`, the Unicode glyph `≤`, `is at most`, or
  `is no greater than` followed by one exact rational literal and a final
  period. These forms mean the same non-strict inequality. No other text,
  prefix, suffix, inferred units, extra assumptions or unbounded quantifier
  is accepted on that line.
- Whole-line matches only. A paragraph containing related words or formulas
  does not qualify. Quotation markers, Markdown quote prefixes, inline
  hedges/negation, strict `<`, percentages, approximation, rounding,
  adjusted models and implicit restrictions do **not** match.

The mathematical model includes **only** those independent real closed bounds
and the extracted affine expression, with zero extra constraints. Its maximum
is attained at a corner. The installed exact verifier checks the whole-box
rational upper bound, while `verify_point` checks the same attaining point.
When the maximum exceeds the literal upper value, the reported strict margin
is an exact rational. The source context remains unresolved either way.

This is **not** an unrestricted natural-language model and is not a claim of
broad formula extraction. Expanding to conditional constraints, multiple
quantifier alternations, integrality, statistical effect estimates,
unit conversions, source-section interpretation and general PDFs requires
new separately tested syntax and source-containment evidence.

## Run, store and replay without network or paid providers

In a trusted, quiescent directory, save an **external** SHA-256 of the original
source bytes. The scanner hashes and parses those same bytes, including
Unicode text elsewhere and original LF/CRLF line endings. It reports zero-based
half-open **UTF-8 byte** spans excluding the line terminator; `sentence_sha256`
hashes exactly that slice. Reports contain no raw quoted source text, but they
do contain derived mathematical models and possibly sensitive numbers; treat
them under the same article-specific rights/privacy rules as their source.

```text
python -m researchwitness.prose_math scan \
  --source PRIVATE_SOURCE.txt \
  --expected-source-sha256 ALREADY_SAVED_SOURCE_SHA256 \
  --output NEW_PRIVATE_REPORT.json
```

The output file is created exclusively, never overwritten. Save its reported
SHA-256 **outside** that report and replay from the original source:

```text
python -m researchwitness.prose_math replay \
  --source PRIVATE_SOURCE.txt \
  --expected-source-sha256 ALREADY_SAVED_SOURCE_SHA256 \
  --report NEW_PRIVATE_REPORT.json \
  --expected-report-sha256 SAVED_REPORT_SHA256
```

Without `--output`, `scan` writes the deterministic JSON report to stdout.
The CLI uses no `eval`, solver, network, AI model, external contact or secret.
An unsupported sentence is **not** an accepted mathematical candidate; a
malformed source, external pin mismatch, over-limit input or tampered replay
fails with nonzero exit and no successful report.

The report includes all physical lines counted under LF delimiters,
`literal_candidates`, `unrecognized_lines`, and the exact line indices of
some unsupported candidate-like sentences beginning with an admitted
quantifier. Other unrecognized prose is not semantically audited. Every
report states `entire_article_semantics_examined: false` and
`absence_of_errors_established: false`, including when all recognized
sentences mathematically pass.

## Deterministic example and adversarial qualification

The repository's entirely fabricated example is
[`examples/prose-math-v1/illustrative-source.txt`](../examples/prose-math-v1/illustrative-source.txt).
It intentionally contains a refutable literal sentence in a discussion of
false claims to demonstrate why a formal result cannot be attributed to an
author or called a publication error.

Tests cover exact signed/fractional arithmetic, up to three independent
variables, negative slopes, attaining points, strict counterexample margins,
multiple lines with multibyte Unicode and CRLF byte offsets, unsupported
natural language, quoted/negated/approximate text, duplicate variables,
unbounded or special domains, malformed rational and AST input, tampered
source/report external pins, duplicate JSON keys, source file symlinks and
hardlinks, full input/line/candidate budget rejection, file overwrite and
`python -O` consistent behavior. Additional separately delegated AI reviews
were used for engineering scrutiny; they are not independent human review,
a research benchmark or external scientific validation.

**Open science gate:** Historically missing original PMC research bytes,
licence qualification, independent source-context labels, source-custody
isolation, and any measured new-paper discovery precision/recall are all
unchanged. Do not use this optional scanner to bypass those gates.
