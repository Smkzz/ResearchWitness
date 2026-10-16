# Delegated OSS maintainer review and integration decision

Date: 2026-10-16. Reviewer: Codex, acting as an **AI-assisted delegated reviewer**.
This is not an independent human approval, release authorization or scientific evaluation.

**2026-10-16 owner acceptance addendum:** The project owner explicitly
accepted the disclosed AI-assisted technical quality review in place of
a second human review for the internal OSS 10/10 Q9 criterion. The
previous human-review gate described below is superseded **only for this
internal criterion**. It does not imply a second independent reviewer,
authorize merging or releasing, or qualify scientific performance.
The reviewed prior final PR head was
`36edc7f824718c36546c1a53570ab81270fca131`; its CI, CodeQL and
dependency-evidence runs passed. See [issue #14](https://github.com/Smkzz/ResearchWitness/issues/14)
for post-documentation exact-head evidence.

PR [#13](https://github.com/Smkzz/ResearchWitness/pull/13) remains draft and unmerged.

## Source identity and technical decision

The original review covers all 52 changed paths from main
`65c814c02ec3e3b8f427ad095986a258470b8f80` to
`10233a8fa05a98aa77931be631fc07d40357836a`, tree
`ec55280925f84ee063e6e0f1a0674356e5bc0460`.
Authenticated file reads were independently checked against Git blob and recursive
tree hashes. The local review mirror uses explicitly synthetic commit identities;
it preserves those exact source trees and does not reconstruct remote signatures.
Codex Security scan `376df00d-ea30-49cd-b75f-7c37c225defb` completed and sealed
52 reviewed surfaces, two candidate dispositions and one conditional low finding.

The successor implementation is
`93efdf4cdf20085a7fd914d3ce647c646ab6fe0a`, tree
`fc38026bb2ce5e6b8cb5fea0d301b5b60f3a68a5`. Changed portions received a separate
AI source review after fixes. The technical decision is to retain this candidate
for separately owner-authorized integration after all applicable checks pass.
The owner accepts this labeled AI-assisted technical review for Q9. No unresolved source-level finding remains within the reviewed scope.

| Surface | Review outcome |
|---|---|
| Release inventory and source ZIP | Git-index allowlist, unstaged-file rejection, mode/link checks, portable path validation, collision checks and deterministic ZIP metadata were traced. Untracked files, caches and private task output are excluded. |
| Wheel and offline installation | Two wheel builds are compared; wheel contents exclude development artifacts; installation uses `--no-index --no-deps`. Build/dev dependencies are not runtime wheel contents. |
| Trusted verifier logic | `arithmetic.py` removes an unused import; `checkers.py` retains modulus validation while removing an unused assignment. Neither change alters checker semantics. |
| JATS/PDF | Parser bounds, DTD/entity rejection, source anchors and abstentions were inspected. PDF extraction remains unavailable pending real image/runtime qualification. Synthetic tests do not qualify Docker, Poppler or a kernel boundary. |
| Discovery | Exact HTTPS hosts, managed proxy, same-host redirects, response limits, explicit failure states and shared timing were traced. Windows ownership verification was missing; managed discovery now fails before filesystem/network access where ownership cannot be verified. The installed core remains supported on Windows. |
| Evidence files | Development readers now reject hard links both before and after opening the descriptor. The original hard-link security candidate was suppressed because no new read authority was established under the trusted local-directory model; the successor nevertheless tightens input validation. |
| CI and dependency evidence | Actions are SHA-pinned, checkout credentials are not persisted, and ordinary PR jobs have `contents: read`. CodeQL alone needs `security-events: write`. No `pull_request_target`, secrets-bearing privileged PR execution, unpinned action or automatic merge/release was found. |
| Documentation and tests | Actual diffs and supporting regression tests were inspected. The v1/v2 annotation documentation was corrected. Scope, scientific abstentions and public/private boundaries remain explicit. |

## GitHub administration verified

Description: **Open-source scientific claim verification with deterministic checks and reproducible evidence.**

Topics: `scientific-computing`, `open-science`, `research-integrity`, `reproducibility`, `python`.
Both were saved and checked on a fresh authenticated repository page.

[Ruleset 25233301](https://github.com/Smkzz/ResearchWitness/rules/25233301)
(`main-quality-gates`) is active and its public effective view matches `main`.
The branch API reports `protected: true`. PRs are required, force pushes and
deletion are prohibited, the branch must be up to date, approval count is zero,
and the bypass list is empty. All required checks are bound to GitHub Actions
(integration ID 15368):

- `Python 3.11 / ubuntu-latest`
- `Python 3.12 / ubuntu-latest`
- `Python 3.13 / ubuntu-latest`
- `Python 3.11 / windows-latest`
- `Python 3.12 / windows-latest`
- `Python 3.13 / windows-latest`
- `Python 3.11 / macos-latest`
- `Python 3.12 / macos-latest`
- `Python 3.13 / macos-latest`
- `Release gate`
- `Analyze Python`

These are real PR-triggered jobs. Zero required approvals leaves the solo
maintainer workflow usable after checks. The repository owner expressly
replaced the separate human-review requirement with the documented AI-assisted
assessment for Q9. No destructive push/delete test was performed against `main`.

## Security and distribution review

Authenticated GitHub Security views showed 0 open / 0 closed Dependabot alerts,
0 open / 0 closed secret alerts, 0 main code-scanning alerts and 0 PR #13
code-scanning alerts. Advisory state counts were 0 triage, 0 draft, 0 published
and 0 closed. These are observed view counts, not an inference from green CI.
Dependency graph, Dependabot alerts, security-fix PRs, package malware monitoring
and private vulnerability reporting are enabled. Automatic development-alert
dismissal was disabled; no alert was dismissed to obtain this result. Secret
scanning and push protection remain enabled. Paid agentic autofix was not enabled.

GitHub's graph is a **default-main snapshot**, checked at `65c814c`: eight entries
(three Python declarations and five Action references), with no resolved PR #13
transitive graph. The separate hosted dependency job provides the resolved graph
used for this review; the main graph is not presented as that evidence.

[Dependency evidence run 38891822570](https://github.com/Smkzz/ResearchWitness/actions/runs/38891822570)
ran in a clean Python 3.12 virtual environment at `93efdf4`. At
`2026-10-16T11:08:55.623601+00:00`, all 14 installed build/dev distributions
returned **0 PyPI and OSV advisories**, with no query errors. OSV pagination and
malformed/error responses are checked; unavailable data fails the audit.
The runner package manager pip is recorded separately and is not a project
dependency. This is a dated database observation, not a promise of future safety.

| Distribution | Resolved version | Observed package/distribution terms |
|---|---|---|
| pytest | 9.1.1 | MIT |
| jsonschema | 4.26.0 | MIT |
| coverage | 7.16.2 | Apache-2.0 and notice |
| ruff | 0.14.14 | MIT plus embedded third-party notices |
| attrs | 26.1.0 | MIT |
| iniconfig | 2.3.1 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause; inline MIT attribution |
| pluggy | 1.7.0 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause and authors attribution |
| referencing | 0.37.0 | MIT |
| rpds-py | 2026.9.1 | MIT |
| typing_extensions | 4.16.0 | PSF/Python license history |
| setuptools | 84.0.0 | MIT package; vendored terms include LGPL-3, MPL-2.0, Apache/BSD/MIT and Zero-Clause BSD |

The distribution review read 39 package-scoped captured files, 33 unique hashes,
360,200 bytes, with every digest verified. The broad capture also includes four
bytecode files and SPDX identifier data: their GPL/AGPL strings are not evidence
that those packages are GPL licensed. Actual notices and license-bearing source
were reviewed separately. Setuptools includes a real LGPL-3 license and a real
MPL-2.0 `validate-pyproject` notice. They must not be erased by its MIT metadata.

ResearchWitness declares no runtime dependencies and does not bundle these
development/build distributions in its source release or installed wheel.
No runtime license blocker was found in this snapshot. Retain upstream license,
attribution and source obligations if redistributing the build toolchain itself.
This engineering review is not legal approval or exhaustive binary provenance
certification. Existing version ranges are retained: this resolved environment
is reviewed; other allowed or future versions require a fresh advisory/license
check. No runtime dependency or paid service was added.

The evidence artifact is
[12041589008](https://github.com/Smkzz/ResearchWitness/actions/runs/38891822570/artifacts/12041589008),
SHA-256 `0291b31e0fe66672cdc21f3b0e7e1583fb5107675e972cc2b8d4c9ea74bbf36a`.
It expires on 2026-11-15. Exact public license bytes and hashes are also retained
in the job log. The browser's artifact download was blocked by its client;
that control was not overridden. Authorized GitHub job logs supplied the evidence.

## PR #5–#12 integration disposition

Live PR identities were re-read. Every PR remains open, draft and unmerged.

| PR | Exact head | Dependency and disposition |
|---|---|---|
| #5 | `8d91362437223c85c700fec92f857ef90e883d15` | Ancestor of #6; compare is ahead-only, with two later commits and no behind commits. All 222 changed paths are in #6. All 345 tracked blobs remain present: 335 identical, ten evolved. Treat #6 as its successor; keep #5 open until a separate owner-approved final disposition. |
| #6 | `94cd15859ec37a965db5f0a2f6dc7ebf620f56c5` | Main-based installed/core paper-audit/JATS foundation; parent of #7. |
| #7 | `57fedcd9efa9afaabd76bc56b1bc06f1063354fe` | Based exactly on #6; source-mapped capability expansion. |
| #8 | `80f1ee0189a2618377239702046160d7d0208f34` | Based exactly on #7; source/evidence follow-up. |
| #9 | `5a50406e4b7662aa9520142d10b9c5d3527bbe65` | Based exactly on #8; correction-evidence maturation. |
| #10 | `f2490bd55568915c501b3c81d1ae3d08fda18cad` | Based exactly on #9; v1.2 count/percentage qualification. |
| #11 | `6843593ff443d4a44c48d15a76949b323d0951ca` | Based exactly on #10; v1.3 denominator provenance. |
| #12 | `78b26e2d9a31a1eafcc9a0f668b19f09283ce5e9` | Based exactly on #11; local UI and offline custody worker. Distinct security/authority review required before integration; this assignment does not approve that worker. |

Recommended eventual order: integrate AI-reviewed #13 only with separate owner
merge authorization; after its acceptance, reconcile #6 against that accepted baseline, then integrate #6–#11
in ancestry order. Review #12 separately before any integration. Do not merge #5
in addition to its successor. No retarget, rebase, closure or merge is performed
by this decision.

The six overlapping #6/#13 files are `CHECKSUMS.sha256`, `CONTRIBUTING.md`,
`README.md`, `SECURITY.md`, `pyproject.toml` and `tools/quality_gate.py`.
Resolve them semantically: retain both required test populations and strict
coverage/release guards; preserve runtime-vs-source-tool separation; preserve
PDF/custody fail-closed gates and scientific qualification limits; regenerate
checksums only after the combined candidate is frozen. A textual conflict
resolution or cherry-pick is not integration qualification. Re-run the complete
combined candidate gates after reconciliation. PR #13 does not replace the
installed `researchwitness.paper_audit` architecture in #6–#12.

## Owner acceptance and continuing boundaries

The repository owner has explicitly accepted this AI-assisted technical
quality review as sufficient for the internal 10/10 engineering standard.
Q9 therefore passes: the repository governance checks are enforced and
review modality is accepted. This is **not independent human approval**,
outside certification or permission to merge/release. The final exact-head
checks and closure decision are recorded in [issue #14](https://github.com/Smkzz/ResearchWitness/issues/14).

PR #13 remains draft and unmerged. PR #12 custody-worker security, real
PDF isolation, protected scientific evaluation and Wave 3 remain separate
and unqualified where previously documented.
