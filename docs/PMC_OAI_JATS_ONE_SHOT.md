# RW-01O pilot: one-shot offline original PMC OAI-PMH → JATS review

**Scope:** Engineering-only, development-exposed offline replay. The script is a
checkout tool, **not** part of the installed wheel. No network access, article
download, licence authentication, researcher contact or scientific evaluation
is performed by this script. ResearchWitness 0.3.1 remains a bounded engineering
preview; its scientific discovery performance is not established.

## Before running

Use one complete, **unaltered decoded HTTP response entity** obtained through a
previously authorized, legitimate PMC OAI-PMH `GetRecord` retrieval. For article
`PMC11845954`, the exact requested OAI identifier is
`oai:pubmedcentral.nih.gov:11845954` and the documented endpoint is
`https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/` with `verb=GetRecord` and
`metadataPrefix=pmc`. Obtain article-specific reuse-rights evidence separately
before retrieval. PMC documents that not every article can be reused and that
OAI/Cloud are supported automated retrieval services.

- **Do not** use the article's web HTML, a copied API/Swagger display,
  reconstructed table, normalized XML, an OCR projection or an older Europe PMC
  snapshot as the original raw PMC `GetRecord` envelope.
- Preserve the exact original provider response, observed request, actual HTTP
  status, time, route, decoding stage, original SHA-256 and article-specific
  rights **outside the public repository**. A hash calculated from the file after
  acquisition establishes byte continuity, *not* verified publisher identity.
- Supply the existing strict 11-key transfer-declaration JSON described in
  [`PMC_OAI_ENVELOPE.md`](PMC_OAI_ENVELOPE.md). Never invent a successful HTTP
  status or a licence classification. If no real response is available, record
  `BLOCKED_SOURCE_BYTES_NOT_AVAILABLE` and do not run a successful fake source.
- Only research articles with an unambiguous article-level CC-BY-4.0 or CC0-1.0
  licence link are supported by the current RW-01M parser. Other licences or
  unclear rights must remain unsupported/excluded until separately reviewed.

The source archive contains the checkout-only `tools` package. Execute the tool
from a **clean ResearchWitness 0.3.1 source checkout**, not from a bare wheel:

```text
python -m tools.pmc_oai_jats_pilot \
  --raw-envelope PRIVATE_response.xml \
  --transfer PRIVATE_transfer.json \
  --expected-raw-sha256 SHA256_RETAINED_SEPARATELY \
  --document-id PMC11845954 \
  --output-dir PRIVATE_NEW_RUN_DIRECTORY \
  --include-denominator-trace --include-structure
```

Do not place `PRIVATE_NEW_RUN_DIRECTORY` inside the public checkout or an
unapproved synchronization/CI directory. The output parent must exist and the
output directory must be new. If a parent, permission or transport boundary is
unavailable, do not change the sandbox or run over another service.

## What a completed invocation actually does

1. Read the complete regular-file input and reject any changed external raw hash.
2. Parse the independently supplied transfer declaration; require a single
   matching `GetRecord`, a declared HTTP 200, current `pmc` metadataPrefix, exact
   requested PMCID and compatible linked licence syntax in the XML.
3. Extract the exact `<article>` byte span and derive standalone JATS only where
   necessary to preserve inherited XML namespaces. Preserve the unchanged OAI
   response and separately hash original span, derived article and transfer.
4. Run the **installed JATS arithmetic table detector** from the derived bytes,
   retain original-source anchors, candidate/abstention counts and optional
   denominator trace. Preserve failed or ambiguous context as abstentions.
5. Recreate the XML derivation and entire `replay-jats` report; only then emit a
   terminal `result.json` with exact byte identities and candidate counts.

The successful private output directory contains `original-oai-response.xml`,
`transfer-declaration.json`, `derived-article.xml`, `derivation-receipt.json`,
`jats-audit/` (source.xml, report.json, report.html, manifest.json), and
`result.json`. The source is kept private. All parsers are bounded; unrecognized
formats/identities/licences or corrupted bytes fail rather than invent results.
An interrupted I/O operation may leave a partial directory: **do not** interpret
it as a successful run. Use a new output directory after diagnosing failures.

A local run that receives an externally supplied expected hash calls it
`raw_pin_matched_supplied_value`, not authenticated provenance. The tool cannot
prove that the expected hash was recorded *before* inspection. It does not
authenticate the provider, verify effective rights, judge author intent, or
convert a mathematical mismatch into a paper-error or novelty claim.

## The previously published vitiligo correction

For `PMC11845954`, the author's published `PMC12063958` correction says the
Table 2 values `23 (73.3%)` and `23 (70%)` should both be `23 (76.7%)`.
An earlier exposed developer analysis tested a **manually transcribed**
projection. That projection is not an OAI raw entity. A genuine original-source
JATS scan may show the original numbers, updated/corrected numbers, or a
different source-presentation profile. Preserve whichever version was actually
retrieved; do not inject the known correction into the XML or assume its row
scope is automatically resolved.

The historical exposed October-2026 Europe PMC 13-source SHA frame is a
**different source route/version**. This new PMC OAI pilot does not close the
old **0/13 exact historical recovery** gate. Independent rights and source
context labels, protected custody and scientific efficacy remain blocked.

## Testing

`python -m pytest tests/test_pmc_oai_jats_pilot.py -q` executes invented
strict OAI response fixtures with a source-anchored percentage match,
mismatch and abstention. It checks end-to-end derivation, exact replay, rights/
identity/hash refusal, output overwrite protection and corrupted manifest
rejection. Synthetic fixtures are never real provider evidence.

## Final-receipt and privacy behavior

The tool creates a fresh private directory with the original response, transfer
declaration, derived JATS and JATS-audit bundle. It writes `result.json` **last**,
only after successful exact OAI derivation, audit result identity comparison and
independent JATS replay. An interrupted run can leave a **partial private**
directory, but it must not be interpreted as a completed run; the caller must
review/clean it explicitly, and cannot reuse that path. The result includes
exact feature flags, but omits the absolute local output path to reduce
accidental privacy disclosure. The CLI may still expose source-record SHA-256
identifiers: keep private result files and logs private.

The caller-controlled transfer metadata, declared HTTP status, claimed licence
ID and supplied hash do not independently authenticate the provider. Verify
request/response origins and rights separately under RW-01O's evidence policy.
This tool does not have permission to use an alternate network route to
recover missing original source bytes.
