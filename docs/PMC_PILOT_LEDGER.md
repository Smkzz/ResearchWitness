# RW-01O1: private PMC development-pilot intake and denominator ledger

**Status:** checkout-only, network-disabled, development-exposed engineering
preparation. No actual PMC transfer, licence determination, publisher identity,
original source version, source-independent scientific annotation or sealed
research experiment is supplied by this feature. [Issue #35](https://github.com/Smkzz/ResearchWitness/issues/35)
remains open until actual private, permission-cleared material exists.

The pilot should record **2–5 declared distinct work families** and at most
12 article/version attempts (to allow corrections and supplements within
families). Attempts that were not acquired, not legally eligible, not parsed
or not independently reviewed **must not disappear** from the original frame.

## Private inputs

Use an already-authorized original-byte PMC acquisition environment, outside
Git and CI. Respect PMC's official OAI-PMH limits and article-specific licences.
Do not use web snippets, GitHub runners, simulated HTTP statuses, XML
reserialization or hash-only declarations as proof of a genuine transfer.

Create a private UTF-8 JSON ledger object with exactly:

- `schema_version: rw-private-pmc-development-pilot.v1`
- `partition: development_exposed`
- `selection: operator_declared_not_time_authenticated`
- `records`: 2–12 complete article/version entries, representing 2–5
  **declared** families; version/correction records share their parent
  family and are never counted as independent trials.

Each entry has exactly `record_id`, `family_id`, `version_id`, `outcome`,
`reason`, `files`, `pins`. Identifiers are private, not included in the
printed report. Supported outcomes:

| Outcome | Evidence required |
|---|---|
| `acquisition_unavailable` | No files/pins; reason `provider_unavailable`, `not_found`, `transport_failed` or `timeout` |
| `rights_excluded` | No files/pins; reason `rights_unknown`, `rights_restricted` or `rights_not_redistributable` |
| `parser_refused` | Private original `raw_envelope` + declared `transfer` files, no pins; a supported *actual* parser refusal diagnostic as reason, exactly reproduced by the offline tool |
| `captured_pending_review` | Full RW-01M/N/K/J/L private evidence chain, three external digest pins; no reviewer records |
| `development_reviews_submitted` | Same complete replayable private chain **plus both** individually submitted developer-review documents; review declarations do not authenticate independence |

For a captured candidate, `files` has exactly these keys, each a basename
inside one already-private directory: `raw_envelope`, `transfer`,
`derived_source`, `derivation_envelope`, `metadata`,
`capture_envelope`, `packet_envelope`, `review_a`, `review_b`.
The last two are both `null` for pending reviews and both filenames for a
submitted review pair. `pins` requires `expected_derivation_sha256`,
`expected_capture_sha256`, `expected_packet_sha256`.

The tool strictly replays the full raw-provider-body-to-derived-JATS chain,
capture metadata, the source-fact packet and optional paired review
reconciliation; source bytes and declared record/family/version IDs must
match. Captured cases are also passed through RW-01K's version registry to
reject duplicate source bytes, incomplete declared parents, and version
lineage cycles. **Family-sharing across scientifically related but
byte-different studies still cannot be authenticated.** Only safe single
filenames are accepted, preventing path traversal and cross-record file
reuse; files are read through the existing bounded regular-file reader.
This is input hardening, not a new OS or network isolation sandbox.

### Execute offline

From a private working directory already protected by your operator rules,
save the JSON and independently pin the canonical SHA-256 (the same
sorted-key, ASCII, no-space, LF-terminated format as
`tools.verification_benchmark.commitment`) **outside the ledger file**.

```text
python -m tools.pmc_pilot_ledger \
  --ledger PRIVATE_PILOT_LEDGER.json \
  --private-root PRIVATE_SOURCE_DIRECTORY \
  --expected-ledger-sha256 EXTERNALLY_SAVED_CANONICAL_LEDGER_HASH
```

The command returns **only aggregate counts**: number of attempted
article/versions, declared families, source chains actually replayed,
relation-count totals, outcome counts, refusal reason counts, unresolved
source-review counts, and commitments to the complete ledger and
captured-family registry. It emits neither source text nor record IDs or
review rationale. All authority flags stay false.

If a file is changed, a pin is stale, source rights/capture declarations
disagree, a reviewer is missing, a correction parent is absent or a
`parser_refused` record actually parses, the command refuses the
input rather than silently producing a misleading success report.
No zero-denominator calculation, independent label or overall research
accuracy can be derived from the report.

## Scientific path after the pilot becomes possible

1. Confirm real acquisition authority, actual provider response body and
   contemporaneous operator-side transport records. Distinguish origin
   authenticity and local byte-preserving replay; the latter does not prove
   the former.
2. Verify article-specific rights, corrections, supplement links and shared
   datasets independently. A CC-looking URL is *not* a legal adjudication.
3. Obtain two genuinely separate substantive source-context reviews with
   appropriate source access/permission, preserve disagreement, scope
   ambiguities and unresolved work; never interpret model personas as an
   independent gold standard.
4. Establish a private development-only source-supported label set and
   compare a frozen deterministic baseline with RW-04C/E metrics. Any
   historical/exposed example remains exposed; sealed RW-05/RW-11 requires
   its own qualified isolated custodian and pre-outcome study freeze.
5. Preserve the pilot's unsuccessful source attempts in all reported
   acquisition and error-denominator counts. Report the scientific
   outcome as **unverified** until source-label and independence gates pass.

Tests under `tests/test_pmc_pilot_ledger.py` use entirely fabricated
OAI-PMH/JATS envelopes; their passing cannot be counted as real-paper
scientific evidence. No external contact, chargeable API or automatic
publication is performed by this tool.
