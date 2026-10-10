# ResearchWitness engineering evidence ledger

Updated 2026-10-10. This public ledger contains aggregate engineering evidence only. It does not contain reserved case identities, source text, labels, correction targets, or private custody records.

## Qualified engineering revision

- Tested source revision: `94359db21d49e134dfe7301238f83d3faf647018`; tree: `49f1b1e6b38d32e3d57d790f372972fbc981255c`.
- PR #12 is open and draft. It is unmerged and unreleased. PR #11 remains an open, draft dependency.
- [CI run 38090558028](https://github.com/Smkzz/ResearchWitness/actions/runs/38090558028) completed successfully on the tested source revision. [CodeQL run 38090558041](https://github.com/Smkzz/ResearchWitness/actions/runs/38090558041) completed successfully; this is static-analysis workflow evidence, not a security certification.
- Python 3.11, 3.12, and 3.13 each reported 837 passed, 7 skipped, and 4 subtests passed. Synthetic conformance matched 500/500 generated cases. Historical MVP fixtures matched 3/3; these fixtures do not qualify an unseen scientific evaluation.
- The Windows synthetic custody-worker job passed 57 tests. Linux and Windows synthetic browser jobs each passed 6 tests.
- Browser coverage includes the upload-to-report journey, keyboard focus checks, reduced-motion behavior, accessible history names, local export/delete flows, and mobile overflow checks. Fresh desktop and mobile captures were inspected on both operating systems. Human visual and assistive-technology review remains pending.
- Two clean application-wheel builds were byte-identical; clean installation and CLI/resource smoke checks passed.

## Artifact integrity

- Application wheel, version `0.4.0.dev0`: SHA-256 `dacb05f10b66644f25eb71d5d2bc36a4087075a0e985272fb6b0d4f54222098e`.
- Synthetic custody-worker zipapp, version `0.5.0.dev0`: SHA-256 `25b4802c1636fdbe2bd2185eeb2179a38d7fc80b2c4cc56e82d3ca91d913c9d2`.
- Linux browser-screenshot artifact (ID `11683093229`): SHA-256 `0f87c24b93aa91708d40e72ea025414d4659aa7d8fbb418dea9f11a4865ff11e`.
- Windows browser-screenshot artifact (ID `11682854591`): SHA-256 `09aaf2a32cbcec602c1a0a26a4ba5ae1344e35eadac18729034ee1905f434b60`.
- The screenshot artifact digests were verified against the downloaded archive bytes. These development-version and synthetic artifacts remain unpublished.

## Ten-category acceptance matrix

Statuses describe the tested development scope. A PASS does not extend beyond the evidence stated.

1. **Product usefulness — PASS (engineering scope).** The local-first interface supports the tested upload, source-mapped review, export, replay, retry, cancellation, and local deletion workflows. Candidate output is presented as requiring human review.
2. **Scientific correctness — FAIL (evaluation eligibility).** No untouched, eligible correction-backed positive is confirmed. The evidence does not establish at least 50 source-verified correct negative relationships across 15 independent works. Wave 3 was not run.
3. **Security — BLOCKED.** CI and CodeQL passed, but neither is a complete security review. Confidential incident disposition and independent security review remain pending; no Codex Security scan execution route was available.
4. **Privacy — BLOCKED.** Automated local-interface privacy and data-handling checks passed in synthetic tests, but protected custodian isolation and the end-to-end custody boundary have not been independently verified.
5. **UX and accessibility — BLOCKED.** Automated keyboard, semantic, reduced-motion, Linux, and Windows browser checks passed. Independent human visual and screen-reader review remains pending; no WCAG conformance claim is made.
6. **Reliability — PASS (synthetic engineering scope).** The hosted Python matrix, Windows synthetic-worker tests, and Linux/Windows browser acceptance jobs passed. This does not qualify protected production custody.
7. **Performance and cost — NOT_CLAIMED.** Production workload performance has not been measured. Additional spending: EUR 0.
8. **Installation and portability — BLOCKED.** The development application wheel builds reproducibly and passes a clean-install smoke test. Custody-worker v5 has not been installed or rollback-tested in the protected Windows store.
9. **Maintainability and reproducibility — PASS (tested scope).** Source checksum checks passed; two clean application-wheel builds were byte-identical.
10. **Documentation and release quality — BLOCKED.** This candidate remains draft and unreleased. Scientific, custody, security-disposition, and human accessibility gates are still open.

## Evaluation and release boundary

The historical negative aggregate is not proof of 15 independent works or of 50 exact, source-verified correct relationships. No reserved evaluation paper was processed by the development runner. No Wave 3 run, merge, tag, or release occurred. Repository releases remain empty. Total additional spend: EUR 0.
