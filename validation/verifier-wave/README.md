# Verifier-wave candidate validation

This directory records the unreleased `0.3.0.dev0` integration candidate. It does not change the frozen [`../screening-15.json`](../screening-15.json).

The qualification JSON is an archived verifier-wave baseline from before the broad-review ledger, tabular-summary checker, and paper-audit scanner. It does not qualify the later source tree. Run `python tools/quality_gate.py` against the exact current checkout for its current engineering checks.

## Engineering and security

[`qualification.json`](qualification.json) records the earlier gate run. It covers unit/adversarial tests, 500 seeded synthetic conformance scenarios, three executable historical fixtures, case and intake schema drift, capability-example drift, the frozen-screen review, the source checksum manifest, the trusted-core static scan, two reproducible wheel builds, offline wheel installation, and installed CLI/schema/scaffold/intake smoke checks. The current gate has additional coverage for the later review and screening workflows.

The independent manual red-team report is [`../../docs/ADVERSARIAL_REVIEW_2026-10-05.md`](../../docs/ADVERSARIAL_REVIEW_2026-10-05.md). Its one Low finding against the public `0.2.0` target—multiline intake text reshaping a generated contact draft—is fixed in this candidate and covered by a regression test. The product still has no send or publish command. Source-to-formalization alignment remains a researcher/user responsibility.

## Historical coverage

[`screening-15-review.json`](screening-15-review.json) preserves the input hash and lists all 15 mechanisms. It reports two fully representable, two mechanism-only, one partial, and ten unsupported. This is a capability-fit review, not a 15-case end-to-end discovery run: only two unique screen entries have runnable source fixtures, producing three historical fixture runs. The older K3 network-reliability and QTT-Tucker statements have no runnable fixture or test in this tree and are not fresh reproductions.

No independently curated development corpus or sealed holdout was available. Discovery recall, false-positive rate on new papers, and author-contact false-positive rate remain unmeasured. The candidate is therefore not ready for a public 0.3.0 release.

## Bounded performance

[`performance.json`](performance.json) records three-run medians on Python 3.12.14. Representative results include 19 ms for a graph at 256 vertices/8,192 edges, 6.8 ms for a 256-state PMF with 64 event clauses, 0.05 ms for a 16×16 modular certificate, and 0.9–1.0 s for 1.44 million finite-field points with 4.33 million point-term evaluations. These are local timings, not service guarantees; enforced input/work limits define accepted workload sizes.

The separate public repository audit found CI and CodeQL passing on the live public `main` commit. Branch-protection settings could not be verified anonymously. This candidate has not been pushed or tagged.
