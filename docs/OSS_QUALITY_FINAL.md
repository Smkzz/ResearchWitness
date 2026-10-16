# OSS quality: accepted baseline and current validation

**Record updated:** 2026-10-16  
**Version:** `0.3.0.dev0` — **UNRELEASED**  
**PR #13:** [merged](https://github.com/Smkzz/ResearchWitness/pull/13) into protected `main`  
**Internal baseline decision:** `OSS_QUALITY_10_OF_10_VERIFIED`

This is a point-in-time, owner-accepted **AI-assisted engineering assessment**.
It is not an independent human audit, external certification, proof of absence
of unknown defects, or general scientific validation. Later changes require
fresh tests and review; the baseline result must not be silently applied to an
untested commit. [PROJECT_STATUS.md](PROJECT_STATUS.md) is the current-state index.

## Integration and validation identities

The final accepted PR #13 head was
`469c3160a4f58402841f60ddb95e28b67800198a`. It merged at
`cb0270490a9bf1592a1d194cad395912afcefe9f` on 2026-10-16.
Both have tree `657bc3effdf3d85707565a5cb386389787ac2299`.

The merge itself did not change source bytes. Post-merge
[CI 38900068975](https://github.com/Smkzz/ResearchWitness/actions/runs/38900068975)
and [CodeQL 38900068843](https://github.com/Smkzz/ResearchWitness/actions/runs/38900068843)
passed. The final pre-merge
[dependency evidence run 38898296242](https://github.com/Smkzz/ResearchWitness/actions/runs/38898296242)
also passed; it is a dated dependency snapshot, not a guarantee about future
resolutions. [Issue #14](https://github.com/Smkzz/ResearchWitness/issues/14)
records owner acceptance, closure and the post-merge readback.

## Ten-category acceptance scope

| Category | Baseline result | Evidence and continuing limits |
|---|---|---|
| Q1 Repository structure | PASS | Git-index source allowlist, path/mode checks and complete manifest; private and generated task output excluded. |
| Q2 CI/CD | PASS | Nine Python 3.11–3.13 jobs across Ubuntu/Windows/macOS, Release gate and CodeQL. New commits need their own runs. |
| Q3 Code quality | PASS | Ruff E4/E7/E9/F and trusted-core static checks; no configured type checker or universal correctness guarantee. |
| Q4 Security | PASS, scoped | AI source review, hard-link rejection and ownership guards. Real PDF isolation and Windows managed acquisition remain separately unqualified. |
| Q5 Tests | PASS | Baseline reported 98% core and 79% whole-repository coverage; enforced core floor is 90%. POSIX-only skips on Windows remain explicit. |
| Q6 Supply chain | PASS, reviewed snapshot | Authenticated alert inspection, 14 resolved build/dev distributions, PyPI/OSV queries and distributed license/notice review. Not every allowed future version. |
| Q7 Documentation | PASS at accepted snapshot; maintain continuously | Current-state, source-tool dependencies, command semantics and historical records must agree with code; documentation regressions run with the suite. |
| Q8 Evidence hygiene | PASS | Frozen scientific evidence is not changed by housekeeping; historical records retain their original meaning. |
| Q9 Governance | PASS | Active main ruleset, real required checks and owner-accepted disclosed AI technical review. No independent human approval claimed. |
| Q10 Reproducibility | PASS | Source checksums/ZIP regressions, two wheel builds in the same environment, offline installation and examples. Cross-environment byte identity is not assumed. |

The predecessor implementation recorded 498 tests/113 subtests per Linux/macOS
job and 492 tests/113 subtests plus six POSIX-only skips on Windows. Those are
**historical counts**, not expected counts for every future commit. One earlier
Windows optimized-CLI subprocess timeout passed on retry; its cause was not
established. Preserve that observation rather than claiming no timing failure
ever occurred. Exact run details and the 39-file license/notice review remain
in the [preserved pre-merge checkpoint](../validation/history/OSS_QUALITY_CHECKPOINT-premerge-20261016.json).

## Documentation follow-up

A post-merge critical review found stale PR status, missing development/build
prerequisites, incomplete manifest instructions and ambiguous CLI result/offset
semantics. This correction separates current status from historical evidence,
adds a synthetic JATS example, and introduces automated documentation checks.
No verifier algorithm or scientific label is changed. The corrective PR and its
exact-head/post-merge checks are the evidence for the revised files; the older
baseline checks are not misrepresented as executing the new tests.

## Governance and review policy

[Ruleset 25233301](https://github.com/Smkzz/ResearchWitness/rules/25233301) targets
`main`, requires PRs, up-to-date checks and the nine Python/OS checks plus
`Release gate` and `Analyze Python`, bound to GitHub Actions. It blocks force-push
and deletion and has no bypass actors. Zero required approvals preserves the
solo-maintainer workflow.

The owner explicitly accepted the AI-assisted review in place of the project's
self-imposed additional-human-review condition on 2026-10-16. This changes the
internal acceptance policy, not the identity or independence of the reviewer.
An outside program requiring a human audit would still need one.

## Remaining work is not an undisclosed release

PR #13 is merged; other paper-audit PRs require their own integration decisions.
See the [maintainer review](OSS_MAINTAINER_REVIEW.md) and [roadmap](ROADMAP.md).
No package/tag release, scientific Wave 3, protected-custody access, independent
scientific-error confirmation or real PDF qualification follows from this score.
Historical reports are indexed under [project status](PROJECT_STATUS.md#historical-records),
not presented as current blockers.
