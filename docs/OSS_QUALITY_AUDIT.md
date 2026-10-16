# ResearchWitness OSS quality audit

**Assessment date:** 2026-10-16  
**Repository:** `Smkzz/ResearchWitness`  
**Pull request:** [#13](https://github.com/Smkzz/ResearchWitness/pull/13), open and draft  
**Validated implementation commit:** `1938496eed153816cc4cf58455d4c7e0d1988ae5`  
**Validated implementation tree:** `bfdfdd9717979188c44677dcfbb3e67969ff6c1c`  
**Overall:** `OSS_QUALITY_NOT_YET_10_OF_10`

This is a public engineering assessment, not a scientific evaluation. It does not
access protected custody, reserved evaluation identifiers or labels, run Wave 3,
or claim a new research finding. PR #13 remains draft and unmerged.

## Ten-category assessment

| Category | Result | Evidence and limits |
|---|---|---|
| Q1. Repository structure and release selection | PASS | The release selector uses Git-indexed, allowlisted files; rejects unstaged selected files, symlinks, non-regular files, unsafe portable paths, path collisions and file/directory conflicts; and excludes ignored/untracked build output. At the validated implementation head, 176 files were selected including the manifest, with 175 checksum entries. Checksum verification passed. The three audit files raise the final snapshot to 179 selected files and 178 manifest entries; the updated manifest and complete inventory are checked locally and by the final hosted release gate. |
| Q2. CI/CD reliability | PASS | Exact implementation head CI run [38881012074](https://github.com/Smkzz/ResearchWitness/actions/runs/38881012074) passed its 9 Python/OS matrix jobs and Linux release gate. CodeQL run [38881012098](https://github.com/Smkzz/ResearchWitness/actions/runs/38881012098) passed. Actions are SHA-pinned; workflow permissions are read-only for source contents; checkout credentials are not persisted. |
| Q3. Code quality | PASS | Ruff passed in all CI matrix jobs (`E4`, `E7`, `E9`, `F`). The trusted core compiles and its static forbidden-import/call scan passes. No type checker is configured; none was added without a useful, reviewed policy. |
| Q4. Security and trust boundaries | PASS, scoped | CodeQL reported no new alerts in the PR diff, and the full PR diff was reviewed for credentials, private custody information and unsafe release paths. PDF execution remains explicitly unavailable unless an operator supplies a reviewed local image and the required Docker boundary; no real PDF was run. This is evidence for the implemented fail-closed boundary, not a security certification or proof of a host/kernel isolation boundary. The separate Codex security-scan tool was unavailable in this tool session. |
| Q5. Testing and regression protection | PASS | Linux and macOS jobs each passed 490 tests and 108 subtests for every Python version. Windows jobs passed 484 tests, skipped 6 POSIX-only tests, and passed 108 subtests for each Python version. CI enforces at least 90% coverage for the verifier core; Python 3.12 measured 98% core coverage and 79% total repository coverage. The development tools are reported separately below; the 79% total is not hidden by the core figure. |
| Q6. Dependencies and software supply chain | BLOCKED | The installed package has no runtime dependencies; development dependencies are version-bounded, and Dependabot plus pinned GitHub Actions are configured. The connected GitHub tools do not expose the repository alert or complete license/advisory views, so this audit cannot establish whether alerts exist or complete a transitive license review. |
| Q7. Documentation and contributor experience | PASS | README now separates the installed deterministic verifier from source-checkout JATS/PDF and discovery tools, gives exact commands, and states the PDF qualification limit. The installed wheel was tested in an isolated offline environment; the README verifier and source-tool help/synthetic commands passed. |
| Q8. File and research-evidence hygiene | PASS | The exact PR inventory was reviewed for credentials and protected material; no high-confidence secret-pattern matches were found. Ignored caches/build/egg-info and untracked files are not selected for release. `RESEARCHWITNESS_NEXT_CAMPAIGN_REPORT.md` is retained as a dated, aggregate-only PR handoff and is intentionally outside the release allowlist. No protected custody or reserved evaluation material was accessed. |
| Q9. GitHub governance and PR management | BLOCKED | The public repository has no description or topics. `main` reports `protected: false`, and the rulesets endpoint returns an empty list. The connection cannot read branch protection (403) or mutate repository settings. No human maintainer review is recorded on #13; #12 has only a `COMMENTED` submission from `github-advanced-security`. All PRs #5–#13 remain open and draft. |
| Q10. Clean-checkout reproducibility and public readiness | PASS | Fresh hosted jobs installed declared development dependencies and ran the exact source checkout. The release gate passed reproducible-wheel, offline-install and installed-CLI checks; the source archive reproducibility regression passed. The local executor could not install development dependencies because its proxy connection was denied before HTTP, so no network retry or bypass was attempted. |

## Cross-platform failures found and repaired

The first expanded matrix at `64a4fed900ad1608383ff79d8afdce0f043feac3` exposed
three portability issues. Linux and the release gate passed, while the macOS and
Windows jobs found them:

1. Git's Windows checkout could convert text to CRLF, changing source bytes and
   breaking source-hash checks. `.gitattributes` now pins text checkout to LF;
   an isolated `core.autocrlf=true` checkout rehearsal preserved the source hashes.
2. Windows text output translated newlines when writing audit JSON/Markdown. The
   writer now emits LF explicitly, and a regression test asserts byte-stable output.
3. Case-only paths and Windows-reserved names cannot be represented reliably by
   macOS/Windows filesystems. Release-inventory path validation now checks the
   complete Git-index path set before filesystem access. Tests use synthetic
   Git-index entries, so the unsafe-path checks run on every OS without relying
   on the host filesystem to create those names.

The repair at `1938496eed153816cc4cf58455d4c7e0d1988ae5` passed the complete
matrix and release gate. No release check was disabled or weakened.

## Coverage review

The Python 3.12 Linux report recorded 4,614 statements, 1,768 branches, 79%
combined coverage for the repository, and 98% for `researchwitness/*.py`. The
90% trusted-core threshold is enforced. Selected source-checkout tool results:

| Module | Coverage | Review note |
|---|---:|---|
| `tools/jats_percentage_audit.py` | 90% | Table parsing, source spans, denominator inheritance and conservative abstentions have focused regression tests. |
| `tools/pdf_percentage_audit.py` | 84% | Fail-closed runner/configuration paths are tested; actual execution remains blocked until an operator qualifies the image and Docker boundary. |
| `tools/public_discovery.py` | 80% | Transport, host/proxy/redirect restrictions, bounds and failure classes are covered with offline tests; no real source retrieval was attempted here. |
| `tools/research_audit.py` | 86% | Hash, provenance, report path, abstention, schema and failure behavior have focused tests. |
| `tools/percentage_benchmark.py` | 76% | Annotation, evidence, denominator and regression logic has tests; residual branches are visible in the CI report. |
| `tools/make_release.py` | 67% | Path safety and deterministic source-archive behavior are tested; the first cross-platform run prompted additional index-driven collision tests. |

Some standalone generation/maintenance scripts have low measured test coverage
because the release workflow executes them as separate commands. Their coverage
is not represented as 100% merely because the gate passed. No further tests were
added solely to raise a percentage; the remaining misses need a concrete failure
mode before they justify new code.

## PR #5–#13 disposition

All nine PRs are open and draft. No merge, retarget, or closure was performed.
Counts for #5–#12 are the current GitHub changed-path counts. PR #13 had 48
changed paths before the portability repair, 49 after adding `.gitattributes`,
and 52 after adding these three audit files.

| PR | Base → head | Changed paths | Classification and disposition |
|---|---|---:|---|
| #5 | `main` → `8d913624` | 222 | Earlier fail-closed paper-audit implementation. Its changed-path set is fully present in #6. The #6 tree contains every #5 path; 335 of 345 common tracked blobs are byte-identical and 10 evolved. Likely superseded by #6, subject to owner review; no #5-only changed paths were found. |
| #6 | `main` → `94cd1585` | 242 | Independent structured JATS/paper-audit foundation. It contains the #5 snapshot and is the parent of the later capability stack. Review before integrating. |
| #7 | #6 → `57fedcd9` | 37 | Stacked source-mapped audit capability expansion. |
| #8 | #7 → `80f1ee01` | 10 | Stacked source-follow-up and evidence qualification updates. |
| #9 | #8 → `5a50406e` | 15 | Stacked correction-evidence maturation. |
| #10 | #9 → `f2490bd5` | 30 | Stacked count/percentage v1.2 qualification work. |
| #11 | #10 → `6843593f` | 25 | Stacked denominator-provenance v1.3 work. |
| #12 | #11 → `78b26e2d` | 82 | Stacked local UI and offline custody-worker package. Require a separate owner security review before any integration. |
| #13 | `main` → `1938496e` (validated implementation head; audit docs follow as a documentation commit) | 52 | Independent development-tool/release-quality branch. It does not include or replace the `researchwitness.paper_audit` stack. Shared files are primarily README, workflow, packaging, checksums and quality-gate files; reconcile those before integration. |

### Safe integration order for the owner

1. Review #6 against #5 and choose whether #6 replaces #5; only then decide #5's
   disposition.
2. If accepted, integrate the stack in ancestry order: #6, #7, #8, #9, #10, #11,
   then #12. Rebase/retarget each dependent PR only with owner approval, and give
   #12 a distinct custody-worker security review.
3. Review #13 independently, then reconcile overlapping workflow, README,
   packaging, benchmark and release-gate changes. Its source-checkout arithmetic
   tools are separate from the earlier installed/core paper-audit architecture;
   decide whether that split remains intentional before integrating both.

## Files and public evidence decisions

- Keep the dated root campaign report. It remains linked from PR #13, contains
  aggregate development conclusions, and is excluded by the explicit release
  selector. No protected evidence is copied into this audit.
- Keep the PDF tool documented as experimental and unavailable until an operator
  qualifies the image and effective sandbox. The smoke command alone does not
  establish qualification.
- Keep the development research tools outside the installed wheel; README says
  so directly.
- Preserve frozen science/evaluation files and the private custody boundary.

## External owner actions still required

1. Add a professional repository description and topics (suggested values below).
2. Configure a ruleset for `main`: require a pull request, require every Python
   3.11–3.13 × Ubuntu/Windows/macOS check plus the Release gate and CodeQL check,
   prohibit force-push and deletion, and require zero approvals so a solo
   maintainer can merge after checks pass. Verify the effective rule afterward.
3. Review repository Dependabot/security alerts and complete a dependency/license
   advisory check; report the actual result and date.
4. Have a human maintainer review PR #13's full diff and choose a documented
   integration/disposition for PRs #5–#12.

Suggested description: “Open-source, reproducible verification of scientific
claims using deterministic checks and source-grounded evidence.” Suggested
topics: `scientific-computing`, `open-science`, `research-integrity`,
`reproducibility`, `python`.
