# Project status

**As of:** 2026-10-16  
**Version:** `0.3.0.dev0`  
**Release:** UNRELEASED  
**Branch:** `main`  
**PR #13:** merged on 2026-10-16 at 12:22:34 UTC

This maintained index distinguishes current capabilities from pinned historical
verification. It does not claim that an untested future commit has passed CI.
Every new change needs its own exact-head checks.

## Merged baseline

PR [#13](https://github.com/Smkzz/ResearchWitness/pull/13) merged at
`cb0270490a9bf1592a1d194cad395912afcefe9f`, tree
`657bc3effdf3d85707565a5cb386389787ac2299`. Its qualified final head was
`469c3160a4f58402841f60ddb95e28b67800198a`, with the identical tree.
Post-merge [CI 38900068975](https://github.com/Smkzz/ResearchWitness/actions/runs/38900068975)
and [CodeQL 38900068843](https://github.com/Smkzz/ResearchWitness/actions/runs/38900068843)
passed at that merge commit. These identifiers describe the integration baseline,
not a perpetually current branch-head identity.

[Issue #14](https://github.com/Smkzz/ResearchWitness/issues/14) records the internal
10/10 engineering acceptance under the owner's explicit approval of a disclosed
AI-assisted technical review. No independent human audit, external certification
or general scientific validation is claimed. The [final assessment](OSS_QUALITY_FINAL.md),
[maintainer review](OSS_MAINTAINER_REVIEW.md) and
[current checkpoint](../validation/OSS_QUALITY_CHECKPOINT.json) distinguish
this integration record from earlier evidence.

`0.3.0.dev0` remains unreleased: no tagged GitHub Release or PyPI publication is
claimed. Merging software does not authorize a package release.

## Available on main

- Dependency-free installed verifier, ten bounded checker families, structured
  intake/schema/scaffold interfaces and deterministic evidence replay.
- Source-checkout JATS arithmetic audit, source-bound comparison, JSON/Markdown
  reports, conditional calculations and conservative abstentions. Install
  `python -m pip install -e '.[dev]'` from the repository root.
- Guarded metadata discovery, bounded file input, Git-index source ZIP selection,
  cross-platform CI, Ruff and verifier-core coverage enforcement.

Start with the [core quickstart](../README.md#quick-start),
[synthetic JATS example](../README.md#offline-jats-audit),
[source-tool reference](OFFLINE_RESEARCH_AUDIT.md), [architecture](ARCHITECTURE.md)
and [release procedure](RELEASING.md).

## Pending work and boundaries

PR #6–#11 remain a separate unmerged paper-audit stack. PR #12 adds a custody
worker requiring separate security review. The merged source-checkout tools do
not install that stack's `researchwitness.paper_audit` implementation. This
documentation change neither integrates those PRs nor grants custody authority.

Windows managed metadata discovery fails closed pending a reviewed ACL ownership
guard; installed-core Windows support is separate. Real PDF extraction awaits a
reviewed pinned image and qualified Docker boundary. Synthetic tests do not
qualify that boundary. Sealed holdout evaluation and scientific Wave 3 have not
run. See the [roadmap](ROADMAP.md); research results remain developer-exposed.

## Historical records

Historical dates, failed attempts, counts, hashes and limitations are retained.
Old branch/review states describe their stated snapshot, not a current failure.

- [Initial OSS quality audit](OSS_QUALITY_AUDIT.md)
- [2026-10-15 campaign report](../RESEARCHWITNESS_NEXT_CAMPAIGN_REPORT.md)
- [2026-10-14 scientific-readiness record](../validation/SCIENTIFIC_EVALUATION_READINESS.md)
- [Historical MVP validation](VALIDATION.md)
- [Historical verifier-wave records](../validation/verifier-wave/README.md)
- [Preserved pre-merge engineering checkpoint](../validation/history/OSS_QUALITY_CHECKPOINT-premerge-20261016.json)

Frozen experiments and scientific JSON evidence are not relabeled as new or
independent validation. The synthetic documentation fixture contains no real
study data.
