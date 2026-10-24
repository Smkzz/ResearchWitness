# PDF execution boundary and outstanding qualification

**Observed state:** UNQUALIFIED; real PDF execution remains disabled.  
**Plan owner:** RW-03 in [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md).

Poppler is a native parser for attacker-controlled complex input. Malformed PDFs
may exploit defects, consume resources or emit adversarial instructions. Arithmetic
checks and pinned image IDs do not remove these risks. The Docker daemon and host
kernel remain trusted; this is process isolation, not a cryptographic/VM boundary.

The existing runner uses only the local Unix socket, a fresh Docker configuration,
no network/source-directory mount, read-only root, UID/GID 65534, dropped capabilities,
verified default seccomp, no-new-privileges, and CPU/memory/PID/file/output/time bounds.
It sends input over stdin and fails closed if cleanup is not confirmed. It cannot
authenticate a builder or inspect hidden image files. Review the rootfs, not only
its empty environment settings. No host Poppler fallback is permitted.

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
