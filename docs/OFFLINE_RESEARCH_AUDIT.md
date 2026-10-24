# Offline development research audit

This source-checkout workflow checks bounded count/percentage relationships and
exports source-linked candidates. It is outside the deterministic core, not a
paper-error classifier. [AGENTS.md](../AGENTS.md) governs development; RW-01/RW-02
in [the plan](DEVELOPMENT_PLAN.md) will consolidate the installed audit workflow.
That future integration is not claimed to exist here.

## Setup and synthetic example

From the repository root in an activated isolated environment:

```text
python -m pip install -e '.[dev]'
python -m tools.research_audit audit examples/synthetic-jats/article.xml --document-id synthetic-jats --format jats --json-output out/synthetic-jats/audit.json --markdown-output out/synthetic-jats/audit.md
```

The optional requirements include `jsonschema`; core-only installation is insufficient
for these source tools. The single-line command works in Bash/PowerShell and needs
no network after setup. Expect two tables, three relationships, one arithmetic
match, one mismatch candidate and one abstention. This is an invented fixture:
`4/50` is `8.00%`, one row prints `8.10%`, and a second table lacks a denominator.

JSON/Markdown uses deterministic LF. Repeating identical inputs/code/output paths
is idempotent; different reports are not overwritten. Use fresh paths after changes.
Every automatic result remains unreviewed, error not established and source origin
unauthenticated. An agent may inspect it without waiting for a human opinion.

## Local inputs and provenance

Replace the fixture with permitted local bytes. `--expected-sha256` checks those
bytes. `--source-url` and `--provenance-status recorded_public_retrieval` require
an actual recorded retrieval; the tool does not fetch/authenticate that URL.
`owner_hash_verified_handoff` needs an expected hash. Default local provenance is
`unverified_local`. Do not upgrade these assertions to make a finding look stronger.

Auditing makes no network request. Inputs must be regular single-link files and
output paths cannot conflict. Completed processing exits 0 even without mismatches
or with abstentions. Unsupported/failed extraction exits 2, with a structured report
where possible; missing inputs may fail before output. Inspect findings/reasons,
not only exit codes.

JATS limits are 8 MiB, 100,000 XML nodes, depth 256, 512 tables, 20,000 rows,
100,000 cells/layout slots, 256 columns and 1,000 relationships. DTD/entity declarations
and non-article roots are refused. Bounded parsing is not OS network/filesystem
isolation. Do not feed developer aids protected custody/reserved evaluation sources.

## Supported relationships and abstentions

The aid supports paired count/percent, explicit `n/N (%)`, explicitly headed `n`,
`No.`, `Frequency`, qualified `N (count)` and percent columns, and valid comma-grouped
integers. Bare uppercase `N` is not a numerator. A single full-width total row may
supply a denominator only with an explicit total-population percentage heading.
Ambiguous/repeated/subgroup totals abstain.

Complete hierarchical headers and nonnumeric label spans are supported, with inherited
row-label evidence; malformed layouts and numeric spans abstain. Explicit row-group
population changes retain conflicts. Bounded labeled multi-percent cells carry
component character spans inside byte-anchored XML cells. Adjustment scope is accepted
only for supported exhaustive statements; unmapped notes stay conservative.

Exact arithmetic uses the unchanged v1.3 half-up display rule. Alternative stated
rounding rules abstain. Missingness/scope may yield explicitly conditional calculations
with the asserted denominator withheld; complete-case populations are never silently
inferred. Article-text group sizes require exact non-negated, non-generic label matches
and anchored article/table context; a specific unmatched header cannot inherit an
unrelated caption group. Attrition/analysis-set uncertainty remains abstention.
The comparison validates evidence roles, locations and sample-size agreement.

JSON follows `research-audit.v1.schema.json`; automatic finding states distinguish
extracted evidence, match and mismatch candidate, always `unreviewed` with scientific
error `not_established`. A separate review record must state its actual modality;
AI work must not be recorded as human review. This command does not promote a finding
or resolve scientific applicability. Markdown includes hashes, anchors, operands,
expected/reported values, scope, abstentions and further evidence needed.

PDF `--format pdf` is permitted only after [real qualification](PDF_SANDBOX_QUALIFICATION.md).
The runner never uses host Poppler. Mock/synthetic tests do not qualify that boundary.

## Offline comparison of supplied runs

This template requires permitted local annotations/run manifests, not a bundled
scientific dataset:

```text
python -m tools.research_audit compare --annotations path/to/percentage-annotations.json --run path/to/run-historical.json --run path/to/run-revised.json --json-output out/comparison.json --markdown-output out/comparison.md --require-no-regression
```

The harness accepts v1/v2 percentage annotations and v1 run manifests. V2 includes
count/percentage anchors/component spans, table/row/cell/work-family identities,
source version/retrieval, population/denominator scope, alternatives and reviewer
fields. Correction sources require their own hashes/anchors; `correction_corroborated`
needs a registered matching correction source. Hashes do not prove source origin or
reviewer independence. Preserve current schema meaning when recording AI review.

Sources/reports stay relative to their manifests. The harness validates versions,
report hashes, exact XML anchors/tokens, denominator evidence and arithmetic. Duplicate
identities/facts, special files, contradictory annotations and inconsistent report
identity/status are rejected. Supplied historical detector hashes are commitments,
not proof that the named program generated a report. No arbitrary old code runs.

Comparison output follows `research-benchmark.v1.schema.json`. It accounts for supplied
reference relationships, unannotated outputs, coverage, arithmetic, denominator/span
errors, abstentions and taxonomy. Discrepancy credit requires valid source spans and
matching resolved reference denominators; unknown/derived scope gets no such credit.
The optional development gate exits 3 for regressions. Explain intentional safety
abstentions rather than changing labels or disabling checks to pass.

This comparison does not establish precision/recall, source authenticity, independent
scientific error or sealed qualification. The new [benchmark specification](BENCHMARK_PROTOCOL.md)
adds separate measurement/custody requirements; it is not yet a completed benchmark.
Keep permitted detailed sources/annotations outside Git. Old failed studies remain
failed; a new experiment has a new protocol and detector freeze.

`tools/percentage_math.py` also checks numerator feasibility, compatible-denominator
ranges and component-rounding sums. These do not prove counts are unweighted,
exhaustive, disjoint or from one population. See [current status](PROJECT_STATUS.md).
