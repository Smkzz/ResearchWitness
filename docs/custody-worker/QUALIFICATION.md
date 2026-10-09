# Custody worker v5 qualification record

**Status: reproducible synthetic development package; not production qualified; not eligible for reserved evidence or Wave 3.**

## Source and versioned contracts

- Starting qualified content: commit `6843593ff443d4a44c48d15a76949b323d0951ca`, tree `e218c518639b614a5bee5850ece62e2cbe6bc745`.
- Worker source package: `0.5.0.dev0`; review contract v5; review-record v4; summary and seal v3; threshold export v2. Historical v1–v4 schemas remain in the branch. The existing v1 owner qualification note is preserved unmodified in the local workspace and excluded from tracked source and package artifacts because it contains custodian operational details.
- V5 requires one exact physical source line, an explicit literal `count` cue immediately before the numerator, no overlap between table-locator and relation-value spans, and complete mapping of numeric characters. Correction old values must be distinct from selected relation values on the mapped statement line.
- V4's uncovered table-number-as-numerator case is covered by a v5 positive-label rejection test. The profile is deliberately narrow; multi-line table/header joins and rows without a literal count field remain unresolved.
- Public negative-document output counts custodian-supplied canonical DOI IDs. It does not resolve DOI aliases and cannot establish 15 independent works by itself.

## Direct checks on this candidate

- `env TMPDIR=/tmp/rw-final-v5-tests python -m unittest tests.test_custody_worker -q`: **48 passed**.
- `env TMPDIR=/tmp/rw-final-v5-tests python -m unittest tests.test_custody_worker tests.test_local_ui -q`: **57 tests, OK; 1 skipped**. The skipped HTTP test reports the sandbox's loopback bind denial. Remaining UI-store lifecycle, cancellation, restart, replay, report truncation and scope-value tests ran offline.
- `python -m py_compile researchwitness/*.py custody_worker/*.py tests/test_local_ui.py tests/test_custody_worker.py tools/qualify_custody_zipapp.py tools/qualify_app_wheel.py`: passed on the committed candidate.
- `node --check researchwitness/webui/app.js`: passed after the UI edits.
- `python -m unittest discover -s tests -q`: **failed to import 19 test modules** because `pytest` is not installed; unittest reported 76 tests and one skipped among importable modules. No dependency was downloaded or installed.
- `python -m pytest --version`: unavailable (`No module named pytest`). The full application suite is not qualified.
- Codex Security's desktop scan could not be started because `start_codex_security_prompt_only_scan` is not exposed by this session. Its desktop workflow requires that start operation; no alternate or headless route was used.
- No real browser, HTTP server, external source, network request, custodian root, reserved identifier, or private label was accessed. Loopback binding was denied with `PermissionError: [Errno 1] Operation not permitted`; the denial was not retried or routed around.

## Reproducible custody package

- `python tools/qualify_custody_zipapp.py` built the v5 zipapp twice from separate clean temporary source copies. Both archives were byte-identical, the allowlisted member set and release manifest hashes were inspected, and the package ran under `python -I -S` through doctor, init, synthetic import, source-bound positive review, verify, seal, and summary. Public export was refused below thresholds as intended.
- Zipapp SHA-256: `665d4d7bd755106db43c562f407e780a2a6520705ecdc970d4c53dd22b334521`.
- `python custody_worker/build_release.py` reproduced the same digest at `custody_worker/dist/rw-custody-0.5.0.dev0.pyz`; its checksum is in `custody_worker/dist/rw-custody-0.5.0.dev0.pyz.sha256`.
- The artifact is source-only, offline and synthetic-tested. It has not been transferred to or installed under the custodian identity. This package evidence does not establish production storage isolation, Windows behavior, or host egress control.

## Reproducible application wheel

- `python tools/qualify_app_wheel.py` created two clean source snapshots from the committed integration branch, built with `--no-index --no-deps --no-build-isolation` and fixed `SOURCE_DATE_EPOCH=1791418753`, and compared the complete wheel bytes.
- Wheel: `researchwitness-0.4.0.dev0-py3-none-any.whl`.
- SHA-256: `f34612a1cfc08c4049380754d34ffe33e77130664fe440e40ddce90abf1c2edd`.
- The qualified wheel is retained locally at `dist/researchwitness-0.4.0.dev0-py3-none-any.whl`.
- Wheel member inspection confirmed the local UI assets are present and test, custody, and validation directories are absent. A clean target install with `--no-index --no-deps` passed a CLI version and packaged-resource smoke check.
- The wheel has not been installed on Windows. This is a Linux packaging check, not a full runtime or browser qualification.

## Limits and open gates

- Hashes bind bytes, not publication authenticity, DOI/work-family identity, version truth, licensing, scope, or correction applicability. Those judgments remain custodian attestations.
- No isolated custodian channel is attached. No current canonical allocation, custody ledger, positive case, or negative relationship was checked. Historical aggregates are not current eligibility evidence.
- No v5 Windows build, effective-access/ACL review, enforced egress check, clean Windows install, hosted CI, CodeQL, or production rehearsal ran on this candidate.
- The local UI did not receive a real-browser inspection. HTTP API origin/token tests are skipped because loopback sockets cannot bind in this execution sandbox.
- No Wave 3 or detector run on a reserved paper occurred.
