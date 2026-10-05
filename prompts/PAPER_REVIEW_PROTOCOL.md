# ResearchWitness broad paper-review protocol

This protocol prepares a structured review ledger. The reviewer may be a person or an AI research agent. It is an investigation aid, not a proof authority, plagiarism detector, misconduct classifier, or guarantee that all errors have been found.

## Preserve the paper version

1. Start with the exact text capture and version under review. Keep the source identifier and version explicit.
2. Use `review-scaffold` to copy the source bytes into a new review workspace. The scaffold marks source identity `unverified`; change it to `captured` only after checking the text against the stated source/version.
3. Keep supplements, data excerpts, calculations, and other review evidence as local files. Do not silently edit the paper capture or normalize values without recording the transformation.

For an initial machine-generated lead list, `paper-audit paper.pdf --output screening/paper` preserves the input and searches extracted text for conflicting explicit `n=` / `N=` integers. It may help locate passages, but does not establish that counts have the same scope. A clean scan is not evidence that other errors are absent. PDF text extraction is optional, performs no OCR, and may be partial; use `review-scaffold` on the verified text capture for the actual review record.

## Review every area

For each area in `review.json`, record the method used, what was in scope, limitations, and any evidence files. Choose one status:

- `not_reviewed`: no substantive review was done;
- `reviewed_no_findings`: the recorded procedure found no candidate issue in its stated scope;
- `findings_recorded`: one or more active findings are attached;
- `unsupported`: an attempted review could not be completed with available material or methods;
- `not_applicable`: explain why the area does not apply to this paper.

Review areas:

1. **Source and citation integrity:** cited sources, dates, versions, quotations, bibliography metadata, and whether references support the nearby claims.
2. **Internal consistency:** definitions, notation, units, labels, assumptions, equation/table/figure references, and agreement between sections.
3. **Mathematics and logic:** algebra, boundary cases, quantifiers, proof steps, theorem hypotheses, counterexamples, and derivations.
4. **Statistics and quantitative reporting:** sample sizes, denominators, summary arithmetic, uncertainty intervals, test assumptions, model specification, multiplicity, and consistency between tables and prose.
5. **Data integrity and provenance:** stated sources, transformations, exclusions, missingness, duplicates, aggregation, and correspondence between described and supplied data. An anomaly alone does not establish fabrication or intent.
6. **Methods and experimental design:** controls, measurement validity, selection, confounding, randomization, blinding, stopping rules, preregistration, and whether the design supports the stated inference.
7. **Code and computational reproducibility:** code/data availability, environment and dependency records, seeds, numerical stability, implementation-to-method alignment, and independent replay where possible. Never execute paper-supplied code inside the deterministic verifier.
8. **Figures and tables:** axis scales, units, labels, captions, denominators, omitted values, uncertainty marks, and agreement with source data and prose.
9. **Interpretation and scope:** causal language, generalization, subgroup claims, null results, uncertainty, limitations, and whether conclusions exceed the design or evidence.
10. **Ethics and reporting requirements:** approvals, consent, registration, disclosures, required reporting items, and consistency between statements and supplied records. Flag missing evidence; do not infer misconduct.

## Record candidate findings

Every finding needs a stable ID, area, precise location, short statement, exact quote from the captured paper, rationale, and supporting local evidence. If the quote appears more than once, include `quote_offset`. Use one of these statuses:

- `candidate`: an observation that needs independent review or a stronger check;
- `unsupported`: a suspected issue that the available review method cannot resolve;
- `dismissed`: a candidate that was examined and dismissed, with the reason preserved;
- `formalization_replay`: a link to a separate ResearchWitness bundle for a bounded deterministic replay;
- `tabular_summary_replay`: a link to a `check-summary` input that recomputes exact descriptive statistics.

Only `formalization_replay` can include a checker bundle path, and only `tabular_summary_replay` can include a summary-check input path. The validator checks exact source bytes and quote offsets for linked formalization bundles, checks linked source identifiers, versions and quotes, then reruns the check. `check-summary` supports one numeric column supplied as rational values or read from a bounded local CSV/TSV file. File inputs select a unique header name or zero-based index, and explicitly declare missing-value markers and whether to reject or drop those records. Every record is processed in order; arbitrary filtering, grouping, weighting, and transformations are not performed. Integers, rational strings, and finite decimals are parsed exactly. Set an explicit tolerance based on how the paper rounds the statistic. A mismatch proves only that the extracted values disagree with the supplied reported number beyond that tolerance. Neither replay authenticates the publication or proves that the supplied data match the author's analysis.

Do not call an agent observation “verified,” “confirmed,” or “a paper error” based only on agreement between models, an optimizer result, a suspicious plot, a metadata search, or an unreplicated script. Keep unsupported and unresolved observations visible.

## Validate and interpret the ledger

```bash
researchwitness validate-review review.json --html review.html
```

The validator checks source quote anchors, evidence paths and hashes, review-area accounting, and any linked formalization replay. `all_areas_accounted_for: true` means the ledger has no area left `not_reviewed` or `unsupported`; it is not an assurance of exhaustive coverage. `reviewed_no_findings` means no candidate was recorded within the method and scope stated by that reviewer. The report always sets `paper_error_established` to `false`.

Use `researchwitness audit` for a narrow claim that fits a proof checker, and `check-summary` for a reported descriptive statistic that can be recomputed from one numeric column. If a file is used, include it in the review workspace so the validator records its byte hash and exact selected records. If no available method faithfully represents a finding, preserve it as a candidate or unsupported item rather than forcing it into an unrelated check.
