# ResearchWitness OSS quality — final assessment

**Assessment date:** 2026-10-16  
**Implementation evidence:** `1938496eed153816cc4cf58455d4c7e0d1988ae5`  
**Implementation tree:** `bfdfdd9717979188c44677dcfbb3e67969ff6c1c`  
**PR #13:** [open, draft, unmerged](https://github.com/Smkzz/ResearchWitness/pull/13)  
**Status:** `OSS_QUALITY_NOT_YET_10_OF_10`

ResearchWitness now has a qualified Python 3.11–3.13 CI matrix on Ubuntu,
Windows and macOS; a passing Linux release gate; deterministic verifier-core
coverage enforcement; explicit source-tool/PDF boundaries; and a Git-index-only
release inventory with portable path checks. Exact-head CI passed 490 tests and
108 subtests on Linux/macOS per job, and 484 tests plus 108 subtests on Windows
with six POSIX-only tests skipped. Trusted-core coverage was 98%; whole-repository
coverage was 79%. CodeQL passed with no new alerts in the PR diff.

The cross-platform run caught and repaired newline conversion, deterministic
report writing, and filesystem-dependent path tests. The release gate and all
nine Python/OS jobs pass at the implementation evidence head. The local executor
could not install development dependencies because its proxy connection was
denied before HTTP; hosted CI performed the dependency installation and release
qualification. No retries or network restrictions were bypassed.

The software status is not 10/10 because repository administration and
independent maintainer actions remain open. The public repository has no
description/topics, `main` is not protected and has no ruleset, security-alert
and complete dependency/license views are unavailable through the current
connection, and no human maintainer review of PR #13 is recorded. These are
specific owner tasks, not reasons to stop the engineering work already completed.

## Ten-category result

| Category | Result |
|---|---|
| Q1 Repository structure and release selection | PASS |
| Q2 CI/CD reliability | PASS |
| Q3 Code quality | PASS |
| Q4 Security and trust boundaries, scoped to documented fail-closed capabilities | PASS |
| Q5 Testing and regression protection | PASS |
| Q6 Dependencies and software supply chain | BLOCKED |
| Q7 Documentation and contributor experience | PASS |
| Q8 File and research-evidence hygiene | PASS |
| Q9 GitHub governance and PR management | BLOCKED |
| Q10 Clean-checkout reproducibility and public readiness | PASS |

The supporting evidence, exact job results, coverage review, complete PR
disposition, file decisions and owner configuration steps are in
[`OSS_QUALITY_AUDIT.md`](OSS_QUALITY_AUDIT.md) and
[`validation/OSS_QUALITY_CHECKPOINT.json`](../validation/OSS_QUALITY_CHECKPOINT.json).

## Smallest remaining action list

1. A repository owner sets the description/topics and protects `main` with the
   exact required checks, PR-only updates, and force-push/deletion disabled.
2. An owner with Security access inspects and records Dependabot alerts and
   dependency/license advisories. No claim of zero alerts is made here.
3. A human maintainer reviews PR #13 and chooses the disposition/integration
   order for #5–#12. PR #5 appears superseded by #6 but remains open until the
   owner confirms.

The PDF research-audit aid remains unavailable until its pinned image and
effective Docker isolation are independently qualified; it fails closed. No
protected custody, reserved evaluation paper, Wave 3, merge or release was
performed.
