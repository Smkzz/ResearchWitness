# Offline development research audit

This source-checkout workflow finds bounded count/percentage relationships,
checks explicit arithmetic and exports evidence for researcher review. It is
outside the trusted verifier core and is not a paper-error classifier. Install
the project's optional development dependencies in an isolated environment.

```bash
python -m tools.research_audit audit /permitted/article.xml \
  --document-id local-example --format jats \
  --expected-sha256 <verified-source-hash> \
  --source-url https://www.ebi.ac.uk/europepmc/webservices/rest/PMC000000/fullTextXML \
  --provenance-status recorded_public_retrieval \
  --json-output /output/audit.json --markdown-output /output/audit.md
```

Use an actual identifier and verified hash. A URL/provenance status is an
operator assertion; a hash verifies supplied bytes and does not authenticate
publisher origin. An owner handoff requires an expected hash. Local documents
can instead use the default `unverified_local` provenance. No network request
occurs during an audit. Inputs must be regular files; existing reports with
different content are not overwritten. A completed audit exits 0; unsupported
or failed extraction exits 2 with a structured report when possible.

JATS inputs are limited to 8 MiB, 100,000 XML nodes, depth 256, 512 tables,
20,000 rows, 100,000 cells/layout slots, 256 columns and 1,000 relationships.
DTD/entity declarations and non-article roots are refused. The pure-Python
parser is bounded input validation, not an OS network/filesystem sandbox.
Do not feed it protected custody or reserved evaluation sources.

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

JSON conforms to `schemas/research-audit.v1.schema.json`. Every automatic
finding is `unreviewed`, with scientific error `not_established`. States separate
extracted evidence, arithmetic match and arithmetic mismatch candidate. Human
reviewed findings and independently corroborated errors require a separate
review record; this command cannot promote them. Markdown includes source and
extraction hashes, source anchors, operands, expected/reported values, scope,
abstention reasons and further evidence required. XML anchors identify original
source elements; normalized character spans disambiguate cell components.

For PDFs use `--format pdf` only after the independent runtime gate in
[`PDF_SANDBOX_QUALIFICATION.md`](PDF_SANDBOX_QUALIFICATION.md) passes. The command
uses the existing strict container runner, never host Poppler. Real PDF
qualification is currently blocked; synthetic/mock tests do not lift that gate.

## Offline comparison of supplied runs

```bash
python -m tools.research_audit compare \
  --annotations /evidence/percentage-annotations.json \
  --run /evidence/run-historical.json --run /evidence/run-revised.json \
  --json-output /output/comparison.json --markdown-output /output/comparison.md \
  --require-no-regression
```

The local annotation and run schemas are
`percentage-annotations.v1.schema.json`, `percentage-annotations.v2.schema.json`
and `percentage-run.v1.schema.json`. The comparison still reads v1. V2 records
independent count and percentage anchors, component spans, table/row/cell
identity, work-family identity, source version and retrieval metadata,
population scope, denominator basis, alternative interpretations, and reviewer
authority/status. Related correction sources carry their own hashes and exact
anchors; a `correction_corroborated` label is rejected without a registered
correction source and matching evidence span. Hashes commit to supplied bytes;
they do not authenticate a source's origin or a reviewer's independence.
Sources/reports are confined relative to their manifests. Source versions,
report hashes, exact XML anchors, count/percent tokens, explicit denominator
evidence and arithmetic are validated. Duplicate identifiers/source facts,
special files, contradictory annotations and inconsistent integrated-audit
identity/status are rejected.
Legacy raw aid reports are supported with externally supplied detector hashes;
those hashes are commitments, not proof that a particular executable produced
the report. The harness never runs arbitrary historical code.

Comparison JSON conforms to `research-benchmark.v1.schema.json`. It reports
every supplied reference relationship, unannotated output, extraction coverage,
arithmetic outcomes, denominator disagreements, span errors, abstention reasons
and error taxonomy. A mismatch earns reference-discrepancy credit only with a
valid source span and the matching resolved reference denominator. Unknown or
derived reference scope is not credited as a detected discrepancy.

The optional development gate exits 3 for lost annotated coverage, new wrong
denominators/span failures/false candidates, or a lost source-bound discrepancy
candidate. A deliberate safety abstention can fail this gate and must be
explained explicitly; it is not grounds to remove the gate or weaken scientific
acceptance. The gate does not establish precision, recall, source authenticity,
independent scientific error or frozen v1.3 qualification.

The reproducible owner evidence package holds permitted development sources,
all frozen versions, manifests, provisional source-linked annotations and
relationship-level outputs. Full-text research collections stay outside Git.
The old failed sample is unchanged; any new prospectively selected development
sample has a separate protocol and detector freeze.
