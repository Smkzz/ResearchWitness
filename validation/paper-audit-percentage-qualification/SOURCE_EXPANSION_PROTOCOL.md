# Development source expansion protocol

Status: frozen before retrieving or opening any newly searched article body.

This protocol expands only the source-first count/percentage negative corpus.
It does not search correction bodies, change the frozen graduation gates, or
inspect any reserved source body or detector output.

## Metadata query and deterministic order

Search Europe PMC's public search API with this exact query:

```text
OPEN_ACCESS:Y AND HAS_FT:Y AND FIRST_PDATE:[2016-01-01 TO 2025-12-31] AND (TITLE_ABS:trial OR TITLE_ABS:cohort OR TITLE_ABS:randomized OR TITLE_ABS:randomised)
```

Request core metadata only, beginning with the API's initial cursor and
`pageSize=64`. Preserve API cursor order. Keep the first 64 unique records with
both a stable DOI and PMCID; when a page has duplicates or incomplete records,
continue the same cursor until 64 qualifying metadata records are collected or
the result set is exhausted. Deduplicate by normalized DOI, keeping the first
PMCID returned. Divide the preserved ordered records into consecutive batches
of 32. Persist the exact query, retrieval timestamp, cursor sequence, result
count, and hash of the returned metadata before fetching any full-text source.

Apply the existing frozen DOI rule to every item in a batch before opening any
article body: normalize DOI by trimming whitespace, removing `https://doi.org/`
or `doi:`, and lowercasing; compute SHA-256 over UTF-8; first digest byte below
64 is `RESERVED`, otherwise `DEVELOPMENT`. Do not retrieve or inspect article
bodies, tables, corrections, or detector outputs for `RESERVED` records.
If a DOI already has a frozen assignment in an existing source ledger, retain
that assignment and do not allocate or move it again.

Process every `DEVELOPMENT` record in DOI order within each batch. Retrieve the
original Europe PMC JATS XML, verify the returned PMCID and DOI against the
metadata record, and pin the exact bytes with SHA-256. Do not choose a subset
based on table content, arithmetic, correction status, or detector output.
If either the DEVELOPMENT negative pool or the source-only RESERVED capacity
pool remains below its frozen 50-correct-relation / 15-document gate, process
the next complete metadata batch under the same rules. Stop only when both
capacity gates are met or the metadata result set is exhausted; do not alter
any eligibility rule to change the result. This addendum aligns the search
stop condition with frozen graduation criterion 10; it does not change the
threshold or any label rule. It was recorded before batch 1 source labels or
detector scores were joined, and before retrieval of any later-batch source.

## Reserved negative capacity exception

Before the first expanded metadata batch is retrieved, the separate
`RESERVED_NEGATIVE_CUSTODIAN_PROTOCOL.md` is frozen as a narrow exception to
the no-reserved-body rule above. A `RESERVED` document may be retrieved only
by the source-only custodian under that protocol, solely to estimate the
reserve pool's source-qualified negative capacity. The custodian must not
receive detector code or development outputs, and must return only the
aggregate counts and sealed record hash specified there. No reserved document
or relation may enter a development runner input, and no detector result may
be joined, scored, or reported for any reserved source. All other reserved
content remains unopened to the development work.

## Source-first review and detector join

For each DEVELOPMENT source, locate candidate count/denominator/percentage
relations from the pinned source independently of detector output. Record
source path, operands, reported precision, exact scope, footnotes, missingness,
weighting/adjustment, and exact-decimal arithmetic. Apply contract 1.2 and
separate contract eligibility from arithmetic correctness. Freeze the labels
and source manifest before running or joining the detector. A negative is
eligible only when it is both contract-eligible and independently arithmetically
correct.

Report relation, table, and document counts. Do not calculate paper-level
uncertainty by treating rows in the same paper as independent. Keep all
new-source evidence DEVELOPMENT-only and preserve the preexisting split.
