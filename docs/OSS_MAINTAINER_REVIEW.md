# Maintainer review: integration record and continuing boundaries

**Updated:** 2026-10-16  
**Version:** `0.3.0.dev0` — **UNRELEASED**  
**Review mode:** AI-assisted delegated technical review, explicitly accepted by the owner.

This is not independent human approval or scientific adjudication. The owner
accepted this review modality for the internal Q9 engineering gate. GitHub's
required status checks and all security/custody boundaries remain in place.

## PR #13 is merged

Qualified head `469c3160a4f58402841f60ddb95e28b67800198a` was merged as
`cb0270490a9bf1592a1d194cad395912afcefe9f`, with unchanged tree
`657bc3effdf3d85707565a5cb386389787ac2299`. PR
[#13](https://github.com/Smkzz/ResearchWitness/pull/13) is closed and merged,
not an open draft. Post-merge [CI](https://github.com/Smkzz/ResearchWitness/actions/runs/38900068975)
and [CodeQL](https://github.com/Smkzz/ResearchWitness/actions/runs/38900068843)
passed. See [project status](PROJECT_STATUS.md),
[the final assessment](OSS_QUALITY_FINAL.md) and
[issue #14](https://github.com/Smkzz/ResearchWitness/issues/14).

## Preserved technical-review evidence

The [pre-merge review at its original pinned commit](https://github.com/Smkzz/ResearchWitness/blob/469c3160a4f58402841f60ddb95e28b67800198a/docs/OSS_MAINTAINER_REVIEW.md)
is retained unchanged in Git history. Its original 52-path source review,
Codex Security scan `376df00d-ea30-49cd-b75f-7c37c225defb`, conditional low
Windows ownership finding and successor fixes are historical evidence, not
newly repeated tests in this documentation pass. The
[preserved machine record](../validation/history/OSS_QUALITY_CHECKPOINT-premerge-20261016.json)
retains exact earlier hashes, counts, policy decisions and dependency notices.

The review traced Git-index release inventory, portable path/collision/link
checks, deterministic archive metadata, wheel scope, no-network core behavior,
JATS bounds/anchors/abstentions, PDF isolation requirements and managed discovery.
Ownership could not be verified for Windows managed discovery, so that path
fails closed until a reviewed ACL guard exists. Development input readers reject
hard links before and after opening. The installed core remains supported on
Windows. No claim of real PDF sandbox qualification was made.

Source acquisition stays outside the deterministic verifier. CodeQL, pinned
Actions, least-privilege workflows, nonpersisted checkout credentials and the
separate dependency job support the review, but do not replace inspection of
actual code or establish absence of all unknown vulnerabilities.

## Security and licensing scope

The earlier authenticated GitHub inspection recorded zero open/closed
Dependabot and secret-scanning alerts, no main/PR code-scanning alerts and no
repository advisories. The dated resolved build/dev review queried PyPI/OSV
for 14 distributions and reviewed their actual distributed license/notice text.
Setuptools carries genuine LGPL-3 and MPL-2.0 component notices as well as MIT
package metadata. Those notices are retained in the historical evidence; package
metadata alone does not override vendored terms.

These build/development packages are not bundled into the dependency-free
ResearchWitness runtime wheel. The assessment is not legal approval or an
exhaustive binary-provenance certification. Future dependency resolutions need
fresh checking; zero historical alerts is not a permanently current inventory.

## Remaining PR integration decisions

The graph below describes the review snapshot, not approval to merge every PR.

| PR | Relationship | Disposition |
|---|---|---|
| #5 | Ancestor of #6; its paths persist in the successor | Do not merge separately from its successor; closure still needs a deliberate owner decision. |
| #6 | Main-based installed/core paper-audit foundation | Reconcile with the now-merged #13 baseline, not the old main. |
| #7–#11 | Consecutive stack based on #6 through #10 | Evaluate in ancestry order and rerun full combined-candidate gates. |
| #12 | Based on #11, local UI and offline custody worker | Separate security/authority qualification before integration; no custody grant here. |
| #13 | Independent source tools and OSS quality branch | Merged, with exact post-merge checks above. |

The six shared #6/#13 paths are `CHECKSUMS.sha256`, `CONTRIBUTING.md`, `README.md`,
`SECURITY.md`, `pyproject.toml` and `tools/quality_gate.py`. Resolve them
semantically: retain both relevant test populations, the source-tool/runtime
separation, strict release guards, PDF/custody boundaries and scientific limits.
Regenerate checksums after reconciliation. A conflict-free textual merge is not
qualification of the combined architecture.

Routine dependency-update PRs are separate from the reviewed source changes.
Their mere presence is not a vulnerability, nor permission to skip their checks.

## Ongoing documentation review

Post-merge corrections resolve stale state, setup omissions, checksum steps,
exit-code ambiguity and byte-offset units. Fixed synthetic examples and
version/link/status contracts are tested, without executing arbitrary Markdown
or downloading research documents. New findings must be corrected and the exact
corrective commit checked before claiming current documentation acceptance.

The [initial audit](OSS_QUALITY_AUDIT.md) and scientific-development records remain
historical. No separate human review, release, Wave 3 or real PDF qualification
is implied by this maintenance work.
