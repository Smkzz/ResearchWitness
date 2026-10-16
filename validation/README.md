# Validation assets and current evidence

For current capabilities and merge state, start with
[project status](../docs/PROJECT_STATUS.md),
[the OSS assessment](../docs/OSS_QUALITY_FINAL.md) and
[the machine-readable checkpoint](OSS_QUALITY_CHECKPOINT.json).
Internal software quality, historical replay and independent scientific
performance are distinct forms of evidence.

## Engineering and documentation

CI evaluates the exact source revision, supported Python/OS matrix, static checks,
core coverage, source manifests, deterministic artifacts and clean installation.
Documentation tests exercise fixed synthetic commands, expected result states,
source hashes/anchors, setup prerequisites and maintained links. They do not
execute arbitrary Markdown or establish scientific findings.

The current checkpoint identifies the integrated baseline and links its original
pre-merge evidence under [history](history/). Snapshot counts and versions are
not silently reused as results for later commits. Exact new validation belongs
to the respective PR/main check runs.

## Historical scientific material

- [MVP replay runner](mvp_real/run_validation.py): three historical executable
  development cases, not three untouched discoveries.
- [Frozen 15-case screen](screening-15.json): a mechanism/coverage map, not a
  complete end-to-end discovery benchmark.
- [Verifier-wave records](verifier-wave/README.md): preserved dated results;
  do not reuse their old test count or wheel hash as a current build result.
- [2026-10-14 readiness assessment](SCIENTIFIC_EVALUATION_READINESS.md): historical
  repository and source-access state, not a current software-quality score.
- [2026-10-15 development experiment aggregate](development-percentage-campaign-20261015.json):
  developer-exposed v1/v2 evidence with its original limitations and commitments.
- [Campaign report](../RESEARCHWITNESS_NEXT_CAMPAIGN_REPORT.md): dated investigation
  history, preserved rather than rewritten to imply success or independence.

No protected-custody source, reserved evaluation identifier or private author
correspondence belongs here. Synthetic fixtures are labeled. The installed
verifier does not authenticate a publication's origin; source hashes establish
byte integrity, not truth. Scientific Wave 3 remains separate and has not run.
