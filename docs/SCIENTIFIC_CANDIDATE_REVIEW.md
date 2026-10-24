# Public scientific candidate review

**Current work:** RW-02/RW-05 under [AGENTS.md](../AGENTS.md) and the
[development plan](DEVELOPMENT_PLAN.md). Public discovery produces development
candidates, not established paper errors or untouched frozen-evaluation cases.

## Metadata discovery into a fresh campaign

Create a new permitted output directory outside tracked historical evidence before
running these templates; `work/discovery-new` is an example, not a reserved dataset.
Do not overwrite `validation/public-candidate-registry.json` or old campaign records.

```text
python tools/discover_public_candidates.py discover --provider europe-pmc --limit 25 --output work/discovery-new/registry.json
python tools/discover_public_candidates.py discover --provider crossref --limit 25 --existing work/discovery-new/registry.json --output work/discovery-new/registry.json
python tools/discover_public_candidates.py summarize work/discovery-new/registry.json
```

Use only configured approved hosts. The collector is outside the trusted core:
read-only HTTPS via the inherited managed proxy, no bypass routes, cross-host
redirect rejection, bounded responses and one-second per-host request-start spacing
across processes in a verified private per-user state directory. It stops on access/
transport failure, does not use publisher credentials or fetch full text, and hashes
metadata responses rather than original article/correction bytes.

The managed transport currently requires POSIX ownership/mode checks. Other platforms,
including Windows, fail before networking until a reviewed ACL guard is qualified.
Installed-core Windows support is separate. Do not bypass this boundary to make a
search succeed. New money use or security authority needs a decision; ordinary
research/engineering choices do not.

## Source capture and review modality

A separate source reviewer captures original/correction versions from permitted
sources, checks license and exact population/table/denominator/units, and records
hashes and stable anchors. Model consensus or a correction title is not ground truth.
AI agents may perform source-backed review without mandatory human opinion; record
actual modality, access/context independence and unresolved ambiguities. Never put
AI work in a field meaning human review or claim that a second prompt proves custody
isolation. Existing runtime/schema states are not changed by this instruction.

## Offline JATS aid

Use the [integrated offline workflow](OFFLINE_RESEARCH_AUDIT.md), or:

```text
python -m tools.jats_percentage_audit path/to/article.xml
```

The tool records supplied-byte hashes and source anchors. It checks supported
`n (%)`, explicit `n/N (%)` and headed count/percent relationships using exact
arithmetic and the contract's half-up display rule. Valid comma-grouped integers
are supported; scope, layout, missingness, weighting/adjustment and alternative
rounding rules may require abstention. DTD/entity declarations and excessive input
are refused. A source hash is not authentication; bounded parsing is not OS isolation.
Every automatic mismatch is a candidate, not a scientific error.

## Offline PDF aid

Real execution remains disabled until [PDF_SANDBOX_QUALIFICATION.md](PDF_SANDBOX_QUALIFICATION.md)
is satisfied. The existing strict runner uses a locally reviewed SHA-256 image,
stdin bytes, no network/host-file mount, read-only root, unprivileged execution,
seccomp/no-new-privileges and bounded resources/output/time with verified cleanup.
Missing image/isolation or failed cleanup must fail closed; no host fallback.
The exact operational requirements are in [SECURITY.md](../SECURITY.md).

PDF evidence includes raw/extracted hashes and page/line/character locations in
extracted text; those are not byte offsets in the original PDF. Simple text-table
arithmetic does not guarantee complete layout/methods fidelity. Image-only input
and OCR remain unsupported. Article-level adjustments require source review.

## Correction-backed positives

Verify exact original/corrected versions and source authority; preserve their
numerical statements/anchors; recompute the relationship; confirm population,
denominator, units and correction scope; apply the registered eligibility contract;
and retain unresolved issues and exposure history. A development-discovered case
is never converted to an untouched holdout by subsequent independent review.

## Correct negatives

Independently verify source/version/location, operands, precision, population,
subgroup and rounding. Do not infer a denominator because it produces agreement.
Group DOI aliases, versions, supplements and related datasets conservatively into
work families. Multiple rows in one family do not become independent papers.
Ambiguous cases are unresolved, not convenient negatives.

## Custody and scientific claims

Only the authorized isolated custodian updates protected qualification records.
The developer registry has no holdout-promotion field. Public receipts contain
safe aggregates and commitments, never reserved identities, labels, targets or
private custody details. [BENCHMARK_PROTOCOL.md](BENCHMARK_PROTOCOL.md) defines the
new protocol requirements without relaxing historical v1.3 gates. Agent authority
to work does not establish scientific applicability or data independence.

## Failures and bounded iteration

A provider/source denial is not a successful empty search. Challenge pages are
failures, not research content. Hash only complete retrieved documents as sources.
Do not switch route/host/proxy/account to bypass a denial. The CLI's fixed
`transport_error_class` is operational output, not a new registry schema field;
do not persist raw exception/proxy details publicly.

Local registry inputs must be regular UTF-8 files no larger than 8 MiB, with at
most 250 candidates and 500 searches. Archive separate campaigns rather than
merging an unbounded history. After repeated identical failures, record the blocker
and choose independent safe work; do not repeatedly ask whether to continue.
