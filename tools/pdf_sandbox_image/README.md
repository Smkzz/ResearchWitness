# Pinned Poppler runtime assembly

This is image preparation, not security/isolation qualification. No real documents,
custody, new privileges, paid services or new source hosts are authorized here.

Use the already provisioned linux/amd64 builder in `build.py`. The committed lock
is `evidence/rw03-pdf-image-2026-11-22/packages.lock.json`. Keep an immutable copy
of that lock; the resolve command creates a new lock, not an update to use silently.

From the repository root, with fresh work directories outside Git:

```text
python tools/pdf_sandbox_image/build.py resolve --work-dir <resolution-dir> --evidence <new-evidence-dir>
python tools/pdf_sandbox_image/build.py build --work-dir <assembly-dir> --evidence <evidence-containing-lock>
python tools/pdf_sandbox_image/build.py image --work-dir <assembly-dir> --evidence <evidence-containing-lock>
```

Before assembly, the host verifies the locked InRelease SHA256, then invokes
the pinned builder's `sqv --cleartext --signatures 3` with networking disabled
and a read-only metadata mount. Its successful fingerprint output must equal
the complete locked signer set, also pinned by `SIGNING_FINGERPRINTS`; missing,
additional or unexpected signers fail closed. Resolution uses the same check.
Assembly's apt-fetched InRelease must match those verified bytes by SHA256.
The build command downloads exact locked versions, checks the signed InRelease
hash and every deb SHA256, and extracts packages without executing maintainer
scripts. Apt is restricted to the fixed snapshot; a closed loopback proxy blocks
other HTTP hosts and HTTPS redirects. A blocked redirect is a stop condition, not
permission to change the proxy or disable verification. HTTP transport is expressly
authorized: integrity relies on the pinned builder's Debian archive keyring,
OpenPGP signatures and the signed SHA256 chain, not TLS.

Resolution uses an empty dpkg status and no recommends, including Depends and
Pre-Depends installation-support packages. The final runtime excludes their
executables: only pdftotext, its staged loader/library closure, present Poppler/font
data and package copyright files are copied. The staged loader's `--list` performs
the dependency inspection normally provided by ldd without using the builder's
potentially different library versions. The extracted dynamic loader **does run**
inside the builder with `--list`; pdftotext's main program and package maintainer
scripts are not invoked during assembly. The builder also runs its shell, apt-get,
apt-cache (resolution), dpkg-deb, awk, find, sort, xargs, sha256sum, tar and file
utilities (rm, mkdir, chmod, chown, cp, ln, touch, dirname). The separate offline
signature check runs the builder's sqv. Host Python and Docker CLI orchestrate
these steps. No PDF is processed during rootfs assembly.
The inventory records sorted paths, modes, sizes, hashes and link targets.
Tar ownership and timestamps are normalized; a second assembly must be compared.

`Dockerfile` records the minimal scratch/COPY layout but is **not the final image
creation method**. BuildKit injects a default PATH, and this machine's classic
builder does too. Both violate the production runner's empty-Env requirement.
The `image` operation therefore uses local, offline `docker import rootfs.tar`,
without any `--change` flags. Before any Docker invocation it hashes rootfs.tar
and requires the recipe's `ROOTFS_SHA256`,
`01e8b685061d4cec687b4f451c4e3a2e8299fbcf3e9b8ddd83cd8e6c5f1e9074`,
matching the recorded image-summary.json rootfs/layer digest. A changed tar
requires a separately reviewed recipe/pin update, not an automatically adopted
new digest. Because import uses the daemon's native platform,
the operation rejects any daemon other than linux amd64/x86_64 before importing,
then requires the inspected image to report Architecture amd64 and Os linux
before writing the image pin. Inspect Config before use; Env, Entrypoint and
Volumes must be absent/empty. Do not relax the runner. Imports include creation
timestamps, so identical rootfs/layer hashes need not yield identical image IDs.
Pin and review each resulting local ID separately; do not claim image-ID
reproducibility from rootfs reproducibility.

Run the existing smoke only after provisioning, using the exact inspected local
ID. A successful smoke remains `smoke_passed_not_qualified`. The evidence bundle
must retain negative attempts, image inspection/history, save-archive SHA256,
layer digests, reproduction comparisons, source hosts/redirects and limitations.
Do not commit binary rootfs/image archives or downloads. See the bundle's
provenance.md for this run and the separate outstanding qualification requirements.
