## Work package and purpose

Plan/package ID (or scoped maintenance reason), baseline SHA, actual problem and
acceptance criterion. Start with AGENTS.md; distinguish implemented behavior from
planned behavior. Ordinary qualified merges do not require routine human approval.

## Changes and compatibility

Describe changed interfaces, proof scope, preserved safeguards and affected docs.
For regressions explain how the test fails without the fix. Do not rewrite frozen
scientific records; append new evidence with its own identity.

## Verification receipt

Record exact commands/check URLs, revision, outcome and skips/limits (not just ticks).

- [ ] Focused regressions and applicable documentation/agent-plan tests.
- [ ] Ruff; pytest/coverage with the unchanged verifier-core floor.
- [ ] Synthetic conformance and historical MVP replay.
- [ ] Regenerated source checksums and applicable quality/reproducible-build gate.
- [ ] Exact-head required CI, CodeQL and Dependency evidence inspected.
- [ ] Separate AI review recorded, or its absence honestly stated.
- [ ] Post-merge main checks will be recorded before claiming integration qualified.

## Safety, evidence and cost

- [ ] No model judgment becomes a trusted proof primitive; claims remain narrow.
- [ ] Resource limits, source provenance and unsupported cases remain explicit.
- [ ] No private sources, credentials, correspondence or protected labels are exposed.
- [ ] No new spending or safety-sensitive authority is silently introduced.
- [ ] Current docs/task receipt are updated; frozen evidence is preserved.

## Handoff

Acceptance evidence, unresolved blockers, scope left disabled and next eligible
package. Do not ask for routine permission to continue; escalate only an actual
safety/cost decision and continue other independent safe work.
