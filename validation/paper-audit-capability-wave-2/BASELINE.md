# Paper-audit capability wave 2 baseline

**Baseline verification date:** 2026-10-06
**New development branch:** `codex/paper-audit-capability-wave-2`
**PR #6:** `https://github.com/Smkzz/ResearchWitness/pull/6`

## Canonical remote state

- PR #6 head commit: `94cd15859ec37a965db5f0a2f6dc7ebf620f56c5`
- PR #6 tree: `de5b083c1afc455750a3efb5898ee7ec110b13aa`
- PR state: open, draft, unmerged, mergeable.
- GitHub CI run `37411247630`: completed successfully.
- GitHub CodeQL run `37411247650`: completed successfully.

The GitHub API confirmed the PR metadata, workflow runs, commit SHA, and tree. A shell `git fetch --all --prune` could not connect through the configured proxy, so this baseline uses the connected GitHub API for remote verification.

## Local state before development changes

- Local qualified commit: `5b4ddbedc75efe35e0dacca620ee049b58902c48`
- Local tree: `de5b083c1afc455750a3efb5898ee7ec110b13aa`
- Local tree matches the canonical PR #6 tree exactly.
- New branch was created from the qualified local commit; PR #6's branch and files were not changed.
- Worktree was clean at branch creation.

## Baseline quality gate

The primary workspace Python did not include `pytest`. The full gate was run successfully using Python 3.12.14 in `/tmp/rw-capability-wave2-venv`, with `pytest 9.1.1` installed there; no dependency or repository files were changed to set up the runner.

- Pytest: 410 passed.
- Synthetic conformance: 500/500.
- Historical deterministic verifier cases: 3/3.
- Trusted-core static scan, source checksums, generated-schema checks, capability examples, frozen-screen review, and compileall: PASS.
- Two reproducible wheel builds, clean installation, and CLI smoke checks: PASS.
- Baseline wheel SHA-256: `b571415d7b98de5d9d942a05a83dea432408856f0b9a5c5a2c8c75361e1fff4d`.

This is the pre-change local baseline, separate from GitHub CI.
