# Custody worker v5 deployment boundary

**No v5 production deployment has occurred.** This integration session has no technically isolated custodian execution channel. No real paper, correction, reserved identifier, or private label was imported or reviewed.

## Current candidate

- Source package version: `0.5.0.dev0`.
- Review v5; review record v4; summary and seal v3; public summary/export v2.
- Runtime uses Python's standard library and offline zipapp format.
- Checked-in rehearsal inputs are synthetic only.
- Production root, identity, installed v1 package, records, and ACLs were not accessed by this development session.
- No v5 package has been installed; its local synthetic build qualification is recorded in `QUALIFICATION.md`.

The prior 0.1.0.dev0 installation and its private records are historical custody assets. This candidate has no migration or compatibility path. Preserve them unchanged.

## Owner-controlled gate before reserved use

A custodian owner must attach one separate execution route that:

1. Runs under the existing custodian identity and keeps development agents unable to read the worker, source evidence, temporary files, logs, backups, and outputs.
2. Verifies owner, SID, effective access, inheritance, reparse points, and hard links for the store and installed code; then uses trusted identity-specific checks to verify ordinary developer and other service denial.
3. Enforces outbound access independently at the process/host boundary to exactly `api.crossref.org`, `www.ebi.ac.uk`, `eutils.ncbi.nlm.nih.gov`, and `pmc.ncbi.nlm.nih.gov`, with TLS, redirect, response-size, decompression, pacing, and retry controls. The development environment is not an approved source route.
4. Preserves the existing canonical allocation, eligibility rules, exclusion set, and custody records; does not run ResearchWitness on reserved papers before the frozen Wave 3 authorization point.
5. Reviews and transfers the exact hash-pinned v5 artifact through an owner-controlled path, performs the synthetic rehearsal under the custodian identity, and retains the raw owner-side verification record.
6. Reconciles DOI aliases/work-family identity with independent custodian adjudication before counting distinct negative papers. The worker's DOI-ID aggregate is not that evidence.

The worker does not create accounts, change ACLs, retrieve sources, contact publishers, invoke detectors, or configure network policy. Do not bypass a failed gate or repeat denied account-switch workarounds.

## Synthetic rehearsal

The synthetic suite covers initialization, source import, exact-line source binding, correction mapping, verification, sealing, threshold export refusal, source tamper checks, restart/retry/delete, and public-export locking mechanics. It is not a production identity, ACL, egress, Windows, public browser, or custody-isolation test. Typical multi-line table header joins remain unsupported by v5.

Do not execute production doctor or point a development session at the existing private store. A separate owner-controlled Windows custodian route is required for those operations.
