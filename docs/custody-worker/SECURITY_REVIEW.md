# ResearchWitness security review — 2026-10-10

This is a scoped, threat-model-driven engineering review, not a full repository audit or a Codex Security scan.

## Scope and findings

- Read-only reviews covered changed JATS parsing/offset mapping, count and percentage detectors, structured arithmetic, the local UI's history and duplicate flows, custody-worker v5 validation changes, and related tests.
- Review found Unicode no-break spaces in count ranges could be misread or omitted from coverage. The scanner now accounts for common nonbreaking-space ranges/fractions as unsupported and marks coverage incomplete.
- Review found US and UK `standardize/standardise` verb forms missing from scope cues. The relevant detectors now recognize those forms.
- Review found fullwidth slash and ranges in JATS ratio-like cells could disappear from relation accounting. The broad shape scanner now records them as skipped/unsupported while the exact arithmetic grammar remains narrow.
- Earlier changed-code reviews found imprecise source-byte wording and a stale duplicate notice on history selection. The UI uses generic source-byte ranges and clears the stale notice on history/replay transitions.
- No concrete injection, path traversal, external-entity fetch, or unbounded-regex defect was reported in those changed-code review scopes. The review did not establish that unchanged HTTP authorization, persistence, export, or every operator path is clear.

## Outstanding limits

- The current environment does not expose a Codex Security scan-start operation. CodeQL is not a complete security certification.
- The local interface is loopback-only but is not an operating-system custody boundary. Another local process that can reach it may use the interface and its data.
- No isolated custodian execution environment was available to this task. Separation of duties, effective-access controls, retention/output handling, and independent outbound policy remain unqualified.
- The v5 worker contains no network client. That does not enforce host egress. No protected installation, migration, or rollback was performed.
- No research source or reserved evidence entered the development environment. No additional spending occurred.

Keep PR #12 draft and unreleased until exact-source hosted checks, human product review, custody separation, and scientific eligibility gates pass.
