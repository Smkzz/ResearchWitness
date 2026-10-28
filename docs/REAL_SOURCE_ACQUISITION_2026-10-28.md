# RW-01Q2: real-source acquisition and comparison record

**Status:** acquisition in progress; no empirical method run yet.
**Code under study:** `7115c0a7fc2db073d1d7bb90a3afe586454b1a36`.
**Scope:** developer-exposed material; zero incremental spending.

This record separates an official response observed in a browser, an actual
source file retained unchanged, historical byte continuity, and a source-grounded
method comparison. None implies the next. [RW-01Q #50](https://github.com/Smkzz/ResearchWitness/issues/50)
and [RW-01O #35](https://github.com/Smkzz/ResearchWitness/issues/35) remain open.

## Fixed source frame and ordinary source links

The complete [historical index](../examples/historical-source-recovery/wave1-source-index.json)
contains nine articles and four correction records. Its SHA-256 is
`d0a3ee22f15868f9c97b4cdf8faa866211f753f562a33370b610a67549958f95`.
All 13 records remain in acquisition accounting. The following five records
form a bounded, already-exposed convenience subset. Failures are not replaced.
These ordinary HTTPS links are provided for source inspection and permitted
file acquisition in an already authorized environment; they grant no new
network or custody authority.

| Order | Source role | Official XML | Article-specific rights evidence |
|---|---|---|---|
| 1 | J-EINSTEIN article | [PMC4339301 fullTextXML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC4339301/fullTextXML) | [Original article](https://pmc.ncbi.nlm.nih.gov/articles/PMC4339301/) explicitly links CC BY 4.0. |
| 2 | J-EINSTEIN correction | [PMC4877730 fullTextXML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC4877730/fullTextXML) | [Publisher correction](https://link.springer.com/article/10.1186/s12959-016-0085-1) explicitly identifies CC BY 4.0. |
| 3 | Vitiligo article | [PMC11845954 fullTextXML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11845954/fullTextXML) | [Original article](https://pmc.ncbi.nlm.nih.gov/articles/PMC11845954/) explicitly identifies CC BY 4.0. |
| 4 | Vitiligo correction | [PMC12063958 fullTextXML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12063958/fullTextXML) | [Correction](https://pmc.ncbi.nlm.nih.gov/articles/PMC12063958/) explicitly identifies CC BY 4.0. |
| 5 | Previously selected, uncertified control | [PMC11148689 fullTextXML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11148689/fullTextXML) | [Article](https://pmc.ncbi.nlm.nih.gov/articles/PMC11148689/) links its [publisher's CC-BY permission](https://jamanetwork.com/pages/cc-by-license-permissions); the numeric licence version is not displayed there. |

Attribution and source/version records must accompany permitted reuse. Current
licence observations are AI-assisted checks of primary pages, not an independent
legal opinion. The last row's historical CC BY 4.0 declaration is not silently
promoted into a newly observed numeric licence version. A selected control is
not an independently certified error-free publication.

## What acquisition has actually established

The existing browser session successfully used the official Europe PMC
interactive REST interface for the first article and observed HTTP 200 with
XML content. A direct HTTPS XML view was also available. This supersedes the
earlier claim that no accessible environment could reach that source service;
it does not establish a retained original response body.

The interactive Swagger display reformats XML. Its display/download must not be
assumed byte-identical to the REST entity. The [upstream response component](https://github.com/swagger-api/swagger-ui/blob/main/src/core/components/response-body.jsx)
explicitly formats XML before rendering its downloadable code view; this is a
representation risk, not a reason to reconstruct an old hash. A browser
`view-source:` navigation was policy-blocked and was stopped. Existing network,
isolation and browser security settings were not changed.

The official [export format guide](https://europepmc.org/docs/Europe_PMC_Export_Formats_Feature_List.pdf)
documents an `XML (open access full text)` export. Attempts through the ordinary
article/search UI did not yet provide a retained file. An export response
reported `Sanity check failed`; no successful acquisition is inferred from a
button click. Source acquisition remains unresolved pending exact file bytes.

Read-only searches of accessible historical repository heads, relevant CI
artifacts and available archive metadata identified no original XML body.
Prior owner notes describe an evidence archive, but the original archive was not
located or materialized here. This is bounded search evidence, not proof of
global absence. No protected source store was opened.

## Pre-method comparison design

Both methods will use the same installed wheel built from the exact code above,
the same unchanged admitted files, and the same evidence flags:
`--include-structure --include-denominator-trace`.

The baseline uses the existing percentage checker. The candidate also enables
all five existing checks, fixed before execution:

```text
--include-unadjusted-2x2 --include-prose-flows --include-prisma-flows
--include-count-totals --include-sd-se-n
```

This is a nested feature comparison. The existing `registered_jats_run` is a
percentage-only runner and does not execute these installed opt-ins. Each
admitted article receives one invocation per method and one `replay-jats`
verification per produced bundle. Corrections provide source context and are
not additional independent article inputs. Parser refusals, acquisition failures,
incomplete coverage and unresolved applicability stay visible.

The initial acquisition design was amended before method execution to allow at
most ten source GET attempts, including the two already observed, within the
same five-record subset. This amendment diagnoses transport/representation
failures, changes no method flags, and does not reset failed attempts. Preserve
the actual attempt ledger and any uncertainty about provider-side requests.
Do not make further requests if the bounded count cannot be established.

Any current file whose bytes differ from the historical pin belongs to a
separately identified current-source run. It cannot replace the historical
snapshot. An official exported representation is not automatically the raw
REST response. Preserve files unchanged; never strip declarations, repair
newlines or reserialize research sources to make them pass.

## Claims this design cannot establish

Known correction targets and the first source-availability result were exposed
before this plan. It is not an independent preregistration or a sealed study.
Shared-workspace AI reviews do not supply independent scientific custody or
human adjudication. Descriptive candidate counts do not establish precision,
recall, scientific error, improved general performance, or clinical impact.
A negative comparison is an admissible outcome.

Europe PMC `fullTextXML` and PMC OAI-PMH `GetRecord` original envelopes are
different objects. This activity cannot complete the separate RW-01O envelope
requirement. Version remains `0.3.0.dev0`, UNRELEASED.
