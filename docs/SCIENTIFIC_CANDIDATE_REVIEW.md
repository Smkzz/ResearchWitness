# Public scientific candidate review handoff

This workflow creates **development candidates** from public metadata. It does not establish that an article contains an error, that a formal correction applies to the same data scope, or that a candidate is eligible for the frozen v1.3 evaluation.

## Run a metadata search

Use only the approved public API hosts configured in `tools/public_discovery.py`:

```bash
python tools/discover_public_candidates.py discover \
  --provider europe-pmc --limit 25 \
  --output validation/public-candidate-registry.json

python tools/discover_public_candidates.py discover \
  --provider crossref --limit 25 \
  --existing validation/public-candidate-registry.json \
  --output validation/public-candidate-registry.json

python tools/discover_public_candidates.py summarize \
  validation/public-candidate-registry.json
```

The collector is a tool outside the trusted `researchwitness` core. It is read-only, requires HTTPS through the inherited managed proxy, rejects proxy-bypass routes and cross-host redirects before following them, caps response sizes, and enforces a one-second per-host request-start interval across collector processes using a verified private per-user state directory and file. It stops on an access or transport failure. It does not follow DOI links to publishers, use credentials, retry a denial, or retain article full text. The recorded SHA-256 is for the returned metadata response, not for the original article or correction.

Search hits are only metadata leads. An independent reviewer must capture the original and correction versions from a permitted public source, verify the applicable license, record content hashes and stable source anchors, and compare the exact numerical statements and scope. The code's percentage recomputation is only arithmetic at the printed precision; it cannot resolve cohort, denominator, table, or correction scope.

## Offline JATS table aid

For a cohesive JSON and Markdown workflow, use the
[offline research audit and comparison CLI](OFFLINE_RESEARCH_AUDIT.md). It
preserves structured abstentions and source-bound benchmark outcomes.

For a locally captured UTF-8 JATS XML file, the bounded external tool can scan simple table cells without making network requests:

```bash
python -m tools.jats_percentage_audit path/to/article.xml
```

The tool records the supplied file's SHA-256 and byte anchors for table cells and denominator evidence. It evaluates paired `n (%)` cells, explicit `n/N (%)` cells, and explicitly headed count/percent columns, using the contract's half-up rounding rule at the printed precision. An `n/N (%)` cell supplies its own row denominator; comma-grouped integer counts and denominators are accepted only with valid three-digit groups. It reports an `arithmetic_mismatch_candidate`, never a paper error. It abstains when denominator scope is unclear, including conflicting unscoped denominators, row-specific `n (% n/N)` notation without a reported row denominator, unsupported header spans, a source-stated rounding convention it does not model, or a document/table note about adjusted or weighted percentages that is not mapped to the row. When the table has separate, explicitly headed `n`, `N`, and percent columns, it uses that row's `N` cell and preserves byte evidence for the value or a missing-cell abstention. It bounds XML size and structure and rejects DTD/entity declarations.

This is a development aid outside the trusted core. It supports JATS XML only: it does not parse PDFs or OCR, preserve publisher layout semantics, authenticate the source, or establish scientific error. A source hash commits to the bytes supplied to the tool, not to their origin.

## Offline PDF table aid

For a local, text-based PDF, the bounded tool runs Poppler's `pdftotext` inside a locally provisioned, SHA-256-pinned Docker image. Set the image ID from a separately reviewed minimal sandbox image, then run:

```bash
export RESEARCHWITNESS_PDF_SANDBOX_IMAGE='sha256:<64 lowercase hex digits>'
python -m tools.pdf_percentage_audit path/to/article.pdf
```

The image must contain `/usr/bin/pdftotext` and its required runtime files, with no baked environment variables, entrypoint, or volumes. Keep credentials, article collections, development workspaces, and other unrelated files out of the image. The runner verifies the local image ID and those image settings, uses an empty Docker client configuration and the local Unix socket, and requires `docker info` to report the built-in default seccomp profile. It lets Docker apply that default rather than passing a non-portable `seccomp=builtin` option. PDF bytes pass through standard input without a host-file mount; the runner clears proxy variables inside the container and uses `--network none`, a read-only root, an unprivileged UID, no capabilities, no-new-privileges, and bounded memory, CPU, process count, temporary storage, output, and time. A per-run CID file records the ID, and a `finally` path removes only that verified container ID after success, timeout, or output-limit failure; missing ID or failed cleanup prevents returning extracted text. It never falls back to running Poppler on the host; absent Docker, a missing or mismatched image, an unavailable seccomp profile, or unsupported isolation flags cause the audit to fail closed. A digest pins the selected image bytes; it does not establish who built them or inspect their filesystem. The operator must review the image layers and provenance before configuring the aid.

The tool accepts only a bounded PDF byte stream and preserves its existing source-size, extracted-text, page, table, row, and time limits. It records the PDF SHA-256, extracted-text SHA-256, table title, page/line, and character offsets within the extracted page text. Those offsets are not byte positions in the PDF. The parser handles simple single-value `count (percent)` rows with a nearby explicit denominator. Where a percent column is not labeled, it infers percentage context only when at least two rows and at least half of the rows match the displayed denominator; all results remain candidates for human review. It abstains on conflicting or row-specific denominators, unmapped table-local adjustment/weight notes, stated rounding conventions, and unsupported layouts. Image-only PDFs and OCR are unsupported. The tool does not ingest methods from a separate article file, so a reviewer must still check article-level weighting and adjustment rules.

This is a development aid outside the trusted core. Text extraction can lose layout meaning, and a hash does not authenticate a file's origin. A mismatch candidate is not proof of a scientific error or correction eligibility.

## Adjudicate a correction-backed positive

For each proposed positive, the reviewer should independently:

1. Confirm the original article and version, then confirm the separate authoritative correction and its publication date.
2. Verify the exact original and corrected numerical statements from those sources and preserve source hashes and provenance.
3. Recompute the relationship and check that the correction covers the same table, population, cohort, denominator, and units.
4. Record whether the issue satisfies the frozen contract v1.3 and document every unresolved ambiguity.
5. Confirm exposure history. A candidate found by this development workflow is exposed and must never be called an untouched holdout case.

## Adjudicate a correct negative relationship

For each proposed negative, independently verify the published version and exact source location; identify the numerator, denominator, reported percent, display precision, population and subgroup; recompute using the contract's rounding rule; and record ambiguity rather than infer denominator scope. Resolve DOI aliases, versions, supplements, and related records into work families. Count at most one independent work per confirmed family, regardless of how many tables or rows it contributes.

## Keep evaluation evidence separate

This registry intentionally has no field that can mark a developer-discovered candidate as a holdout. Independent review of a development candidate may support development or a demonstration set; it does not create an untouched evaluation example. Only the authorized custodian can update the private qualification record. Public reports may carry approved aggregates and integrity commitments, never reserved identifiers, labels, correction targets, or private custody records.

## Source access and failure handling

Provider failures and source-access denials are distinct from successful zero-result searches. Treat challenge pages and other non-document responses as access failures, never as research content; preserve source hashes only for complete retrieved documents. Stop after an access denial, and do not use an alternate host, proxy, or route to bypass it. A failed request does not establish that no relevant publication or correction exists.
