# RW-03 follow-up: capture identity and benign-check scope

This is not image/security qualification, a human audit, or escape/exploit testing.
The 32 records comprise effective-config inspection, synthetic benign
success/malformed/timeout/output-overflow fixture runs and cleanup counts,
plus explicitly mocked cleanup-denial regressions. No exploit PDFs or escape
attempts were run. The inspection-only container was never started; benign
extraction containers used the production runner and unchanged flags/defaults.

## Capture identity

Git comparison used commits 947ac3126ebd4867bfa91912dcd047c6a95ef580 and
6a26ab5147c2443b7bff1e8cd5469d1409b43c96. The runner differs, and the harness
is absent in 947ac31. The old isolation log recorded that base HEAD while its
runtime sources were uncommitted; its source hashes identify those bytes.
The smoke and other imported repository modules are identical. The complete
dependency-continuity.json lists old/new hashes or null for absence, including
both sources hashed by the old harness and the smoke/isolation/image summary
receipts. Complete byte identity between those commits is NOT claimed.

New isolation.json/log, isolation-container-inspect.json, smoke.json and
image-inspect.json are alongside, not over, the old receipts. capture.log records
UTC, OS, Python, base HEAD, commands, outputs and exit codes. The source hashes
at merged main and in this recapture are:

| Runtime source | SHA256 |
|---|---|
| tools/__init__.py | `50a6a287fbbf712f17d2e5dd99b49ed2346f90e5dd1b0e97e3c55281f921faf8` |
| tools/offline_files.py | `425e518ba222f06363acf3476c4b03afce3a855b2d0c5796d5cfb15e358f3448` |
| tools/public_discovery.py | `6938feee387756bfa4c000268b784b588e9d0139cd896690080a647ded113e59` |
| tools/pdf_percentage_audit.py | `ebc509b94cd70a6cf1106e158866511c4fd819d5e4c5d7d73b8f202ed9c51f9c` |
| tools/pdf_sandbox_qualify.py | `01217634962dc14a2e4bb1f27ad4edba30507e2c6201a251bcdfc5df5a8c521e` |
| tools/pdf_sandbox_smoke.py | `d90d5cc1706b7ecce05b396accd2b1ff836c7dfebae50b927b4362f47595e9ac` |

The existing local image was inspected first:
`sha256:a526f5d88b02e0af23ae5105d4f14da0f8c664595462afc65cac73b94744c944`,
linux/amd64. Its sole uncompressed layer remains
`sha256:01e8b685061d4cec687b4f451c4e3a2e8299fbcf3e9b8ddd83cd8e6c5f1e9074`.
No pull, apt operation, assembly or new image import was performed.

Isolation exit 0: 32/32 records passed, evidence_recorded_not_qualified.
Smoke exit 0: three fixtures passed, smoke_passed_not_qualified. Both retain
sandbox_qualified=false. Every real fixture had zero ancestor containers before
and after, plus individual CID absence. The 0.5-second timeout includes client
startup, not just parser CPU. Cleanup-denial regressions remain mocked.

## Recipe enforcement

Before invoking Docker, image() now hashes rootfs.tar against ROOTFS_SHA256,
matching the old image-summary.json digest above. Import arguments are unchanged;
#95's pre/post platform checks remain intact. The recipe verifies the hash-locked
InRelease independently using the pinned builder's sqv, --network none,
--pull=never, a read-only metadata mount, --cleartext and --signatures 3.
Successful stdout fingerprints must equal the locked set, itself restricted to
the three recorded fingerprints. Hash, missing/additional signer, verifier or
lock-set errors fail closed before assembly. Apt's fetched InRelease must match
those independently verified bytes by SHA256, binding its existing index/deb checks.

Offline feasibility was checked with the existing builder and committed InRelease,
not a build/download. sqv returned exit 0 and exactly:

```text
04B54C3CDCA79751B16BC6B5225629DF75B188BD
41587F7DB8C774BCCF131416762F67A0B2C39DE4
B8B80B5B623EAB6AD8775C45B7C5D7D6350947F8
```

An initial /dev/null output target failed because sqv refuses existing destinations;
fresh /tmp/authenticated-release inside the throwaway container resolved that
invocation error without weakening verification. Accept/error paths are tested
with mocks; no rebuild was performed. Method docs explicitly name the extracted
dynamic loader --list execution and the builder/host tools that execute.

## Merge receipt and gates

PR #95 head bcdf888c862a74790966555771e6f98faa5b90f4 merged as main
6a26ab5147c2443b7bff1e8cd5469d1409b43c96. Engineering approval:
https://github.com/Smkzz/ResearchWitness/pull/95#pullrequestreview-6009551621.
The coordinator confirmed post-merge main CI 11/11 PASS on 2026-11-22: nine
matrix jobs, Release gate and Analyze Python/CodeQL. This is not independent
image-inventory/evidence security review or Windows residual-risk acceptance.

pdf_execution unqualified; RW-03 blocked_external; custody NOT RUN; scientific
gates unchanged. EUR 0; no new privileges, downloads or egress. The overwritten
historical standalone BuildKit log remains a disclosed gap.
