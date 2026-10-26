# Rich JATS table projection — RW-01D

**Scope:** Opt-in engineering model; not a publisher authentication, population inference, a new checker family, or a scientific accuracy evaluation.

## Purpose

The installed audit-jats command already extracts bounded arithmetic candidates, source-byte anchors and conservative abstentions. Passing --include-structure additionally projects the same original, unmodified UTF-8 JATS into the existing immutable PaperDocument type. The old XML-normalizing legacy parser is NOT activated. This is one parser and one installed audit entry point.

## Commands

From an installed environment, using a new output directory under a trusted existing parent:

    python -m researchwitness audit-jats examples/synthetic-jats/article.xml --document-id synthetic-jats --output-dir out/structured --include-structure
    python -m researchwitness replay-jats out/structured --expected-manifest-sha256 EXPECTED_HASH_FROM_AUDIT

The JSON report contains table_projection when requested, including source hashes, full XML element byte ranges, header hierarchy, body rows, table spans and warnings, row/column roles, cross-references, footnotes, selected numeric surface forms, and source-bound detector assertions. Original XML and offline HTML are retained in the same manifest-validated private bundle. Without the flag, the original smaller report remains available.

## Source and interpretation limits

- An element's start_byte:end_byte range includes original XML markup. A quote is the complete normalized element text. These are different kinds of location, not interchangeable literal quote offsets.
- Headers, caption N cues, row labels, footnote references, source versions and detector denominator facts are recorded as traceable evidence, never silently treated as verified scientific population or denominator scope.
- Bare numbers or mean(SD) pairs are not automatically classified as percentages. Source percent tokens or unambiguous matching column headers are required; conflicting headers on a spanning body cell preserve all header references but suppress inferred numeric roles.
- Header spans and row/column layouts preserve warnings on malformed or missing structures. Duplicate source-assigned table IDs receive distinct indexed model identities and explicit warnings; no guessed publisher identity is introduced.
- An asserted denominator is included in a numeric assertion only if the unchanged detector reports a resolved arithmetic relation. Conditional and unknown denominators remain absent. A trusted reviewer must still verify source correspondence and applicability.
- The projection does not reconstruct scientific narrative sections or figures. Missing population, outcome, group, timepoint or adjustment fields remain null; their identity_key remains unavailable.
- extraction_confidence=0.0 is an uncalibrated placeholder, not a probabilistic quality score. Inspect structure_status and limitations instead.
- A large opt-in projection can exceed the fixed report byte limit; it fails closed rather than truncating source data. Default audit behavior is retained.
- Supplied detector reports are recomputed against original source bytes before being projected, preventing altered numerator, percentage, denominator or status fields from forging source-linked assertions.
- Replaying a bundle checks recorded source and implementation bytes, not original publisher authority. An independently retained manifest digest is necessary to detect coherent changes; hashes cannot prove scientific validity.

## Engineering acceptance and next work

The tests exercise nested/cross-spanning headers, original Unicode byte anchors, footnotes, malformed and missing layouts, duplicate IDs, source-version mismatch, explicit/unknown denominators, optional installed CLI and bundle replay. Exact-head CI and post-merge checks are required; no frozen real-world scientific corpus was processed.

Next RW-01 work is source-mapped ratios, flows and richer denominators from legacy PR #6–#11. They must use the preserved original-byte model without widening source interpretation. PR #12's protected custody/unsafe runtime is separately unqualified and remains disabled.

## Opt-in unadjusted 2×2 odds ratio relationship

An additional opt-in source checker consumes this bounded original-byte table
projection for exactly labelled single-row unadjusted odds ratios, without
modifying its model. See [the 2×2 review contract](JATS_2X2_RATIO_REVIEW.md).
Its strict structural acceptance is **not** an assertion that the paper's
scientific populations are authentic or comparable. Ineligible rows abstain.

## Optional standalone body-prose paragraphs

`project_jats_tables(..., include_body_paragraphs=True)` also returns
bounded `Paragraph` objects anchored to original XML **element**
start/end offsets. Quotes remain whitespace-normalized; bytes are not
guessed for individual projected words. It does not fill the document's
scientific section hierarchy, text around figures, or captions. The default
projection remains exactly table-only.

The new [prose sample-flow contract](JATS_PROSE_FLOW_REVIEW.md) describes the
separate opt-in `audit-jats --include-prose-flows` interpretation and its
abstentions. It does not infer whole-paper scientific context.
