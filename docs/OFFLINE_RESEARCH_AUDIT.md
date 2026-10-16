# Offline development research audit

This source-checkout workflow finds bounded count/percentage relationships,
checks explicit arithmetic and exports evidence for researcher review. It is
outside the trusted verifier core and is not a paper-error classifier.

## Setup and synthetic example

From the repository root, in an activated isolated virtual environment:

```text
python -m pip install -e '.[dev]'
python -m tools.research_audit audit examples/synthetic-jats/article.xml --document-id synthetic-jats --format jats --json-output out/synthetic-jats/audit.json --markdown-output out/synthetic-jats/audit.md
```

The optional development dependencies include `jsonschema`; a core-only
`python -m pip install .` does not install the source tools' requirements.
The single-line command works in Bash and PowerShell and needs no network
request after installation. Expected output: two tables, three relationships,
one arithmetic match, one mismatch candidate and one abstention. The fixture
is invented, not research data. `4/50` gives `8.00%`; one row deliberately prints
`8.10%`, while the second table supplies no explicit denominator.

JSON and Markdown outputs are created with deterministic LF newlines. Reusing
identical input and detector bytes with the same output paths is idempotent;
different existing reports are not overwritten. Use fresh outputs after changes.
Every result remains unreviewed, with scientific error not established and
source origin unauthenticated.

## Local research input and provenance

Replace the synthetic path and document ID with your own permitted source.
`--expected-sha256` verifies the supplied source bytes. Use `--source-url` and
`--provenance-status recorded_public_retrieval` only when you have a recorded
retrieval; the tool does not fetch or authenticate that URL. A
`owner_hash_verified_handoff` requires an expected hash. The default for local
input is `unverified_local`.

No network request occurs during an audit. Inputs must be regular single-link
files; conflicting output paths are rejected. A completed audit exits 0,
including when no mismatch is found or some relationships abstain. Failed or
unsupported extraction exits 2 with a structured report when possible; missing
input can fail before output creation. Inspect processing, findings and reasons,
not only the exit code.

JATS inputs are limited to 8 MiB, 100,000 XML nodes, depth 256, 512 tables,
20,000 rows, 100,000 cells/layout slots, 256 columns and 1,000 relationships.
DTD/entity declarations and non-article roots are refused. The bounded Python
parser is input validation, not an OS network/filesystem sandbox. Do not feed
it protected custody or reserved evaluation sources.

## What is evaluated

- Paired count/percent cells, explicit `n/N (%)`, and explicitly headed `n`,
  `No.`, `Frequency`, qualified `N (count)` and percent columns, with valid
  comma-grouped integers. A bare uppercase `N` is never treated as a numerator.
- A single full-width `Total N (100%)` row can supply a denominator only when
  the table heading explicitly says percentages are of the total population.
  Ambiguous, repeated, subgroup or unscoped totals remain abstentions.
- Complete hierarchical header grids and nonnumeric body labels with spans.
  Inherited row-label evidence survives rowspans. Numeric data spans and
  malformed layouts abstain.
- Explicit row-group population changes, with conflicts against column/row
  populations or an explicit table percentage basis preserved as abstentions.
- Bounded, fully parsed labeled multiple percentages in a cell, each with its
  own normalized-character span inside the original byte-anchored XML cell.
- Table-specific adjustment scope only for an exhaustive supported statement;
  mixed or unmapped document notes remain conservative abstentions.

Computations use the unchanged v1.3 half-up display rule and exact rational
operands. A stated alternative rounding rule remains an abstention. Missing
data can invalidate denominator inheritance: the report may show an explicitly
conditional calculation, while withholding the asserted denominator and final
arithmetic decision. It never derives complete-case populations silently.
Subgroup versus total population conventions can similarly remain unresolved.
When a table caption or a matching column header names a group that has one
explicit article-text `group (n=...)` declaration, the report may show a second
conditional calculation with exact anchors to both the group-size paragraph
and table context. Caption fallback is allowed only for generic statistic
headers; a specific unmatched header blocks it. Group labels must match as a
complete phrase, so negated or generic labels do not supply context. This is
not an asserted table denominator: attrition, missingness, or a follow-up
analysis set can change the applicable population, so the automatic status
remains an abstention until the link is independently resolved. The offline
benchmark checks the evidence roles, article/table locations, group text, and
the declared sample size before counting a conditional mismatch.

JSON conforms to `schemas/research-audit.v1.schema.json`. Every automatic
finding is `unreviewed`, with scientific error `not_established`. States separate
extracted evidence, arithmetic match and arithmetic mismatch candidate. Human
reviewed findings and independently corroborated errors require a separate
review record; this command cannot promote them. Markdown includes source and
extraction hashes, source anchors, operands, expected/reported values, scope,
abstention reasons and further evidence required. XML anchors identify original
source elements; normalized character spans disambiguate cell components.

For PDFs use `--format pdf` only after the independent runtime gate in
[PDF_SANDBOX_QUALIFICATION.md](PDF_SANDBOX_QUALIFICATION.md) passes. The command
uses the existing strict container runner, never host Poppler. Real PDF
qualification remains blocked; synthetic/mock tests do not lift that gate.

## Offline comparison of supplied runs

This is a template requiring your own permitted local annotations and run
manifests, not a bundled scientific dataset:

```text
python -m tools.research_audit compare --annotations path/to/percentage-annotations.json --run path/to/run-historical.json --run path/to/run-revised.json --json-output out/comparison.json --markdown-output out/comparison.md --require-no-regression
```

The local annotation and run schemas are
`percentage-annotations.v1.schema.json`, `percentage-annotations.v2.schema.json`
and `percentage-run.v1.schema.json`. The comparison accepts v1 and v2 annotations.
V2 records separate count/percentage anchors, component spans, table/row/cell
identity, work-family identity, source version and retrieval metadata,
population scope, denominator basis, alternatives and reviewer authority/status.
Related correction sources carry their own hashes and exact anchors;
`correction_corroborated` is rejected without a registered correction source and
matching evidence span. Hashes commit to supplied bytes; they do not authenticate
a source's origin or a reviewer's independence.

Sources/reports are confined relative to their manifests. Source versions,
report hashes, exact XML anchors, count/percent tokens, explicit denominator
evidence and arithmetic are validated. Duplicate identifiers/source facts,
special files, contradictory annotations and inconsistent integrated-audit
identity/status are rejected. Legacy raw reports use supplied detector hashes;
those are commitments, not proof that a particular executable produced a report.
The harness never runs arbitrary historical code.

Comparison JSON conforms to `research-benchmark.v1.schema.json`. It reports
every supplied reference relationship, unannotated output, extraction coverage,
arithmetic outcomes, denominator disagreements, span errors, abstention reasons
and taxonomy. A mismatch earns reference-discrepancy credit only with a valid
source span and matching resolved reference denominator. Unknown or derived
reference scope does not receive detected-discrepancy credit.

The optional development gate exits 3 for lost annotated coverage, new wrong
denominators/span failures/false candidates, or a lost source-bound discrepancy
candidate. An intentional safety abstention may fail this gate and must be
explained, not hidden by changing labels or disabling checks. This does not
establish precision, recall, source authenticity, independent scientific error
or frozen v1.3 qualification.

The owner evidence package holds permitted development sources, frozen versions,
annotations and detailed reports outside Git. Old failed experiments stay failed;
new prospective evaluation needs a separate protocol and detector freeze.

`tools/percentage_math.py` additionally checks integer-numerator feasibility at a
fixed denominator/precision, compatible-denominator ranges for a supplied count,
and independent component-rounding sums. These are arithmetic checks, not proof
that counts are unweighted, exhaustive, disjoint or in the same population.

See [project status](PROJECT_STATUS.md) for the integration and research boundaries.
