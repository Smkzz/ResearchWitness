# ResearchWitness next campaign report

**As of:** 2026-10-15  
**Repository:** `Smkzz/ResearchWitness`  
**Pull request:** [#13](https://github.com/Smkzz/ResearchWitness/pull/13), open and draft  
**Reviewed code commit:** `bd13eacf379f77a52133e9059b4d9a7a42a0a895`  
**Parent PR head:** `4e2cdee52fbf109d50ed7e9bef62e6073daa81a5`  
**JATS detector SHA-256:** `3d93b3f90ac17a84f51af28bb8a705db34aacba6fd7b5548559f666478cc6320`

This report contains sanitized aggregate results and integrity commitments only. Full text, source IDs, per-relationship evidence, and detailed candidate states remain outside Git in the owner-review package. The reviewed code commit above includes the final detector safeguards described here; this report/checkpoint may be committed separately and can advance the PR head.

## Work completed

- Added bounded source-anchored conditional calculations when an article-text group sample size exactly matches a group explicitly named in a table or column. Conflicting values, ambiguous labels, and over-limit context fail closed. The denominator remains null and the result remains an abstention.
- Integrated both source spans into Markdown audit output and validated evidence anchors nested inside conditional calculations.
- Added regressions for grouped zero-count denominators, exact group-label matching, unrelated and conflicting groups, the context limit, integrated abstention reporting, and invalid nested anchors.
- Replayed historical, live-PR, and improved JATS implementations against the same source-bound annotation set; generated a deterministic JSON/Markdown relationship comparison and passed `--require-no-regression`.
- A read-only independent model diff review found three actionable issues in conditional group matching, semantic anchor validation, and nested-paragraph scan cost. The fixes now reject specific unmatched headers and negated/generic labels, validate article/table roles and sample-size linkage, and scan each outside-table paragraph subtree once.
- Replayed the reviewed detector on the same exposed v1 sample. It preserved relationship-level metrics while reducing conditional mismatch calculations from 16 to 4; the remaining four depend on the explicitly hypothetical displayed-denominator assumption for missing data.
- Ran the offline audit CLI against a hash-checked public JATS source. It emitted schema-valid JSON and Markdown and stated that the hash did not authenticate provenance.
- Preserved, without rerunning after detector changes, the separate prospectively registered v2 development experiment already recorded in the PR’s sanitized aggregate ledger.

## Historical development replay

The owner-review archive SHA-256 `71b7f8df399ebeea123bf46ab4cb89d7d6836cb4465b8e3abd7ef984355084a5` was reverified. The original sample selected 20 records and acquired 13 JATS sources; 8 safely parsed and 5 were refused by the DOCTYPE/ENTITY guard. Those 8 works are below the original ten-document minimum. The sample inspected 34 tables and has 423 developer-supplied, source-cell relationship annotations. It is not an independent gold set.

| Replay | Parsed / failed | Tables | Relationships surfaced | Matches | Mismatch candidates | Abstentions | Incorrect denominators | Reference discrepancies missed | Conditional mismatches |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Frozen historical (`5d251c8`) | 8 / 5 | 34 | 239 | 20 | 0 | 219 | 6 | 16 | 0 |
| Live PR head (`68bd0e3`) | 8 / 5 | 34 | 423 | 205 | 3 | 215 | 0 | 13 | 4 |
| Pre-review implementation (`090ff4f`) | 8 / 5 | 34 | 423 | 205 | 3 | 215 | 0 | 13 | 16 |
| Reviewed implementation (`bd13eac`) | 8 / 5 | 34 | 423 | 205 | 3 | 215 | 0 | 13 | 4 |

The six historical incorrect denominators were comma-group truncations in zero-count cells (`205,488` and `304,997` source populations). The active PR and improved replay assign none incorrectly. Regression tests cover both grouped values.

The reviewed implementation does not change extraction coverage, arithmetic matches, ordinary mismatch candidates, abstentions, or missed discrepancy references from the pre-review implementation. It removes 12 false conditional mismatch calculations caused by caption fallback across a specific unmatched group header or weak label matching. Eight article-group calculations remain, with distinct source-linked group and table evidence; four additional calculations remain conditional missing-data checks. All 423 source anchors validate; there are zero anchor failures and zero candidate false positives against the supplied annotations. These developer-exposed results do not estimate precision or scientific-error detection.

The post-review private run manifest SHA-256 is `fa6294ff5e56f6ef68ea573a079f19a7c23c39716c5932294a96d52026258c9a`; its comparison JSON and Markdown commitments are `f4b6c1dbfe71317e195c52c8382d181a8043482df842ef66e40afd77f9f264da` and `b2dd823b190b04c1c15f23163d3050ab2baca82ca088553847032bc770da65c6`. The detailed outputs remain in the separate owner-review package.

## Separate prospectively selected v2 development experiment

The checked-in aggregate [`validation/development-percentage-campaign-20261015.json`](validation/development-percentage-campaign-20261015.json) and its owner-review package record protocol `RW-GEN-2026-10-15-v2`, frozen detector bytes, selection manifest, and their integrity commitments. The protocol reports that it was frozen before metadata/full-text acquisition. This finite Europe PMC frame was not a random sample of all science. Thirty primary works were selected from a 1,000-record metadata frame, with twelve preregistered reserves; all primary records were attempted and no reserve was needed.

| Outcome | Frozen v2 result |
|---|---:|
| Primary works attempted | 30 |
| Permitted, safely parsed works | 18 |
| DOCTYPE/ENTITY refusals | 9 |
| Conservatively withheld for license uncertainty | 3 |
| Unused registered reserves | 12 |
| Tables inspected | 51 |
| Frozen-detector relationships | 590 |
| Matches / mismatch candidates / abstentions | 175 / 7 / 408 |
| Source-anchor failures | 0 |
| Detector relationship-bearing / source-located numerical works | 11 / 13 |
| Additional relationships in a partial source census | 84 |
| Additional matches / supported missed arithmetic candidates | 82 / 2 |

The protocol’s development completion criteria were met: 18 safely parsed works, 13 source-located numerical works, four metadata strata, and multiple table-layout classes. The run is descriptive development evidence. Model source review classified five of seven automatic candidates as supported arithmetic candidates and two as unresolved rounding-balancing cases; the partial census found two additional supported arithmetic candidates. Human scientific adjudication was **NOT RUN**; no scientific error was established. Work-family independence remains provisional. Three license-uncertain sources stayed excluded; later license-text inspection did not retrospectively repair the frozen run.

The new group-context implementation was **not** run on this v2 sample after its freeze. Doing so would be post-freeze reuse, not an independent generalization result. The v2 results and all failures remain unchanged.

## Error and candidate interpretation

- **Corrected in prior PR work:** the six historical grouped-count denominator truncations are absent in the active PR.
- **Improved in this commit:** unmatched specific column groups no longer inherit a different group from a caption; negated and generic label matches are rejected; article/table evidence role, sample-size agreement, and conditional arithmetic are validated. Nested paragraphs are scanned without repeated recursive text reconstruction.
- **Still missed or unresolved:** the new feature did not reduce the 13 misses in the old source sample. Separate v2 source review found two candidates missed by its frozen detector. Both are development-exposed, not confirmed scientific errors.
- **No established false positives:** none against the old supplied annotations; human review of the v2 candidate set was not run. Neither result supports a precision estimate.
- **No scientific error established:** arithmetic candidates stay separate from source attribution, correction corroboration, scientific impact, and independent human adjudication.

## COMET-T correction analysis

The article and correction were re-retrieved through the approved Europe PMC route in the prior campaign, and their source hashes match the preserved evidence. The PDF handoff member was 356,554 bytes with SHA-256 `b74d637aef5b371fc7a442b03b86fe4ec90f697a34a716fd8e91364c612a8536`; that handoff claim does not independently authenticate publisher origin. No PDF parser ran.

The official correction changes `3 (3.19)` to `3 (3.29)` while the handoff table shows `n=94`. `3/94` rounds to `3.19%`. Five displayed category counts sum to 88, so exhaustive accounting cannot be assumed. The article permits adjusted percentage frequencies when necessary but provides no cell-specific rule. An alternate denominator, weighting, truncation, or adjustment remains unsupported; the original pre-correction supplement was not authenticated. A bounded title search found only the article and correction and did not recover an archived original. The prepared clarification request remains **unsent**. This is an unresolved arithmetic discrepancy, not an established scientific error.

## End-to-end workflow and provenance

`python -m tools.research_audit audit` generated schema-valid JSON and Markdown from a permitted local JATS source with exact byte/hash checks. The output preserved table relationships, anchors, computations and abstentions; it did not claim the hash authenticated source origin. Full article bytes, detailed annotations, per-document records, and candidate registry remain in the owner-review evidence package and are excluded from Git.

The old v1 sample’s required JATS OS isolation was not established, and its five declaration refusals were not bypassed. The v2 experiment used a bounded offline Python parser, not an OS network/filesystem sandbox. These facts are not retroactively repaired by this code change.

## Security, tests, and release status

- Real PDF extraction remains **BLOCKED**. Access to `/var/run/docker.sock` returned `operation not permitted`; required reviewed Poppler image provenance is unavailable. No PDF was run in Docker or directly on the host.
- Manual review of the patch found no credentials, custody records, reserved identities, licensed full text, or detailed candidate labels. The repository release-file selector was unchanged; checksums were regenerated using that selector. Ignored Python/pytest caches and build metadata were excluded; no other untracked files were present in selected release directories.
- Focused JATS and integrated audit tests passed: 80 total. Full `python -m tools.quality_gate` passed in the isolated `/tmp/rw-campaign-venv` on Python 3.12.14 with pytest 9.1.1: 457 tests, 87 subtests, 500/500 synthetic cases, 3/3 existing historical replays, source checksums, schema/frozen-screen checks, trusted-core scan, reproducible wheel, install smoke, and CLI checks. Wheel SHA-256: `73796d50071caa47c8abf3c7d36085ba451507fc39241e0aeace8d1f186320b5`. Contract validation and `git diff --check` passed. No dependency was added to the project.
- Exact code commit `bd13eacf379f77a52133e9059b4d9a7a42a0a895` passed hosted [CI run 38727434145](https://github.com/Smkzz/ResearchWitness/actions/runs/38727434145): Release gate and Python 3.11–3.13 jobs succeeded. [CodeQL run 38727434167](https://github.com/Smkzz/ResearchWitness/actions/runs/38727434167) also succeeded. CodeQL is automated analysis. The independent review was model-generated, not human scientific adjudication or a formal Codex Security scan; the Codex Security scan workflow capability was unavailable.
- The PR remains draft. No merge, release, contact, custody access, reserved-paper run, or Wave 3 occurred.

## Qualification answers

1. **Real relationship coverage improved?** Yes between the historical detector and active PR (239 to 423 surfaced on the old supplied annotations). The reviewed fixes preserve 423 surfaced relationships. The separate frozen v2 run surfaced 590; it is descriptive and not a complete gold set.
2. **Known denominator errors corrected?** Yes: six historically, zero in active and improved replays; regression cases cover grouped zero-count denominators.
3. **Previously missed discrepancies found?** Current PR candidates match three old supplied reference relationships versus zero historically, all unresolved. The separate v2 partial census found two missed arithmetic candidates, but the reviewed implementation was not run on that sample and neither candidate is independently confirmed.
4. **Improvements introduce false positives?** None against old supplied annotations. Review removed 12 false conditional mismatches; human adjudication of v2 candidates was not run, so general false-positive performance is unknown.
5. **Evidence source-traceable?** All 423 old-sample anchors validate, and the reviewed conditional group links now require article/table role, label, and sample-size agreement. Source hashes establish byte continuity, not publisher origin, license, or reviewer independence.
6. **Improvement demonstrated on real development documents?** The reviewed fix was replayed on the old exposed sample and removed unsupported group-linked calculations without changing surfaced relationships. It was not run on the frozen v2 sample; no independent generalization claim is made.
7. **New preregistered evaluation completed?** The separate v2 development experiment completed its preregistered descriptive run. Protected independent evaluation did not run.
8. **Minimum sample met?** v2 development minima were met; old v1 remained below its minimum of ten analyzable documents. Protected v1.3 requirements remain unmet.
9. **Independent work-family overlap controlled?** Screened conservatively, but not proven; unnamed shared datasets can remain undetected.
10. **Independent precision/recall justified?** No.
11. **PDF sandbox qualified by real execution?** No; Docker access and image provenance block it.
12. **Untrusted inputs processed within the PDF trust boundary?** No PDF was processed. JATS declaration refusals remained in place.
13. **Source/provenance assumptions verified?** Partially. Recorded public retrieval and hashes exist; source-origin authentication, some license links, work-family independence, and COMET-T’s calculation remain limited.
14. **Tests and release gates pass?** Yes for reviewed code commit `bd13eac`: the full local gate plus hosted release qualification, Python 3.11–3.13 matrix, and CodeQL all pass. A later report-only commit may advance the PR head.
15. **Code committed on GitHub?** Yes, on draft PR #13. No merge or release occurred.
16. **Independently scientifically qualified?** No. The protected custodian acceptance criteria remain unchanged and unmet; no protected evidence was accessed or evaluated.

## Next highest-value work

1. Obtain independent human review of the development candidate registry, including the two partial-census candidates and the rounding-balancing alternatives, without describing them as untouched holdouts.
2. Preserve the separate v2 frozen outputs; any test of a changed detector needs a new preregistered sample.
3. Obtain authorized Docker isolation and reviewed Poppler image provenance before real PDF execution.
4. Continue v1.3 qualification only through the independent custodian. Resolve COMET-T using authenticated source/version evidence or an owner-approved reply; do not infer the denominator or send the request without authorization.

The machine-readable continuation state is [`validation/RESEARCHWITNESS_NEXT_CAMPAIGN_CHECKPOINT.json`](validation/RESEARCHWITNESS_NEXT_CAMPAIGN_CHECKPOINT.json).
