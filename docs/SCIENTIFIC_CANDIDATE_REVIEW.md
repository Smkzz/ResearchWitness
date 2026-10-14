# Public scientific candidate review handoff

This workflow creates **development candidates** from public metadata. It does not establish that an article contains an error, that a formal correction applies to the same data scope, or that a candidate is eligible for the frozen v1.3 evaluation.

## Run a metadata search

Use only the approved public API hosts configured in `tools/public_discovery.py`:

```bash
python tools/discover_public_candidates.py discover \
  --provider europe-pmc --limit 25 \
  --output validation/public-candidate-registry.json

python tools/discover_public_candidates.py discover \
  --provider crossref --limit 25 \
  --existing validation/public-candidate-registry.json \
  --output validation/public-candidate-registry.json

python tools/discover_public_candidates.py summarize \
  validation/public-candidate-registry.json
```

The collector is a tool outside the trusted `researchwitness` core. It is read-only, requires HTTPS through the inherited managed proxy, rejects proxy-bypass routes and cross-host redirects before following them, caps response sizes, and enforces a one-second per-host request-start interval across collector processes using a verified private per-user state directory and file. It stops on an access or transport failure. It does not follow DOI links to publishers, use credentials, retry a denial, or retain article full text. The recorded SHA-256 is for the returned metadata response, not for the original article or correction.

Search hits are only metadata leads. An independent reviewer must capture the original and correction versions from a permitted public source, verify the applicable license, record content hashes and stable source anchors, and compare the exact numerical statements and scope. The code's percentage recomputation is only arithmetic at the printed precision; it cannot resolve cohort, denominator, table, or correction scope.

## Adjudicate a correction-backed positive

For each proposed positive, the reviewer should independently:

1. Confirm the original article and version, then confirm the separate authoritative correction and its publication date.
2. Verify the exact original and corrected numerical statements from those sources and preserve source hashes and provenance.
3. Recompute the relationship and check that the correction covers the same table, population, cohort, denominator, and units.
4. Record whether the issue satisfies the frozen contract v1.3 and document every unresolved ambiguity.
5. Confirm exposure history. A candidate found by this development workflow is exposed and must never be called an untouched holdout case.

## Adjudicate a correct negative relationship

For each proposed negative, independently verify the published version and exact source location; identify the numerator, denominator, reported percent, display precision, population and subgroup; recompute using the contract's rounding rule; and record ambiguity rather than infer denominator scope. Resolve DOI aliases, versions, supplements, and related records into work families. Count at most one independent work per confirmed family, regardless of how many tables or rows it contributes.

## Keep evaluation evidence separate

This registry intentionally has no field that can mark a developer-discovered candidate as a holdout. Independent review of a development candidate may support development or a demonstration set; it does not create an untouched evaluation example. Only the authorized custodian can update the private qualification record. Public reports may carry approved aggregates and integrity commitments, never reserved identifiers, labels, correction targets, or private custody records.

## Current run boundary

On 2026-10-14, two Europe PMC metadata attempts failed before an HTTP response: one earlier run reported `MANAGED_PROXY_UNAVAILABLE`, and the current run reported `TRANSPORT_UNAVAILABLE`. A separate Crossref request also failed before an HTTP response with `TRANSPORT_UNAVAILABLE`. No candidate metadata, original article, or correction notice was retrieved. The registry retains all three failures with request URLs where available and leaves result counts unknown; this does not represent a zero-result search. Further source calls stopped after both approved provider routes failed.
