# Project status

**As of:** 2026-10-24  
**Version:** `0.3.0.dev0`  
**Release:** UNRELEASED  
**Branch:** `main`  
**Observed pre-plan head:** `242abaa2b5fe1f064ac10f14ae88e9bdfc825c1a`

The current development instructions are [AGENTS.md](../AGENTS.md),
[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) and [EXECUTION_STATE.json](EXECUTION_STATE.json).
This status records an observed software baseline, not automatic qualification
of a later commit. New work needs its own exact-head checks. The plan adds no
claim-compiler, search engine, PDF qualification or scientific result by itself.

## Merged baseline

PR [#13](https://github.com/Smkzz/ResearchWitness/pull/13) merged on 2026-10-16 at
`cb0270490a9bf1592a1d194cad395912afcefe9f`, tree
`657bc3effdf3d85707565a5cb386389787ac2299`. Its qualified head was
`469c3160a4f58402841f60ddb95e28b67800198a`, with the identical tree.
Post-merge [CI 38900068975](https://github.com/Smkzz/ResearchWitness/actions/runs/38900068975)
and [CodeQL 38900068843](https://github.com/Smkzz/ResearchWitness/actions/runs/38900068843)
passed. Those identifiers remain the integration baseline, not the current head.

PR [#17](https://github.com/Smkzz/ResearchWitness/pull/17) merged on 2026-10-16 at
`397ef8a978ff8e9bc406f7de330e45b2a0f8b5f2`, aligning documentation and adding executable
documentation contracts. PR [#18](https://github.com/Smkzz/ResearchWitness/pull/18)
merged on 2026-10-17 at the observed head above, aligning intake/export validation,
reserving generated metadata names and enforcing the 64 MiB aggregate input limit.

At #18, the reported local suite was 521 tests and 181 subtests, with 98.50% core
coverage; synthetic conformance was 500/500 and historical replays 3/3. Main
[CI 39030296638](https://github.com/Smkzz/ResearchWitness/actions/runs/39030296638)
passed all nine Python/OS jobs and Release gate; main
[CodeQL 39030296605](https://github.com/Smkzz/ResearchWitness/actions/runs/39030296605)
passed. The later scheduled [CodeQL 39233639894](https://github.com/Smkzz/ResearchWitness/actions/runs/39233639894)
passed on 2026-10-19 at the same head. These are observed historical checks, not
new runs performed by this documentation change.

[Issue #14](https://github.com/Smkzz/ResearchWitness/issues/14) is closed. The owner's
internal 10/10 engineering acceptance used disclosed AI-assisted review, not an
independent human audit, security certification or scientific evaluation. The
[final assessment](OSS_QUALITY_FINAL.md), [maintainer record](OSS_MAINTAINER_REVIEW.md)
and [checkpoint](../validation/OSS_QUALITY_CHECKPOINT.json) remain pinned records.
No GitHub Release or PyPI publication is claimed for this development version.

## Available and pending

| Area | Observed state | Planned package |
|---|---|---|
| Deterministic verifier, intake, reports/export | Available for ten bounded families | Preserve in RW-01/RW-08 |
| JATS/metadata tools | Checkout-only, narrow supported relationships | RW-01/RW-02/RW-09 |
| Paper-audit stack #6-#11 | Draft, unmerged | RW-01 |
| #12 local preview/custody worker | Draft, unmerged; authority not qualified | RW-03/RW-09 |
| Real PDF extraction | Disabled pending real sandbox/image qualification | RW-03 |
| Windows managed metadata | Fails closed pending ACL ownership qualification | RW-03 |
| Claim compiler and adversarial search | Proposed system components, not implemented end to end | RW-06/RW-07 |
| Research benchmark/independent evaluation | Development tools exist; sealed study not completed | RW-04/RW-05/RW-10/RW-11 |
| Routine agent authority | Autonomous within safety and zero-incremental-cost limits | AGENTS.md |

#5 is an ancestor of #6 and must not be imported as unrelated duplicate work.
Dependency PRs #15/#16 were open at the observed snapshot; recheck before acting.
Installed-core Windows support is tested separately from Windows metadata discovery.
Synthetic PDF/custody tests do not establish real isolation. No protected holdout
run, scientific Wave 3 or broad independent precision/recall claim is established.

## Current operating policy

Agents make ordinary technical decisions, obtain AI review, perform qualified
merges and prepare scoped releases without asking for routine human signoff.
Escalate only new safety-sensitive authority or actual unauthorized spending.
Missing scientific evidence remains a gate, not a request for an opinion.
See [DECISIONS.md](DECISIONS.md). Historical instructions requesting routine approval
record their old context; current work follows AGENTS.md and the new plan.

## Documentation map and preserved history

Current interfaces: [README](../README.md), [architecture](ARCHITECTURE.md),
[protocol](PROTOCOL.md), [offline tools](OFFLINE_RESEARCH_AUDIT.md),
[source review](SCIENTIFIC_CANDIDATE_REVIEW.md), [security](../SECURITY.md),
[PDF qualification](PDF_SANDBOX_QUALIFICATION.md), [contributing](../CONTRIBUTING.md)
and [release procedure](RELEASING.md). [MVP.md](MVP.md) describes the existing narrow
product contract, not a competing future priority list.

The following are dated evidence, not instructions to repeat old approval loops:

- [Initial OSS audit](OSS_QUALITY_AUDIT.md) and the pinned final engineering records.
- [2026-10-15 campaign report](../RESEARCHWITNESS_NEXT_CAMPAIGN_REPORT.md) and its
  [checkpoint](../validation/RESEARCHWITNESS_NEXT_CAMPAIGN_CHECKPOINT.json).
- [2026-10-14 scientific-readiness record](../validation/SCIENTIFIC_EVALUATION_READINESS.md).
- [Historical MVP validation](VALIDATION.md) and [verifier-wave records](../validation/verifier-wave/README.md).
- [Preserved pre-merge checkpoint](../validation/history/OSS_QUALITY_CHECKPOINT-premerge-20261016.json).

Frozen dates, source hashes, failed attempts, exposure decisions and scientific
labels are preserved. Append new evidence; do not relabel old results as current,
independent, human-reviewed or successful. Never publish private custody records.
