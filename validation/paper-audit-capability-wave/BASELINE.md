# Capability wave baseline

Captured 2026-10-06 before implementation on `codex/paper-audit-capability-wave`.

## Repository state

- Starting commit: `8d91362437223c85c700fec92f857ef90e883d15` (`Fail closed on ambiguous paper tables`).
- Starting tree: `3c2d531b99176245ea9ac609e15d274ce12533b8`.
- Requested base branch: `codex/paper-audit-wave-2`.
- PR #5: open draft, base `main` at `65c814c02ec3e3b8f427ad095986a258470b8f80`, head `8d91362437223c85c700fec92f857ef90e883d15`.
- GitHub's commit API reports tree `3c2d531b99176245ea9ac609e15d274ce12533b8`, equal to the local tree. The connected GitHub branch search resolves `codex/paper-audit-wave-2`; the PR head and local branch both resolve to the requested commit.
- The initial worktree was clean. `git fetch --all --prune` could not reach GitHub because the environment proxy refused the connection; remote verification used the connected GitHub API instead.
- The working branch was created locally from the exact starting commit. No wave-2 output was rerun or modified.

## Baseline quality gate

`.venv/bin/python tools/quality_gate.py` passed on the starting commit with Python 3.12.14:

- 363 tests passed.
- 500/500 synthetic conformance cases and 3/3 historical verifier cases matched.
- Static security scan, source checksums, schemas, capability examples, frozen-screen review, and compilation passed.
- Two wheel builds were reproducible (SHA-256 `3a6c74162f39f2b1ff1ffba3639344431fef893c1bd9902eaf994fa21bc0d494`); clean-install and CLI smoke checks passed.

## PR #5 Actions observation

- Both workflow files at the branch head contain `pull_request` triggers. The connected GitHub API exposes their raw contents.
- The PR head SHA has no Actions workflow runs or check runs; commit status is `pending` with zero status entries. GitHub's pull-request merge ref `refs/pull/5/merge` returns 404.
- Repository-wide Actions run listing filtered to `event=pull_request` returned runs for other heads, so pull-request workflows have run in this repository; that does not prove the settings state at PR #5 creation time.
- The connected GitHub API wrapper rejected the Actions settings and workflow-metadata endpoints as unavailable through its endpoint allowlist. The Git remote is unreachable from this environment.

### Diagnosis update

GitHub reports `mergeable=false` and `mergeable_state=dirty` for PR #5, indicating a merge conflict with the base branch. GitHub's [Actions troubleshooting guidance](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows) says `pull_request` workflows do not run while a PR has a merge conflict. Successful CI and CodeQL `pull_request` runs exist for PR #4, and both workflows are present on `main` and the PR head. This is the best-supported explanation for the missing runs. The connected API cannot read Actions settings or workflow activation metadata, so a simultaneous settings or policy change cannot be ruled out conclusively.

The current PR check suites named `cursor` and `devin-ai-integration` are integration-app queues with no workflow check runs; they are not Actions runs. The PR was opened through the connected GitHub App path, but the evidence points to the merge conflict and does not establish that the creation path suppressed an event.

No CI configuration has been changed to manufacture a check result.
