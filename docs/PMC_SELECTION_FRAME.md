# RW-01O2: a separately pinned private selection frame for the PMC pilot

**Status:** engineering safeguard for the source-exposed development cohort.
This is not an independently time-stamped preregistration, authenticated
publisher retrieval, publisher-permitted reuse, independently adjudicated
science or a protected/sealed evaluation. No network operation is performed.

## The scientific accounting problem solved

The RW-01O1 private attempt ledger records and replays all rows **that it
contains**, but its hash does not prove those were all cases originally
selected. For example, someone could remove a difficult third paper,
recalculate the ledger digest and still get a valid two-paper report.

RW-01O2 therefore introduces a **separately committed, outcome-free list of
source identities**. The later complete attempt ledger must match that list
*exactly* before any source chain is processed. Every selected item must be
present, including `not_attempted`, failed acquisitions, licence exclusions,
replayed parser refusals and still-unreviewed source captures.

The full selection frame remains **private**. A checksum can establish
continuity with a separately saved frame; it cannot establish that the frame
was created before viewing study outcomes. A genuinely independent
pre-outcome timestamp and custodian are separate, still-unqualified gates.

## Selection frame v1

Exactly these top-level keys are allowed:

```json
{
  "schema_version": "rw-private-pmc-selection-frame.v1",
  "partition": "development_exposed",
  "selection": "operator_declared_not_time_authenticated",
  "records": [
    {
      "record_id": "demo-original",
      "family_id": "demo-family-a",
      "version_id": "v1",
      "oai_identifier": "oai:pubmedcentral.nih.gov:12345",
      "kind": "article",
      "parent_record_id": null
    },
    {
      "record_id": "demo-second",
      "family_id": "demo-family-b",
      "version_id": "v1",
      "oai_identifier": "oai:pubmedcentral.nih.gov:67890",
      "kind": "article",
      "parent_record_id": null
    }
  ]
}
```

These numeric OAI identifiers are *invented example identities*, not real
article assertions. The frame declares 2–12 selected source/version
records from 2–5 independent *declared* work families. It contains
**no results, labels, licence approvals, actual transfers or timestamps**.

A record identifies the exact article to attempt via official PMC
`GetRecord` with `metadataPrefix=pmc`, its declared work family/version
and whether it is an initial article, correction, supplement or revision.
Corrections and supplements must name a selected parent of the same family.
Revisions reuse their parent's OAI identity; records with the same OAI
identity cannot be counted as distinct independent families. Cyclic
parent relationships, repeated records or family/version combinations,
incomplete family counts and cross-family identifier reuse are refused.

## Required private v2 replay procedure

1. **Before attempting selected articles**, write the private selection
   frame into an already-authorized private work area and retain its
   canonical sorted-key ASCII/JSON + LF SHA-256 independently. For genuine
   scientific preregistration, an actually independent custodian must
   additionally preserve the protocol, scope and timestamp. A self-declared
   local hash is *not* that authority.
2. Build a private RW-01O1 attempt ledger with **exactly one row per frame
   record**, preserving the same record/family/version keys. Use outcome
   `not_attempted` with `reason=null`, `files=null`, `pins=null`
   before work begins. Never fabricate a provider failure as a placeholder.
3. When an article is legally acquired through an **already approved**
   official PMC retrieval environment, record its actual transfer/time,
   article-specific rights and private raw bytes, and complete RW-01M/N/K/J/L
   evidence. The attempted `transfer.requested_identifier` must exactly
   match its selected `oai_identifier`. For accepted captures,
   `metadata.kind` and `metadata.parent_record_id` must match the
   selection frame, in addition to the existing source/version constraints.
   Parser-refused cases must likewise bind the originally requested OAI ID.
4. Supply **both** separately saved canonical SHA-256 values to the
   dedicated framed CLI; retain output only under appropriate private
   storage controls.

```text
python -m tools.pmc_pilot_selection_frame \
  --frame PRIVATE_SELECTION_FRAME.json \
  --expected-frame-sha256 PREVIOUSLY_STORED_FRAME_DIGEST \
  --ledger PRIVATE_PILOT_LEDGER.json \
  --private-root PRIVATE_SOURCE_DIRECTORY \
  --expected-ledger-sha256 PREVIOUSLY_STORED_LEDGER_DIGEST
```

A full report includes original bounded RW-01O1 chain replay/attempt
counts plus `selection_frame_sha256`,
`selection_frame_coverage=all_selected_record_ids_accounted`,
`selected_attempts_not_yet_run`,
`selected_attempts_with_declared_outcomes` and
`source_identifiers_and_lineage_match_frame=true`. It explicitly returns
`pre_outcome_frame_timing_authenticated=false`,
`independent_scientific_labels_established=false` and
`scientific_detection_improvement_established=false`.

The **legacy** `python -m tools.pmc_pilot_ledger` remains available
only for *unframed* source-accounting development diagnostics. Its older
v1 result cannot claim population completeness. Use the new framed CLI
for future RW-01O development-pilot reporting.

## Precise protection and remaining gaps

- This protects **against omissions and source substitutions relative to
  the provided separately pinned frame**, not against a dishonest original
  frame, re-pinning after outcomes, publication bias, dataset overlap or
  altered official retrieval logs.
- Work families remain researcher/operator declarations. Byte hashes,
  matching OAI identifiers and a valid parent graph do not authenticate
  article rights, versions, publisher identity or scientific independence.
- A `not_attempted` row contributes to the selected denominator; it is
  neither a successful acquisition nor an observed failure.
- The frame and its identifiers remain private. Only sanitized counts
  and digest continuity are emitted; even a frame digest is not proof of
  independence or chronological preregistration.
- Original complete HTTP response bodies, article-specific rights and real
  source-grounded independent reviewers remain **unavailable** in the
  current network-disabled tool environment. Do not use CI egress,
  a search snippet or an alternate tool to bypass that blocker.
- Protected evaluation still requires RW-03/RW-05 custody qualification
  and fresh, genuinely untouched materials; this feature does not open
  those gates.

All committed tests use **invented** XML and OAI identifiers. The tool
never acquires, modifies, publishes or contacts any paper or author.
