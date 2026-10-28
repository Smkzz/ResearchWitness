# RW-01Q1 — exact-byte historical Europe PMC development-source recovery

**Software purpose:** recover or identify genuine byte-identical source JATS
for the previously *exposed*, non-blinded October 5, 2026 research
development sample. This is a source-recovery operation, not a new benchmark,
academic result, authorised independent custodian, legal opinion or sealed
source set.

## Auditable historical index

[`wave1-source-index.json`](../examples/historical-source-recovery/wave1-source-index.json)
contains **nine original JATS articles and four correction records**,
with original Europe PMC URL, exact byte count, SHA-256, source PMCID,
correction linkage and declared licence from historical
[unmerged October 2026 PR #11](https://github.com/Smkzz/ResearchWitness/pull/11).

- The **original Oct 5 manifest** is pinned at historical Git commit
  `6843593ff443d4a44c48d15a76949b323d0951ca`, file
  `validation/paper-audit-wave-1/cases.json`, raw SHA-256
  `f626061019cafddb25164abe647fa127f3843ef8f1187bbbbf94398a8c19134d`.
- The independent raw-byte SHA-256 of the newly committed **source index**
  is `d0a3ee22f15868f9c97b4cdf8faa866211f753f562a33370b610a67549958f95`.
- The index contains only **source metadata**; none of the original full-text
  XML, private PDF sources, adjudication notes, author allegations or
  newly available research labels were published.
- The 13 records are **historically exposed source identities**, not a
  preselected untouched corpus. The original manifests were publicly
  visible to developers. Some old licence claims (notably one correction)
  were ambiguous, and *all* original rights declarations need
  independent article-specific verification before real reuse.

## Default: audit authorized *private* existing source bytes, no network

Choose an existing private directory **outside** the checkout and CI source
tree, with permission to hold the licensed original XML. Create and
secure the directory in the operator's existing approved workspace if
necessary; this utility itself does **not** create one.

```text
python -m tools.recover_legacy_europepmc_sources \
  --index examples/historical-source-recovery/wave1-source-index.json \
  --expected-index-sha256 d0a3ee22f15868f9c97b4cdf8faa866211f753f562a33370b610a67549958f95 \
  --private-root PRIVATE_SOURCE_DIRECTORY
```

This reads only 13 expected filenames `PMC*.xml` and returns sanitized
per-record states and aggregate counts. Local body bytes are checked
against **both** the exact historical byte length and SHA-256 via
the existing bounded regular-file reader. Unsafe/symlink input refuses.
If any selected file is absent or has changed, the CLI exits **1**.
Invalid or stale index pins exit **2**. When all selected source files
exactly match, exit **0**. It emits no original source text and makes
zero network calls or filesystem writes in default audit mode.

A matching old SHA proves **historical byte continuity only**. It does
not independently prove who served the source in 2026, that every paper
was correctly attributed, that its copyright licence is valid for this
study, or that any correction represents a scientifically important error.

## Explicit, strictly bounded *conditional* network recovery

Only when an **already authorized** process has network egress to the
official Europe PMC service and the operator has independently validated
each article's usage rights, add:

```text
  --allow-authorized-network --only-pmcid PMC4339301 --max-network-requests 1
```

The **flag is not permission** and does not change local sandbox policy,
network filtering or private-source custody. It is ineffective in the
network-disabled LocalControl AppContainer: do not deploy a runner,
proxy, CI, tunnel or alternate egress route to defeat the guard.

The downloader has a fixed `https://www.ebi.ac.uk/europepmc/webservices/rest/{PMCID}/fullTextXML`
origin and ID grammar: it accepts no arbitrary URL, credential, port,
path traversal or source-program script; follows **no redirects**, accepts
only HTTP 200 with identity-encoded body, caps bytes at 8 MiB and makes
at most **five sequential requests** per invocation. The actual
HTTP-entity bytes must match **exactly** the historic SHA and byte length.
If Europe's current article version differs, the response is
`PROVIDER_BODY_DIFFERS_FROM_HISTORICAL_PIN_NO_WRITE` and no source
or misleading 2026-matched receipt is saved. A modified local cache is
never overwritten or silently replaced.

A successful authorized provider recovery writes *only* to the
pre-existing private directory, creates `PMC….xml` via exclusive
create plus a new `PMC….transfer.json` observation containing the
**current** HTTP 200, URL, observation time and exact body hash. Both
are fsynced; incomplete writes are explicitly reported for review.
The transfer receipt flags
`historical_2026_10_05_transport_proven=false` and
`article_specific_licence_independently_verified=false`.
A historical correction whose *declared* licence version was unclear
is not automatically requested.

## Important methodological distinctions

- Europe PMC `fullTextXML` is **not** the NCBI PMC OAI-PMH raw
  `GetRecord` response envelope. It may support **RW-01Q**
  exposed-development source replay; it does not close the
  separately required [RW-01O original PMC envelope pilot](https://github.com/Smkzz/ResearchWitness/issues/35).
- The source index is *post-hoc exposed*. It does not contain an
  independently timestamped preregistration or prove selection preceded
  knowledge of the correction labels. Do not use it as sealed holdout.
- Real-paper evaluation still requires the *same* verified XML bytes
  in both arms, complete family/case inclusion, actual legal rights and
  version checks, fixed protocol/budgets and truly independent
  substantive source-context review. The installed JATS checker's
  raw-source replay alone **does not adjudicate the publication**.
- Do not normalize/reserialize a newer XML file to force the old SHA.
  A changed source must remain a **version mismatch** with old
  study reproduction incomplete. Genuine negative findings are valid.
- Exactly no incremental spending or protected custody is authorized.

## Present operator evidence

On 28 October 2026, a bounded read-only scan of
`C:\\Projects\\ResearchWitness` found **no original XML/JATS/NXML**
(329 directories, 1,291 ordinary files scanned, no recognized source
archives), while this conversation's model-side runtime failed DNS for
`www.ebi.ac.uk` and the exact official XML URL could not be
retrieved. This does not prove no independently approved private cache
exists, nor that Europe PMC is globally unavailable.

**The recovery implementation has synthetic-only test inputs, and
none of the 13 historic provider bodies was recovered in this task.**
The [RW-01Q scientific comparison](https://github.com/Smkzz/ResearchWitness/issues/50)
therefore remains `blocked_evidence` until actual, permitted bytes
are available. Any successful future run requires independently
collected real provider evidence and a separately reviewed label set.
