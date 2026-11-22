# PDF execution boundary and outstanding qualification

**Observed state:** UNQUALIFIED; synthetic candidate-image evidence is recorded,
but real-document use remains disabled pending separate review and risk acceptance.
**Plan owner:** RW-03 in [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md).

Poppler is a native parser for attacker-controlled complex input. Malformed PDFs
may exploit defects, consume resources or emit adversarial instructions. Arithmetic
checks and pinned image IDs do not remove these risks. The Docker daemon and host
kernel remain trusted; this is process isolation, not a cryptographic/VM boundary.

The existing runner uses the local Unix socket on POSIX or the Docker Desktop
named pipe `npipe:////./pipe/docker_engine` on Windows, a fresh Docker configuration,
no network/source-directory mount, read-only root, UID/GID 65534, dropped capabilities,
verified default seccomp, no-new-privileges, and CPU/memory/PID/file/output/time bounds.
It sends input over stdin and fails closed if cleanup is not confirmed. It cannot
authenticate a builder or inspect hidden image files. Review the rootfs, not only
its empty environment settings. No host Poppler fallback is permitted.

Unlike the root-owned `/var/run/docker.sock`, the Windows pipe name
`\\.\pipe\docker_engine` can be created by any local process when Docker Desktop
is not listening. Before any Docker invocation on Windows, the runner opens this
pipe, queries `GetNamedPipeServerProcessId`, and inspects the server process token
and image path. It requires the current process user SID or LocalSystem
(`S-1-5-18`) and a resolved image path under the known Program Files folder's
`Docker\` subtree, compared case-insensitively. `SHGetKnownFolderPath` supplies
the folder instead of the environment. The executable must pass an offline,
**name-based** Authenticode signature check with `WinVerifyTrust`: its leaf signer
certificate's simple display name must equal `Docker Inc`. No issuer restriction,
chain-root pin or certificate-fingerprint check is applied. Any otherwise valid
signature whose certificate chains to a trusted root with that subject name would
pass this signer check; name-only matching remains a residual risk. Verification disables
UI and revocation checks and uses cache-only URL retrieval: no network access.
Trust state is always closed and known-folder memory freed; API and cleanup
failures block execution. Offline-only revocation means a revoked certificate
is not detected; the entire installation's integrity is not verified.
A check-then-use race remains because
the Docker CLI opens a separate connection after the check; an administrator or
same-user attacker is not defended against. These remain qualification limitations,
and `pdf_execution` stays unqualified: candidate-image evidence is not a separate
security review or acceptance of these residual risks.
The authority
for native RW-03 qualification runs on the org Windows Devin machine is Sami's
answer to the "Use a Windows machine" card, **2026-11-21 19:59 UTC**. That
authorization is not pipe-server authentication or a waiver of qualification.

## Native transport evidence - not isolation qualification

Raw evidence captured on 2026-11-21 at PR #87 head
`f7e17793abe151f5b7bcd68a3d5bfa11419528b6` is archived under
[`evidence/rw03-native-2026-11-21/`](../evidence/rw03-native-2026-11-21/):
[focused tests](../evidence/rw03-native-2026-11-21/pdf-focused.log),
[runtime commands](../evidence/rw03-native-2026-11-21/pdf-runtime.log),
[release sequence](../evidence/rw03-native-2026-11-21/pdf-release.log),
[smoke result](../evidence/rw03-native-2026-11-21/pdf-smoke.json), and the
[capture script](../evidence/rw03-native-2026-11-21/capture.py).
The script records the original machine paths and also includes the separate
Windows metadata capture procedure; it is an execution record, not a portable
qualification harness. Logs retain their output text and branch-head IDs, with
line endings normalized to LF for the repository's checksum convention.
The smoke used a nonexistent image digest and failed closed at image verification;
it did not run Poppler or qualify PDF isolation. No containers remained; the image
inventory contained only a pre-existing `hello-world` image. No image was pulled.

## Minimal rootfs construction requirements

Use an already authorized build machine and managed daemon. Record OS/architecture,
package-repository snapshot and signed metadata, exact packages/hashes, builder
image digest, build script and source materials. Do not rely on floating `latest`.
Extract reviewed distribution packages into a fresh rootfs containing `pdftotext`,
its dynamic loader/library closure and necessary Poppler/font data only. Do not
copy home directories, development images, credentials, Docker/proxy configuration,
package caches, documents, shells or network clients. Verify symlink targets and
runtime resources against package manifests. Independently inspect a sorted hashed
file inventory, licenses and known-vulnerability information.

Use only that reviewed rootfs in the build context:

```dockerfile
FROM scratch
COPY rootfs/ /
```

Build offline without ENV, ENTRYPOINT, VOLUME or secrets. Record the local image ID,
exported archive hash, layer/rootfs inventory and build log. The runner requires
empty image configuration. On the recorded daemon both BuildKit and the classic
builder inject PATH even with the illustrative Dockerfile above. The implemented
[locked recipe](../tools/pdf_sandbox_image/README.md) therefore uses local offline
`docker import rootfs.tar`, with no `--change` flags. Do not substitute a broad
development container or relax the runner's configuration checks.

## Candidate-image provenance and native evidence - 2026-11-22

Sami's bounded download approval was relayed by the coordinator on **2026-11-22**:
Docker Hub (`registry-1.docker.io`, `auth.docker.io` and its observed blob CDN) and
`snapshot.debian.org` only; EUR 0, no new privileges, custody NOT RUN. A subsequent
explicit decision authorized HTTP snapshot transport inside the slim builder after
HTTPS trust verification failed. Archive integrity relies on the pinned builder's
Debian archive-keyring OpenPGP verification, then signed index/package SHA256,
not TLS. No signature or hash check was disabled.

The candidate is bound to these exact identities, not a mutable tag:

| Material | Recorded identity |
|---|---|
| Builder tag/platform | `debian:trixie-slim`, linux/amd64 |
| Builder manifest pin | `debian@sha256:7378260c0a098d27ac206225db5e7d92b8c7c84ea7afccc86eeb513756bbd392` |
| Snapshot/suite | `20261120T000000Z`, trixie/main, `check-valid-until=no` |
| Package lock | [114 exact packages](../evidence/rw03-pdf-image-2026-11-22/packages.lock.json), including installation-support dependencies excluded from runtime binaries |
| InRelease SHA256 | `0584fba32e13e0ab8285fb16c27adea1ec03a73669c18702821094fd6ca86675` |
| Signature fingerprints (apt sqv) | `04B54C3CDCA79751B16BC6B5225629DF75B188BD`, `41587F7DB8C774BCCF131416762F67A0B2C39DE4`, `B8B80B5B623EAB6AD8775C45B7C5D7D6350947F8` |
| Rootfs tar / sole uncompressed layer SHA256 | `01e8b685061d4cec687b4f451c4e3a2e8299fbcf3e9b8ddd83cd8e6c5f1e9074` |
| Imported candidate local image ID | `sha256:a526f5d88b02e0af23ae5105d4f14da0f8c664595462afc65cac73b94744c944` |
| Docker-save archive SHA256 | `625d839aae1cd03ac798d8f78ab417b2d54fe73ab6f6d6f797e6cf0c3ea786e4` |

Acquisition hosts were `registry-1.docker.io`, `auth.docker.io`,
`production.cloudfront.docker.com` (observed registry HTTP 307 blob redirect) and
`snapshot.debian.org`. The existing Docker Desktop transport proxy
`http.docker.internal:3128` was in the path. Snapshot redirects recorded relative
paths on the same host. Step B used only local commands and the local daemon;
it downloaded nothing. See the [provenance receipt](../evidence/rw03-pdf-image-2026-11-22/provenance.md).

Two rootfs assemblies have identical inventories/tar bytes. Two imports have
different image IDs and creation timestamps, despite identical Config `{}` and
layer digests: **image-ID reproducibility is not established**. The smoke passed
normal arithmetic/anchors, malformed input and empty-page fixtures, exit 0,
`smoke_passed_not_qualified`, `sandbox_qualified: false`.

The [native isolation report](../evidence/rw03-pdf-image-2026-11-22/isolation-final.json)
and [full command log](../evidence/rw03-pdf-image-2026-11-22/isolation-final.log)
record working-tree source hashes over base `947ac3126ebd4867bfa91912dcd047c6a95ef580`.
The [raw create/inspect result](../evidence/rw03-pdf-image-2026-11-22/isolation-final-container-inspect.json)
uses the production argument helper, replacing only `run` with `create`; it was
never started. All these observed checks passed:

- NetworkMode `none`, no networks except `none`; read-only root; ALL capabilities
  dropped; no-new-privileges; UID/GID `65534:65534`.
- Memory and swap each 512 MiB, one CPU, PIDs 8; ulimits cpu 20, fsize 2097152,
  nofile 64 and core 0 (soft and hard).
- Only `/tmp` tmpfs, 32 MiB with nosuid/nodev/noexec; empty Mounts/Binds; no
  environment beyond the production runner's explicit environment; exact image
  pin; daemon reports built-in default seccomp. Created container removed and
  its absence verified.
- Real production-runner success and malformed-input rejection, a deterministic
  7,000,552-byte graphics-only PDF rejected at a lowered **0.5-second** deadline,
  and a 70,672-byte shared-page text PDF rejected for **over 2 MiB output**.
  The deadline bounds the Docker-client extraction phase, including startup;
  it is not a parser-only CPU benchmark. Production default remains 20 seconds.
- Exact expected timeout/overflow errors, captured CIDs, zero ancestor-image
  containers before/after each run, and individual CID absence after cleanup.
- Cleanup-denial/error-preservation regressions: **3 passed / 12 subtests**, exit
  0, explicitly **mocked**, not a real injected daemon cleanup denial.

These are configured-isolation and bounded synthetic runtime observations, not
proof of kernel escape resistance or independent security certification. The
first harness receipt is also retained; the final receipt adds complete outcome
logging and missing-inspection failure handling, rather than repeating an
unchanged run. The original standalone BuildKit build log was overwritten by
the classic attempt: its result is summarized in provenance and its rejected
smoke is retained, but the missing raw build log has not been reconstructed.

## Executable preparation

After image review, on the already authorized environment (the explicitly
authorized synthetic candidate runs above do not themselves constitute review):

```bash
export RESEARCHWITNESS_PDF_SANDBOX_IMAGE='sha256:<reviewed local image ID>'
python -m tools.pdf_sandbox_smoke --output /safe/output/pdf-smoke.json
```

The smoke tool constructs synthetic PDFs and calls the strict runner for normal
text/arithmetic, malformed bytes and no extractable text. It never pulls an image
or runs host Poppler. A first-fixture runtime failure stops the sequence. Its
`sandbox_qualified: false` output is intentional: smoke extraction is insufficient.

## Required real qualification

Before real documents, a separately reviewing security agent/operator must review
the image inventory/provenance and recorded evidence bound to the exact image ID,
and accept or resolve the open Windows pipe residual risks. No such separate
review has happened for this candidate. The required evidence includes
effective image/container inspection, no network route, bounded writable tmpfs,
no mounts/secrets, enforced resource limits, seccomp/capabilities/user, and confirmed
container absence after success/failure. Exercise controlled real timeout/output-
overflow fixtures and hermetic cleanup failures. Keep code/image/environment IDs
and hashes with every receipt. No dangerous exploit PDFs are required or authorized.

AI review is acceptable but must not be called a human audit or proof against a
kernel/runtime escape. Synthetic/mock success does not qualify actual isolation.
Protected evaluation additionally requires the separately qualified custody gate.

## Current blocker and autonomous next action

Candidate image and real synthetic isolation/resource/cleanup evidence are now
recorded. Separate security review of the inventory and this evidence, bound to
the exact image ID above, plus residual-risk acceptance remain outstanding:
check-then-use race, same-user/admin attackers, offline revocation, name-only
signer matching and installation integrity. `pdf_execution` remains `unqualified`.
The earlier managed-socket `operation not permitted` result is historical, not
the current image-availability blocker. RW-03 remains `blocked_external` while
separate capability acceptance and authorized isolated custody remain absent.

RW-03 may inspect current authorized capabilities, assemble/review an image and
collect real evidence autonomously when no new privileges, egress, secret access
or spending are required. It must not bypass the refusal through an alternative
daemon/route or alter permissions without a safety decision. If authority or money
is needed, record the exact blocker and ask only for that decision. Continue JATS
and other unblocked work. Do not turn a general "continue" instruction into permission
to weaken this boundary; the status changes only with actual qualification evidence.
