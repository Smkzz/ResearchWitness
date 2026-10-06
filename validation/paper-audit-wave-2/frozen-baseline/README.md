# Wave 2 frozen baseline

The detector baseline is the exact wave-1 branch commit `3042b3d62b8f20cc646b0c121dff376bfdd201cb` (tree `a19c53c2c2e6c400ee8b0d7feb0d0261f0cf009f`). The fetched GitHub branch pointed to the same commit and tree. The worktree was clean before freezing.

The new task text supplied `3042b3d62b8f20cc646f0b827315bf3287a09f28`; that string is not a Git object in this repository. The branch and remote ref resolve to the commit recorded above, so no history was rewritten or reconstructed.

The complete offline quality gate passed on Python 3.12.14: 356 tests, 500/500 synthetic conformance cases, 3/3 historical verifier cases, generated-schema and checksum checks, compileall, static checks, clean wheel install and CLI smoke checks. Two wheel builds were byte-identical; SHA-256: `83181729e901c5dc924e03eee4d3f545549f2a3b33766cb825ee139eba263e02`. The paper-audit schema is version 0.2 (`ResearchWitness bounded paper-screening report 0.2`).

GitHub reported no combined commit statuses and no workflow runs for the baseline. The repository workflows run on pushes to `main`, on pull requests, and (for CodeQL) on its weekly schedule; CI also allows manual dispatch. This development branch had no automatic Actions run, so no remote CI result is claimed.

`PAPER_AUDIT_WAVE_2_FREEZE.json` records source and schema hashes, the fixed configuration, the source-only CLI invocation, and the blinding limitation. No detector source, threshold, regex, schema, or filtering rule has changed since the baseline commit.

## Pre-lock format pilot deviation

Before the primary raw-output lock, a separate format-evaluation worker ran the unchanged frozen CLI once on six opaque JATS captures rendered to Markdown. This was an exploratory renderer/extraction pilot, not a comparison between source formats. No same-version PDF captures were available, so a JATS-versus-PDF comparison could not be made. The pilot output is kept outside the repository under `/tmp`, is excluded from all primary metrics, and was not shared with the custodian or the primary evaluator before lock. All six pilot capture hashes match the final 24-source manifest. Those six papers remain in the primary run, so their reports had prior exposure to that worker; this evaluation is therefore blinded within the workflow, not independently concealed.

## Locked wave-2 result

The unchanged detector's 24-paper, two-pass run is locked at commit
`4659ddd2335595ab77f96949469318f8c50f021b`. Its exact scoring inputs and
aggregate metrics are in `EVIDENCE_HASHES.json` and `SCORING_SUMMARY.json`.
The custodian serialized structured supportability labels and target arrays
after lock; there was no pre-run artifact or hash. Treat positive issue
eligibility and sensitivity as exploratory. See `POST_LOCK_FAILURE_ANALYSIS.md`
for the adjudicated results and failure classes.

After the lock, the format evaluator compared five legally accessible,
same-record publisher PDFs with their JATS-derived Markdown sources. Results
are in `SOURCE_FORMAT_SUMMARY.json` and excluded from primary metrics. The
candidate differences mix PDF extraction with the frozen detector's
Markdown-only table coverage, so they do not isolate parser effects.

Post-lock detector changes and the separate wave-1 development replay are
documented in [`../POST_LOCK_DEVELOPMENT.md`](../POST_LOCK_DEVELOPMENT.md).
