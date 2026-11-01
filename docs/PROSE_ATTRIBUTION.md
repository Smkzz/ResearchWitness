# RW-MATH-04: source-declared literal context (development-only)

This is an optional, offline, **declared-context** layer over the existing
[RW-MATH-03 literal screen](PROSE_MATH_CANDIDATES.md). It never authenticates
an author's intention, a publisher, or a scientific publication error.
Version `0.3.0.dev0` remains **UNRELEASED**.

## Why this separate profile exists

A mathematically false sentence can be an example, quotation, hypothesis or
superseded statement. The source-anchored arithmetic from RW-MATH-03 is valid
for the literal sentence regardless of its surrounding prose. Treating that
literal result as a publication error would be unsound.

This tool **never infers context from free-form prose**. A declarant must
explicitly mark a complete source sentence. Markers are themselves untrusted
source declarations, not independent evidence of an author's actual intent.

## Strict three-line grammar

The accepted block is exactly three adjacent physical UTF-8 lines:

```text
RW-MATH-CONTEXT-BEGIN v1 id=claim1 role=asserted
For all real x in [0,1], x <= 1/2.
RW-MATH-CONTEXT-END v1 id=claim1
```

Replace `role=asserted` with one of `asserted`, `quoted`, `negated`,
`hypothetical`, `corrected`. The source-local ID matches
`[a-z][a-z0-9_]{0,31}`, is unique, and must match on both markers.
The body must be **one complete line** accepted by RW-MATH-03's precise
universal affine-inequality grammar over 1–3 bounded independent real
variables. No second line, prefix, suffix, comment, nesting, silent inference,
assumption from adjacent paragraphs or partial quotation is allowed.

All marker-like malformed lines are fatal, not silently ignored. Original
LF/CRLF/UTF-8 bytes, zero-based half-open byte spans, source hash, literal
hash and both marker hashes are retained. An unmarked valid literal stays
`unattributed`; unrecognized surrounding prose stays uninterpreted.
At most 64 source-declared blocks, 64 literal candidates, 12,000 source
lines, 1 MiB of source and 1 MiB of report are supported.

## Exact same-math negative control

[Invented fixture](../examples/prose-attribution-v1/illustrative-source.txt)
places the exact same mathematically false sentence once in a
`role=asserted` block and once in a `role=quoted` block, **in one source**.
Both compute the same model, exact certificate, maximum `1` and violation
margin `1/2`. Their labels deliberately differ:

```text
declared_asserted_literal_refuted
declared_quoted_literal_refuted
```

These labels mean **declared by the supplied source**, not verified as an
author assertion or a true correction record. Quoted/negated/hypothetical/
corrected roles cannot become author-error accusations. A declared
`asserted` role does not itself authenticate author attribution either.
All outputs retain `paper_error_established: false`,
`author_intent_authenticated: false`,
`publisher_source_authenticated: false`, and
`surrounding_prose_adjudicated: false`.

## Strict scan and byte-identical replay

In a trusted, quiescent directory, record the exact original UTF-8 source
SHA-256 **externally** to the generated report:

```text
python -m researchwitness.prose_attribution scan \
  --source PRIVATE_SOURCE.txt \
  --expected-source-sha256 EXTERNAL_SOURCE_SHA256 \
  --output NEW_PRIVATE_REPORT.json
```

Save the SHA-256 of those report bytes outside the report and replay:

```text
python -m researchwitness.prose_attribution replay \
  --source PRIVATE_SOURCE.txt \
  --expected-source-sha256 EXTERNAL_SOURCE_SHA256 \
  --report NEW_PRIVATE_REPORT.json \
  --expected-report-sha256 EXTERNAL_REPORT_SHA256
```

Reports are created exclusively, never overwritten. Replay checks the
report's external pin, parses all JSON with strict duplicate-key and numeric
refusals, regenerates every annotation and mathematical field **from the
same externally pinned source bytes**, and compares canonical report bytes.
Raw source sentences are not copied to the report. Derived mathematics may
still be sensitive; reports inherit original article-specific privacy/rights
rules. Source bytes are never executed.

## Limits and scientific interpretation

The only accepted formal premises are the exact independent bounded-real
intervals written **inside the literal sentence**. Other real-paper
qualifiers, populations, source sections, statistics, weights, units,
correction lineage, peer review, licence/rights, publication authenticity,
and scientific correctness are **unverified**. A byte hash establishes
continuity relative to its trusted external pin, not publisher origin.
A newly annotated source is not necessarily an original publisher artifact.

No generic NLU, PDF/OCR processing, external network, billed model,
external researcher, author contact, protected custody, new permission or
paper-error conclusion is part of this slice. The project-wide RW-01O #35,
RW-01Q #50, RW-03 and RW-06 gates remain unchanged. Engineering tests
and AI review are not scientific precision/recall measurements.
