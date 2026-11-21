# PDF execution boundary and outstanding qualification

**Observed state:** UNQUALIFIED; real PDF execution remains disabled.  
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
the folder instead of the environment. The executable must pass offline
`WinVerifyTrust` Authenticode verification and its leaf signer certificate's
subject simple-display name must be exactly `Docker Inc`. Verification disables
UI and revocation checks and uses cache-only URL retrieval: no network access.
Trust state is always closed and known-folder memory freed; API and cleanup
failures block execution. Offline-only revocation means a revoked certificate
is not detected; the entire installation's integrity is not verified.
A check-then-use race remains because
the Docker CLI opens a separate connection after the check; an administrator or
same-user attacker is not defended against. These remain qualification limitations,
and `pdf_execution` stays unqualified: the reviewed image is still blocked.
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

## Minimal image construction recipe - not built or qualified by this document

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
empty image configuration. This recipe supplies no image, trusted package lock or
reproducibility proof. Do not substitute a broad development container.

## Executable preparation

After image review, on the already authorized environment:

```bash
export RESEARCHWITNESS_PDF_SANDBOX_IMAGE='sha256:<reviewed local image ID>'
python -m tools.pdf_sandbox_smoke --output /safe/output/pdf-smoke.json
```

The smoke tool constructs synthetic PDFs and calls the strict runner for normal
text/arithmetic, malformed bytes and no extractable text. It never pulls an image
or runs host Poppler. A first-fixture runtime failure stops the sequence. Its
`sandbox_qualified: false` output is intentional: smoke extraction is insufficient.

## Required real qualification

Before real documents, a separately reviewing security agent/operator must record
effective image/container inspection, no network route, bounded writable tmpfs,
no mounts/secrets, enforced resource limits, seccomp/capabilities/user, and confirmed
container absence after success/failure. Exercise controlled real timeout/output-
overflow fixtures and hermetic cleanup failures. Keep code/image/environment IDs
and hashes with every receipt. No dangerous exploit PDFs are required or authorized.

AI review is acceptable but must not be called a human audit or proof against a
kernel/runtime escape. Synthetic/mock success does not qualify actual isolation.
Protected evaluation additionally requires the separately qualified custody gate.

## Current blocker and autonomous next action

The prior managed-socket attempt returned `operation not permitted`; accepted image
provenance and real isolation/resource/cleanup receipts are still absent at the
observed baseline. That historical failure is not a fresh test of every environment.

RW-03 may inspect current authorized capabilities, assemble/review an image and
collect real evidence autonomously when no new privileges, egress, secret access
or spending are required. It must not bypass the refusal through an alternative
daemon/route or alter permissions without a safety decision. If authority or money
is needed, record the exact blocker and ask only for that decision. Continue JATS
and other unblocked work. Do not turn a general "continue" instruction into permission
to weaken this boundary; the status changes only with actual qualification evidence.
