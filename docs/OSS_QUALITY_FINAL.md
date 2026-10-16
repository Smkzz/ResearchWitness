# ResearchWitness OSS quality — final closure assessment

**Date:** 2026-10-16  
**Validated implementation:** `93efdf4cdf20085a7fd914d3ce647c646ab6fe0a`  
**Implementation tree:** `fc38026bb2ce5e6b8cb5fea0d301b5b60f3a68a5`  
**PR #13:** [open, draft, unmerged](https://github.com/Smkzz/ResearchWitness/pull/13)  
**Decision:** `OSS_QUALITY_10_OF_10_VERIFIED` — all ten internal engineering categories PASS under the owner's 2026-10-16 acceptance of disclosed AI-assisted technical review. This is not independent human approval, release authorization, or scientific validation.

## What is now complete

The requested description and all five topics were saved and verified on a fresh
GitHub page. [The active main ruleset](https://github.com/Smkzz/ResearchWitness/rules/25233301)
requires PRs, all nine Python/OS jobs, `Release gate` and `Analyze Python`, bound
to GitHub Actions. It prevents force pushes and deletion, requires an up-to-date
branch, has no bypass actors, and requires zero approvals for solo-maintainer
operation. Its effective public view matches `main`; the API reports the branch
protected. These administrative operations require no further owner click-through.

Authenticated Security views were inspected. Dependabot and secret scanning each
showed 0 open / 0 closed alerts; main and PR #13 code-scanning views showed no
alerts. Advisory counts were zero in triage, draft, published and closed states.
Dependency graph, alerts, security-fix PRs, malware monitoring and private
vulnerability reporting are enabled. Silent development-alert dismissal was
disabled. No real alert was dismissed to improve the score.

The [dependency evidence job](https://github.com/Smkzz/ResearchWitness/actions/runs/38891822570)
resolved 14 build/dev distributions, captured distributed license/notice evidence
and queried PyPI plus OSV successfully with zero advisories at the recorded time.
The distribution review retains setuptools' LGPL-3 and MPL-2.0 component notices;
its MIT package metadata does not replace those terms. These build/dev packages
are not bundled in the ResearchWitness runtime wheel. No runtime license blocker
was evidenced. Future dependency resolutions require fresh review.

An AI-assisted technical review inspected all 52 original PR changed paths and
supporting controls. A conditional low Windows rate-state finding was repaired by
refusing managed discovery where ownership cannot be verified. Development file
readers also reject hard links. Supplementary changes were reviewed after fixes.
The trusted verifier's checker semantics remain unchanged. Real Windows discovery
awaits an ACL guard; real PDF extraction awaits separate image/runtime qualification.

## Ten-category result

| Category | Result | Evidence |
|---|---|---|
| Q1 Repository structure and release selection | PASS | Git-index allowlist, safe portable paths and complete source checksum inventory. |
| Q2 CI/CD reliability | PASS | All nine Python 3.11–3.13 × Ubuntu/Windows/macOS jobs, Release gate and CodeQL passed at the implementation head. |
| Q3 Code quality | PASS | Ruff and trusted-core static gate passed. |
| Q4 Security and documented trust boundaries | PASS, scoped | Full AI source review, repaired local guards, no outstanding scoped source finding; no security certification or real PDF qualification claim. |
| Q5 Testing and regression protection | PASS | 498 tests and 113 subtests per Linux/macOS job; Windows 492 tests, six POSIX-only skips and 113 subtests. Core coverage 98%, enforced floor 90%; whole repository 79%. |
| Q6 Dependencies and supply chain | PASS, resolved snapshot | Actual Security views; 14-distribution advisory review; shipped license/notice review; pinned Actions and least-privilege workflows. |
| Q7 Documentation | PASS | Installed-core/source-tool distinction and platform/qualification limits are explicit. |
| Q8 File/evidence hygiene | PASS | Release inventory excludes private task/build/cache state; no protected custody or reserved evaluation accessed. |
| Q9 GitHub governance and maintainer review | PASS — owner-accepted AI review | Metadata and active main protection verified. The owner explicitly accepted the disclosed AI technical review instead of requiring a second human reviewer for this internal gate. No independent human review is claimed. |
| Q10 Reproducibility | PASS | Exact-head release gate, source checksums and ZIP regression, two matching wheels, offline install, synthetic 500/500 and historical replay. |

[CI run 38891822471](https://github.com/Smkzz/ResearchWitness/actions/runs/38891822471)
passed after a retry. The first Windows Python 3.11 attempt hit the unchanged
optimized-CLI test's ten-second subprocess timeout; the same source passed on
retry. The cause of that timing event was not established. No test, timeout or
coverage threshold was weakened. [CodeQL 38891822456](https://github.com/Smkzz/ResearchWitness/actions/runs/38891822456)
and the dependency job passed. Heavy local dispatch was deferred because the
authorized memory preflight could not obtain telemetry; hosted jobs supplied
the comprehensive validation.

## Owner decision and completion

On 2026-10-16, the repository owner expressly accepted the disclosed
AI-assisted technical assessment as sufficient for the project's own Q9
review requirement. An additional human reviewer is therefore **not required
for this internal engineering-quality standard**. This is a deliberate
owner-approved review-policy revision, not a false claim that an independent
human review occurred. Exact post-documentation checks are referenced in
[issue #14](https://github.com/Smkzz/ResearchWitness/issues/14).

**All ten internal OSS engineering categories PASS for the reviewed PR #13
scope.** The result applies to the verified commit, not to future changes,
an external certification, a full scientific validation, or an assurance
that unknown vulnerabilities do not exist.

No merge, release, scientific Wave 3, real PDF sandbox qualification, or
protected-custody operation is authorized by this acceptance.

Recommended eventual order: integrate AI-reviewed #13 only with separate owner authorization; reconcile the six
shared files with #6; then #6–#11 in ancestry order; give #12 its own custody-worker
security review. #5 is an ancestor/superseded snapshot of #6 and remains open
pending owner-approved disposition. No PR was merged, closed, retargeted or force-pushed.

This document binds the implementation validation above. The final documentation
commit, its exact-head checks and readbacks are recorded in issue #14 to avoid a
self-referential commit identifier in the checksummed source tree. The earlier
[`OSS_QUALITY_AUDIT.md`](OSS_QUALITY_AUDIT.md) is retained as a historical baseline;
[`OSS_QUALITY_CHECKPOINT.json`](../validation/OSS_QUALITY_CHECKPOINT.json) and this
report supersede its former administration/supply-chain blockers.

OSS engineering quality remains separate from scientific qualification: no
Wave 3, reserved evaluation, protected custody access, scientific-error finding,
real PDF execution, merge or release was performed.
