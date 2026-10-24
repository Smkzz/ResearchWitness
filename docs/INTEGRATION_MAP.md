# RW-01 integration map - first bounded slice

**Observed baseline:** `32a8f20f0f64a0dd6c6e9c9cb8a0a4c4e3e12732` (plan adopted).  
**Stack tip inspected:** PR #11, `6843593ff443d4a44c48d15a76949b323d0951ca`.  
**Common ancestor:** `65c814c02ec3e3b8f427ad095986a258470b8f80`.

The GitHub comparison reports 22 stack-side commits and 39 main-side commits.
This is diverged history, not a fast-forward. Its large file response is not a
complete reviewed inventory. No blanket merge, PR closure, force-push, historical
corpus import or replacement of current core/security/release files was performed.
RW-01 remains incomplete. Follow [the plan](DEVELOPMENT_PLAN.md) and
[execution state](EXECUTION_STATE.json).

## Landed slice: operand-only 2x2 arithmetic

`researchwitness/paper_statistics.py` reuses the small standalone calculator from
PR #11. Original blob: `9ebcb2fd47f76b5c5100e0f2b4ba3e6cb6718da6`.
Original source: [pinned module](https://github.com/Smkzz/ResearchWitness/blob/6843593ff443d4a44c48d15a76949b323d0951ca/researchwitness/paper_statistics.py).

It computes crude risk ratios, odds ratios and differences in proportions from
four supplied nonnegative integer counts under explicit unadjusted context. It
returns arithmetic consistency, an arithmetic candidate or unsupported. It does
not parse a paper, authenticate a source, establish scientific applicability or
add a new trusted `checkers.KINDS` family. It is available as an installed Python
helper, not a new paper-audit CLI command. The existing ten checker families and
runtime proof/status contracts are unchanged.

The four existing upstream 2x2 scenarios are retained in
`tests/test_paper_statistics_integration.py`: RR/OR/difference, mismatch, adjustment/
zero-cell policy, and half-up/count bounds. Additional cases reject non-string
reported values, truthy non-boolean context flags and malformed counts. Rounding,
tolerance and difference formatting use a fully specified Decimal context, including
traps/exponent limits, so neither thread context nor mutable `DefaultContext` changes
results. A second agent identified the DefaultContext defect; the new regression
failed before repair and passed afterward. A fixed-seed differential test checks
300 bounded calculations against independent exact Fraction/integer rounding.

## Remaining integration, in order

| Component | Disposition |
|---|---|
| #5 ancestor and #6 foundation | Refresh effective changes; do not merge #5 as duplicate work or close it before no-unique-change evidence exists. |
| Canonical `paper_document` and JATS model/parser | Next RW-01 slice. Reconcile original-byte anchors and supported layouts with current `tools/jats_percentage_audit.py`. |
| Denominator provenance, flow, ratios, statistics source mapping | Not yet imported; retain their actual tests when their dependencies land. The 2x2 helper alone supplies no source mapping. |
| `paper_audit`, coverage, review/CLI/schema wiring | Not yet integrated; avoid retaining conflicting public audit entry points. |
| #12 local UI | Separate from custody activation; not imported. |
| #12 custody and old `_pdf_worker` | Not imported or activated. Existing safety gates still apply. |
| Main intake/export, source selection, CI and agent policy | Retained, not overwritten by older stack versions. |
| Historical case records and frozen studies | Preserved in their original branches/records; no relabeling, protected-data read or corpus replay. |
| #15/#16 dependency maintenance | Separate pending work; not implicitly resolved by this slice. |

The installed source-to-report workflow, combined original test populations and
full PR-stack disposition are still outstanding. Do not mark RW-01 done because
this isolated helper passes. The next slice should reconcile the two JATS/source
representations and preserve main's bounded file handling and denominator rules.
