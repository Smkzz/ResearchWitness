# PDF execution boundary and outstanding qualification

The PDF byte parser is Poppler, a native parser for untrusted complex input. A
malformed PDF may exploit a native-code defect, consume resources, or emit
adversarial text. Table arithmetic and a pinned image ID do not mitigate those
risks by themselves. The Docker daemon and host kernel remain trusted. This is
process isolation, not a cryptographic or virtual-machine security boundary.

The existing runner in `tools/pdf_percentage_audit.py` uses only the local Unix
socket, a fresh Docker configuration, no network, no source-directory mount,
read-only root, UID/GID 65534, dropped capabilities, Docker's verified default
seccomp profile, no-new-privileges, and CPU/memory/PID/file/output/time bounds.
It transmits only input bytes over stdin and fails closed when cleanup cannot
be confirmed. It cannot inspect an image's hidden files or authenticate its
builder. Credentials in a baked filesystem remain a risk despite empty image
environment settings. Review the rootfs before selecting an image.

## Minimal image construction recipe (not built or qualified here)

Use an authorized build machine with a working managed daemon. Record the OS,
architecture, package-repository snapshot, signed repository metadata, exact
Poppler/package versions and hashes, builder image digest, build script and
source materials. No floating `latest` reference is an integrity commitment.
Extract reviewed distribution packages into a fresh rootfs: `pdftotext`, its
dynamic loader/shared-library dependency closure, required Poppler data and
font configuration only. Do not copy a development container, home directory,
Docker configuration, proxy CA, package cache, credentials, documents, shell,
or network client into the rootfs. Verify symlink destinations and needed
runtime resources against the package manifests. Record a sorted file inventory
with hashes, package licenses and known-vulnerability review. Verify the
inventory independently before building the runtime image.

Use a build context containing only that rootfs and this Dockerfile:

```dockerfile
FROM scratch
COPY rootfs/ /
```

Build offline from the audited context, without `ENV`, `ENTRYPOINT`, `VOLUME`
or build secrets. Record the resulting local `sha256:...` image ID, exported
image archive hash, complete layer/rootfs inventory and build log. Empty image
config is required by the runner. This recipe does not supply a reviewed rootfs,
package lock, trusted image ID or reproducibility proof. Those are external
qualification inputs; do not substitute the broad development image.

## Executable preparation

On the authorized machine, after image review, configure its exact local ID:

```bash
export RESEARCHWITNESS_PDF_SANDBOX_IMAGE='sha256:<reviewed local image ID>'
python -m tools.pdf_sandbox_smoke --output /safe/output/pdf-smoke.json
```

This constructs deterministic synthetic PDFs in Python, then calls the existing
strict runner. It checks normal text/arithmetic, malformed bytes and a page
without extractable text. It never pulls an image or runs Poppler on the host.
A first-fixture runtime failure stops the sequence. The result always states
`sandbox_qualified: false`: smoke extraction alone cannot qualify isolation.

Before real documents, an independent operator must additionally capture image
and effective container inspection, no network route, bounded writable tmpfs,
no mounts/secrets, enforced OS resource limits, seccomp/capabilities/user, and
container absence after success and failure. Run controlled real time-limit
and output-overflow fixtures, plus hermetic cleanup-failure injections. Keep
hashes and versions with each extracted representation. Do not run dangerous
exploit PDFs to establish this boundary.

## Current gate

**BLOCKED.** The prior managed-socket attempt returned `operation not permitted`;
no recovery or alternative daemon is authorized. No accepted minimal image
provenance or real isolation/resource/cleanup qualification is available.
Hermetic tests cover runner construction and failure paths; they are not real
Docker evidence. The required owner/environment action is to provision the
reviewed image and an authorized functioning local managed daemon, then collect
the qualification evidence above. No permission or policy change is made here.
