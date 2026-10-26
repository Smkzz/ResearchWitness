# RW-01 integration map

**Current slice baseline:** `b2d4863d28e037d35bd8052997e6b02318977771` (PR #20).  
**Legacy stack tip inspected:** PR #11, `6843593ff443d4a44c48d15a76949b323d0951ca`.  
**Common ancestor:** `65c814c02ec3e3b8f427ad095986a258470b8f80`.

The earlier comparison from plan head `32a8f20f0f64a0dd6c6e9c9cb8a0a4c4e3e12732`
reported 22 stack-side and 39 main-side commits. That is a dated divergence record,
not the current commit count or a complete reviewed inventory. No blanket merge,
legacy PR closure, force-push, historical corpus import or replacement of current
core/security/release files has occurred. RW-01 remains incomplete. Follow
[the plan](DEVELOPMENT_PLAN.md) and [execution state](EXECUTION_STATE.json).

## RW-01A: operand-only 2x2 arithmetic

`researchwitness/paper_statistics.py` reuses the standalone calculator from PR #11,
original blob `9ebcb2fd47f76b5c5100e0f2b4ba3e6cb6718da6`. It computes crude risk ratios,
odds ratios and differences in proportions from explicit unadjusted counts. It is
an installed Python helper, not a new trusted `checkers.KINDS` family or paper-audit
CLI. Four upstream scenario groups and malformed-input/context regressions remain
in `tests/test_paper_statistics_integration.py`. Fully specified Decimal contexts
and exact differential checks protect it from mutable ambient rounding settings.
See the preserved [first-slice receipt](IMPLEMENTATION_2026-10-24.md).

## RW-01B: canonical source evidence, without replacing the parser

`researchwitness/paper_document.py` is copied byte-for-byte from legacy blob
`4a000cb423de3d45811f64ed942b0d9425f373ef`. `tools/jats_source_adapter.py` uses its
immutable `SourceAnchor` and `NumericAssertion` contracts with the **current main**
JATS detector. The legacy parser normalizes XML before parsing; importing it as a
replacement would not preserve the current original-byte anchor semantics.
It is therefore not imported or enabled by this slice.

The bridge reconstructs element identity, complete normalized quotes and operand
bindings from captured original bytes; explicit element-span semantics prevent
confusion with literal quote offsets. Unknown scientific context remains null.
All existing scope/rounding abstentions and conditional calculations stay visible.
Separate exact integer arithmetic replay validates resolved numerical relationships,
not a source's authenticity or the paper's conclusion. Both component and relation
IDs bind the evidence appropriate to their roles. The existing detector is unchanged.

`tools.registered_jats_run` and `tools.jats_demo` provide actual checkout-only
source-to-report execution with registered denominators and recovery. See
[JATS_DEVELOPMENT_RUNNER.md](JATS_DEVELOPMENT_RUNNER.md) and the
[current implementation receipt](IMPLEMENTATION_2026-10-25.md).
This is not full `PaperDocument` table construction, migration of all legacy
source-mapped detectors, or completion of the installed product.

## Remaining integration, in order

| Component | Disposition |
|---|---|
| #5 ancestor and #6 foundation | Refresh effective changes; do not merge #5 twice or close it before proving no unique changes are lost. |
| Canonical model | Preserved unchanged; source-anchor/numeric-assertion bridge implemented. Rich table projection still pending. |
| Legacy JATS parser and denominator provenance | Not imported. Reconcile exact original-byte mappings, layouts and denominator semantics before adoption. |
| Flow, ratios, statistics source mapping | Not yet imported; retain their actual tests with their dependencies. |
| `paper_audit`, coverage, review/CLI/schema wiring | Pending; create one installed audit path, not conflicting public commands. |
| #12 local UI/custody and old `_pdf_worker` | Not imported or activated; safety gates unchanged. |
| Current core, intake/export, source selection, CI and agent policy | Retained, not overwritten by older stack versions. |
| Frozen studies and historical case records | Preserved in original records; no relabeling, protected reads or corpus replay. |
| #15/#16 dependency maintenance | Separate pending work, not resolved by these slices. |

The combined retained test populations and full PR-stack disposition remain
outstanding. Passing the bridge/runner tests does not complete RW-01 or establish
scientific discovery performance. Next work is richer source-model consolidation
and detector wiring, not repeating the same successful tests.

## RW-01C candidate — installed JATS review

The existing JATS detector is the single parser implementation in the wheel;
legacy checkout imports and direct invocation remain supported. JSON/HTML
review bundles and replay are separate from unmerged rich-table/flow components.
PR #22 holds the exact-source integration and test evidence; this is not a
blanket merge of #6–#12 and not independent scientific adjudication.
