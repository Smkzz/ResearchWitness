# Paper-audit capability wave qualification

**Evaluation status:** post-hoc development only; no wave 3 was run.  
**Wave-3 freeze readiness:** **not ready**.  
**Starting commit:** `8d91362437223c85c700fec92f857ef90e883d15`.  
**Starting tree:** `3c2d531b99176245ea9ac609e15d274ce12533b8`.  
**Development branch:** `codex/paper-audit-capability-wave`.  
The final commit/tree and the remote pull-request check state are reported with this committed qualification artifact. The exact commit and tree identifiers are supplied separately so they do not change the artifact they identify.

## What this branch supports

ResearchWitness now has a frozen source-aware `PaperDocument` model. It represents sections and hierarchy, paragraphs, tables, header paths, rows and columns, spans, cell identities, table metadata, footnotes and xrefs, numeric assertions, extraction confidence, and source-file hashes with element-path anchors. Text projection is a navigation view; it does not replace the table grid.

For JATS/XML inputs, the bounded parser reads `table-wrap`, `thead`/`tbody`/`tfoot`, labels, captions, nested headers, `rowspan`/`colspan`, footnotes, xrefs, table IDs, and source paths directly. It does not fetch external DTDs. It can remove external DTD references and expand known named entities; internal DTD/entity declarations and unknown entities fail closed. Byte, element, nesting, text, table, row, column, cell, and span limits apply.

The active JATS table arithmetic detector checks only a cell containing one integer count and one displayed percentage when the exact denominator is explicit in the applicable column header, the displayed precision is known, and no scope-changing cue is unresolved. It uses exact decimal arithmetic and `ROUND_HALF_UP` at the displayed precision. A mismatching result is an arithmetic candidate with source anchors; it does not establish which value is wrong or whether a conclusion changes.

The detector returns unsupported or incomplete for ambiguous grids, missing or conflicting header denominators, row-local or structurally indicated category-block denominators, footnoted operands/headers/row labels, weighted or adjusted estimates, missing-data cues, overlapping categories, and multiple responses. The category-block guard suppresses a block only when its count total is smaller than the header denominator and every displayed percentage rounds from that block total while at least one differs under the header denominator.

The Markdown pipe-table adapter remains a guarded legacy path. Markdown is not the canonical document model. PDF extraction remains a separate `pypdf` worker for prose/count discovery: it reports reliable, degraded, image-only/no-text, or failed extraction states, performs no OCR, and never runs PDF table arithmetic. It does not reconstruct table geometry.

## Detector contracts and current boundaries

The machine-readable registry is version 1.1 and records implementation status, required structure and operands, scope, rounding, exclusions, what a result establishes, and unsupported/incomplete reasons.

- **Active source-mapped behavior:** explicit prose count-marker discovery for text/PDF prose; exact count/percentage recomputation for eligible JATS tables; guarded legacy Markdown table arithmetic; and a narrow prose sample-flow locator that emits an unresolved relation only.
- **Pure helpers, not connected to paper-source results:** explicit additive/subtractive flow graph checking; crude risk ratio, odds ratio, and difference-in-proportions calculation from explicit unadjusted 2x2 operands; and cross-section numeric comparison under a complete identity key.
- **Not implemented as source-mapped detectors:** row/column or subgroup totals, percentage-sum checks, PRISMA/synthesis extraction, sample-flow graph extraction, 2x2 result mapping, mean/SD/SE or confidence-interval checks, z/t/chi-square and p-value checks, person-time/rate checks, and numeric assertion extraction across prose, abstract, tables, and conclusion.

Flow arithmetic requires an explicit graph, common fully specified scope, a declared operation, matching edges, and explicit disjointness and exhaustiveness. The current prose flow locator does not infer those facts. The 2x2 helper rejects missing operands, unspecified reference group/timepoint, adjusted or unknown adjustment status, invalid/oversized values, and zero-cell cases without a declared policy. The cross-section helper requires population, group, outcome, statistic type, timepoint, unit, and adjustment status; incomplete identity can yield only a possible-scope note. These helpers do not count as active paper detectors.

`paper_error_established` remains false for all paper-audit candidates. No paper-correct/paper-wrong verdict, fraud or misconduct score, researcher ranking, retraction claim, author contact, or automatic public posting is supported.

## Development corpus results

Eligibility was classified from the correction/source records before this current-code replay and bound to the source manifests and wave-2 locked output. This is development material: correction labels and prior candidates were visible during earlier development.

The reproducible direct-JATS replay covered **33 source documents**: 16 correction-backed issues and 17 selected controls. Current strict eligibility supports **1/16** correction issues overall. Conditional eligible-issue sensitivity is **1/1**, matching **2/2** target cells, from one wave-1 table-percentage correction. The other 15 issues are unsupported by current contracts. Wave 2 contributes **0/12 eligible** correction issues, so its eligible-sensitivity denominator is **0**, not 12.

The replay emitted three candidate items: two map to the one eligible correction issue, and one separate paper-020 Table 1 percentage candidate is unresolved. Candidate precision is **not estimated** because that candidate has not been fully adjudicated. Selected controls had **0/17 candidate-bearing papers** and zero candidate items; these controls are not certified error-free or matched hard negatives, so these counts are not a false-positive rate.

Table coverage was incomplete in **33/33** papers. Extraction succeeded for **33/33** and JSON/HTML replay was byte-repeatable for **33/33**. These results show low overall coverage and universal incomplete table coverage despite the conditional result on one eligible issue.

Wave-1 direct JATS results were 1/4 overall correction coverage, 1/1 eligible-issue sensitivity, and 2/2 target cells. Wave-2 post-hoc JATS results were 0/12 coverage, 0/0 eligible-issue sensitivity, and one unresolved candidate. The two strata and the older Markdown replay are kept separate in [`REPLAY_SUMMARY.json`](REPLAY_SUMMARY.json) and [`WAVE1_LEGACY_REPLAY.json`](WAVE1_LEGACY_REPLAY.json). The legacy run rendered JATS to Markdown and mapped three candidate items to two known correction issues; it missed the flow correction and treated the annualized-rate correction as unsupported. It is a representation comparison, not the direct-JATS performance estimate.

### Development adjudications

The separate wave-2 off-target track contains 15 historical candidates: 14 `VERIFIED_INTERNAL_DISCREPANCY` and 1 `KNOWN_CORRECTION`. The original JATS hashes were pinned. Supplementary-material resolution, full publisher PDF fidelity, comprehensive correction-history search, scientific or clinical consequence, and impact on conclusions were not assessed for those items. These are not discoveries, are not unseen, and do not imply that any paper is wrong.

The remaining post-hoc paper-020 JATS candidate is tracked separately in [`POSTHOC_JATS_CANDIDATE_REVIEW.json`](POSTHOC_JATS_CANDIDATE_REVIEW.json). It is **UNRESOLVED** and is excluded from candidate precision. The original 88 wave-2 candidates and their adjudications remain unchanged.

To regenerate the direct-JATS replay, retrieve source captures into local directories using the manifests, then run:

```bash
python tools/run_paper_audit_capability_replay.py \
  --wave1-source-dir /path/to/wave1-jats \
  --wave2-source-dir /path/to/wave2-jats \
  --output-dir /tmp/researchwitness-capability-replay
```

The runner checks pinned source hashes, eligibility-manifest bindings, report schemas, candidate-only report semantics, and byte-identical JSON/HTML across repeated runs. Publisher source captures and generated source copies are not committed.

## CI diagnosis

PR #5 at the starting head had no Actions workflow runs or check runs; the commit status was pending with zero status entries, and `refs/pull/5/merge` was unavailable. Both workflows at that head contained `pull_request` triggers, workflows were present on `main`, and successful pull-request Actions runs existed on PR #4. GitHub reported `mergeable=false` and `mergeable_state=dirty`. GitHub's Actions troubleshooting guidance says `pull_request` workflows do not run while a pull request has a merge conflict, making the merge conflict the best-supported cause. The connected API could not read Actions settings or workflow activation metadata, and the shell could not reach the remote, so a simultaneous settings or policy change cannot be ruled out. The evidence does not establish that the GitHub App/PR creation path suppressed the event. No CI configuration was changed to manufacture a status.

## Engineering gate and repository state

The baseline full gate passed before development on Python 3.12.14: 363 tests, 500/500 synthetic conformance cases, 3/3 historical verifier cases, static security/schema/checksum/compile checks, two identical wheel builds (`3a6c74162f39f2b1ff1ffba3639344431fef893c1bd9902eaf994fa21bc0d494`), clean install, and CLI smoke checks.

The final local quality gate passed on Python 3.12.14: **410 tests**, **500/500** synthetic conformance cases, and **3/3** historical verifier cases matched. Static trusted-core security scan, source checksums, generated schemas, capability examples, frozen-screen review, and compilation passed. Two builds produced identical wheels; offline installation and installed CLI, review, and paper-audit smoke checks passed. The final wheel SHA-256 is reported with the task's final gate evidence. This local gate is not GitHub CI. The direct-JATS replay used `tools/run_paper_audit_capability_replay.py`; its 33 reports and summary are recorded in `REPLAY_SUMMARY.json`. Remote branch/tree confirmation, Actions/CodeQL state for the new draft PR, and post-commit worktree cleanliness are reported with the final task result.

## Wave-3 decision and proposed protocol

Do **not** freeze or run wave 3 from this branch. Only one correction issue currently satisfies an active paper-source contract; all wave-2 correction issues are unsupported, every replayed paper has incomplete table coverage, and the remaining source-mapped detector families do not cover flow, synthesis, or paper-mapped statistics. The selected controls do not establish low false-candidate behavior on difficult matched negatives.

When the table-percentage detector is stable enough to qualify, preregister a wave-3 protocol before the custodian selects exact cases:

1. Limit the primary stratum to original JATS/XML sources and the frozen count/percentage contract. Exclude PDF tables. Report PDF prose separately; do not combine format-specific performance.
2. Have an independent custodian select approximately 15–25 eligible correction-backed positives and 15–25 matched difficult negatives if source and ground-truth quality supports those counts. Each positive must be mapped to the frozen contract from source operands and correction evidence before the detector runs. If fewer cases qualify, use fewer and report the limited precision; do not loosen eligibility.
3. Match negative tables on layout and trap type: grouped/ragged headers, All/No or treatment/control alignment, local and footnoted denominators, missingness, weighting/adjustment, overlap/multiple responses, timepoint or subgroup scope, and valid rounding. Include only traps relevant to the frozen detector and label them independently of its output.
4. Freeze the exact commit/tree, source manifest and hashes, schemas, contract registry, rounding policy, parser/runtime versions, configuration, wheel hash, runner, and scoring code. Publish a hash-addressed manifest and custodial signature before execution.
5. Separate roles as far as the environment permits: the custodian holds correction labels and eligibility; the runner receives originals and writes/locks JSON, HTML, and source-model hashes before adjudication; an adjudicator maps locked candidates to ground truth afterward. Document any shared-workspace limitation and do not call the run sealed if labels can reach the runner.
6. Report numerators and denominators for eligible-positive sensitivity, overall correction coverage, candidate precision, false candidates per negative paper, negative papers with at least one false candidate, unresolved candidates per paper, supported-check completion, extraction failures, incomplete table coverage, repeatability, and source-format agreement only where both formats support the same check. Use exact binomial 95% intervals for paper-level proportions; keep issue/candidate clustering by paper visible and do not treat candidate cells as independent papers.

If the eligibility pipeline cannot produce a sufficient matched corpus for the table contract, continue development rather than running wave 3. Add flow/PRISMA or statistical results only after they have source mappers, independently defined contracts, and their own matched development negatives.

## Final qualification run
