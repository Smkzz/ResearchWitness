# RW-03 image preparation receipt

Captured 2026-11-22 UTC, base commit
`62a8e32f030335bdccbaf3ee77f7384ddcb542d3`. This is build and smoke
evidence, not image review or sandbox qualification. Custody NOT RUN; EUR 0.

## Sources and transport

- Docker Hub: `auth.docker.io`, `registry-1.docker.io`.
- Observed blob redirect: HTTP 307 from `registry-1.docker.io` to
  `production.cloudfront.docker.com`. Signed redirect query values were not logged.
- Debian: `snapshot.debian.org` only. All recorded apt Host headers name that
  host; all recorded redirects use relative `/file/` paths on the same host.
- Docker Desktop reports its existing internal transport proxy
  `http.docker.internal:3128`; it was not reconfigured.

Snapshot transport is HTTP, explicitly authorized after the slim builder's
HTTPS certificate verification failed. TLS is not relied on for Debian archive
integrity. Apt verifies the InRelease OpenPGP signature using the pinned builder's
debian-archive-keyring, then the index hashes. Each downloaded deb is additionally
checked against its SHA256 in packages.lock.json. No signature/hash bypass,
trusted=yes, allow-insecure or extra trust key was used. The final recipe routes
non-snapshot apt hosts to a closed loopback proxy rather than an external host.

## Pins

- Tag: `debian:trixie-slim`.
- Tag index: `sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2`.
- Selected linux/amd64 manifest, pulled by digest:
  `sha256:7378260c0a098d27ac206225db5e7d92b8c7c84ea7afccc86eeb513756bbd392`.
- Snapshot: `http://snapshot.debian.org/archive/debian/20261120T000000Z/`,
  trixie/main, check-valid-until=no, archive signatures still mandatory.
- InRelease SHA256:
  `0584fba32e13e0ab8285fb16c27adea1ec03a73669c18702821094fd6ca86675`.
- Apt's sqv GOODSIG fingerprints are recorded in the lock and resolve.log.
- 114 packages: apt's no-recommends poppler-utils dependency/predependency
  resolution with an empty installed-package status. This deliberately includes
  installation-support dependencies. They are extracted, not installed; their
  binaries are not copied into the final runtime. Copyright files are retained.
- Runtime selection: pdftotext, staged dynamic-loader dependency listing,
  Poppler/font/fontconfig resources present in those packages, and licenses only.
  No extra recommended poppler-data package was added.

## Reproducibility

Two final-script assemblies (`rw03-pdf-repro-a`, `rw03-pdf-repro-b`) have identical
inventories and rootfs tar bytes. SHA256 of both rootfs tars:
`01e8b685061d4cec687b4f451c4e3a2e8299fbcf3e9b8ddd83cd8e6c5f1e9074`.
The intermediate assembly used to build the image below has the same tar hash.
Archive ownership is numeric 0:0; mtimes are fixed to the snapshot timestamp.
Work directories and binary archives are outside Git under the operator's home.

## Negative builder attempts and selected import method

The Dockerfile is exactly FROM scratch plus COPY rootfs/ /. BuildKit built it
without a syntax frontend or pulled base, but injected a default PATH into Env.
BuildKit local image ID:
`sha256:89d25fd47d849b9d7678601baad2fa6ed1db7aff47608fa1301a39ca32091d85`.
The production smoke stopped at image configuration verification, exit 2:
`The Poppler sandbox image must have no baked environment, entrypoint, or volumes`.
The normal PDF fixture was not executed. See pdf-smoke.json for the rejection.

Image config inspection returned:

```json
{"Env":["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"],"WorkingDir":"/"}
```

The subsequent classic-builder attempt also injected the same PATH. See
classic-build.log. Its image ID was
`sha256:1e8bacbfa2a12e8c708698169d161b8334074c3038f0eaed96b001c2296451f9`.
The original BuildKit console output is summarized here rather than retained as
a full standalone build log; the original rejected smoke is pdf-smoke.json.
The classic attempt replaced the original build log before it was renamed;
this evidence limitation is not a claim that classic-build.log records BuildKit.
Recorded text has LF line endings. A cosmetic trailing space on the classic
builder's empty scratch-image progress line was trimmed; no result was changed.

As subsequently authorized, the final recipe uses local offline `docker import`
of the deterministic rootfs tar, with no --change flags. Env, Entrypoint, Cmd,
Volumes, WorkingDir and User are all absent in both imported Config objects (`{}`).
The runner is unchanged. No default PATH is baked into this image; the runner
sets its own runtime environment explicitly.

Final selected image:
`sha256:a526f5d88b02e0af23ae5105d4f14da0f8c664595462afc65cac73b94744c944`.
Second import of identical rootfs bytes:
`sha256:f410b28090506815349ba6964bd23cbb1e72114c790cbb42eca1df3e90b581da`.
**Image IDs are not reproducible**: creation timestamps differ. The rootfs tar,
inventories and uncompressed layer digests are identical. See image-summary.json
and the full image-inspect.json, which retain creation timestamps and IDs.

Both imports have the sole RootFS layer/diff ID
`sha256:01e8b685061d4cec687b4f451c4e3a2e8299fbcf3e9b8ddd83cd8e6c5f1e9074`.
SHA256 of docker save archive (outside Git at the operator's home,
`rw03-pdf-final-image.tar`):
`625d839aae1cd03ac798d8f78ab417b2d54fe73ab6f6d6f797e6cf0c3ea786e4`.
Archive identity is a receipt for this export, not a reproducibility claim.

The final image passes all three smoke fixtures, exit 0, recorded in
pdf-final-smoke.json and final-image.log. Status is `smoke_passed_not_qualified`,
with `sandbox_qualified: false`. The intermediate import's successful smoke is
also retained as pdf-import-smoke.json; it is not evidence for the final ID.
capture_final.py records the exact local commands, environment header, inspect,
history and export, with exit codes. Imports/builds do not contact registries.

This image has not received the separate rootfs/package/provenance security
review, current vulnerability/license assessment, or real isolation/resource/
cleanup qualification. The supplied tar/rootfs reconstruction is reproducible,
but image ID reconstruction is not. Gate and status documents remain untouched.

## Step B - native synthetic isolation evidence (2026-11-22)

The paragraph above describes the Step A receipt. Step B now updates the gate
notes/status documents while retaining every gate value as unqualified/not_run.
The coordinator relayed Sami's bounded download approval on 2026-11-22; the
subsequent HTTP decision did not waive archive signatures, hashes or security
review. Step B itself used only local tools and daemon operations, no downloads,
new privileges, protected custody or scientific evaluation.

isolation-final.json/log and isolation-final-container-inspect.json bind the
native results to the exact candidate ID above and record source SHA256 over
Step A base 947ac3126ebd4867bfa91912dcd047c6a95ef580. The harness reuses the
production argument helper and real extraction runner. The inspection container
was created, not started, and removed. Every configured isolation check passed:
network none, read-only root, capabilities dropped, no-new-privileges, UID/GID,
memory/swap/CPU/PID/ulimits, bounded secure tmpfs, no mounts/binds or unexpected
environment, exact pin and daemon default seccomp.

Real success, malformed-input rejection, 0.5-second lowered-timeout rejection
and over-2-MiB output rejection all passed. All per-run ancestor inventories were
empty before and after, and each recorded CID was independently confirmed
absent. Production timeout remains 20 seconds. Timeout is the runner's
Docker-client extraction deadline (including startup), not parser-only CPU time.
The timeout PDF is 7,000,552 bytes of benign drawing instructions; overflow is a
70,672-byte synthetic shared-stream multipage text PDF. Neither is an exploit.
Cleanup-denial/error-preservation tests were mocked: 3 passed, 12 subtests, exit
0; they do not prove real cleanup-denial handling on this daemon.

The earlier isolation.json/log and container-inspect.json are retained as the
first harness capture. The final run followed logging and missing-inspection
failure-handling changes; it is not an unchanged confidence-inflation rerun.
Both have sandbox_qualified=false. Separate security review of the image
inventory and this evidence bound to the exact candidate ID has NOT happened;
an AI reviewer is acceptable, but no human audit is claimed. Windows pipe risks
remain open: race, same-user/admin attackers, offline-only revocation, name-only
signer matching and installation integrity. RW-03 remains blocked_external;
custody NOT RUN and scientific gates unchanged. The overwritten standalone
BuildKit log remains a disclosed gap, not repaired by these runtime receipts.

## Follow-up scope and continuity clarification

The 32 isolation check records mean effective-config inspection plus synthetic
benign fixture runs (timeout, overflow, success/failure cleanup) and explicitly
mocked cleanup-denial regressions. They are not escape or exploit attempts.
The base HEAD 947ac31 recorded during Step B does not mean its uncommitted
runner/harness source hashes were present in that Git commit. Comparison with
merged main 6a26ab5 found the runner changed and the harness was absent in
947ac31. The smoke tool and other imported runtime source files were unchanged.
The exact per-file old/new hashes and a fresh local-only capture against
6a26ab5's runtime are preserved alongside this historical bundle in
../rw03-pdf-followup-2026-11-22/. Neither historical raw receipts nor this
qualification boundary have been replaced: the 32 checks are not security
certification, and PDF execution remains unqualified.
