# Security and trust model

ResearchWitness is a bounded offline verifier, not a secure execution platform and not an authority on scientific truth.

## Supported boundary

The caller chooses a trusted, quiescent directory. Files inside the bundle are treated as untrusted data.

The core rejects or bounds:

- duplicate JSON keys;
- JSON floats and non-finite values;
- excessive JSON size, depth and node count;
- malformed or oversized rational literals;
- unknown schema fields;
- path traversal and absolute paths;
- backslash/drive-letter path forms;
- common Windows reserved names;
- case-insensitive path collisions;
- file/directory prefix collisions;
- symbolic links;
- hard-linked artifacts;
- FIFOs and other non-regular files;
- oversized individual artifacts and bundles.

Artifact bytes are checked against their SHA-256 manifest entries. Proof-boundary checks use explicit exceptions rather than Python `assert`, including when Python is run with `-O`.

The deterministic verifier imports only its own modules and the Python standard library. The optional `paper` extra adds `pypdf` for PDF text extraction. The untrusted paper-ingestion front end starts one fixed-argument PDF worker with `shell=False`, a wall timeout, bounded input and output, and CPU/address-space limits where supported. The worker has no network client or access to the user's original path, but it runs as the same OS user; this is process isolation, not a sandbox. ResearchWitness has no arbitrary dynamic code loading, pickle deserialization, model call, email sender, browser integration, or publication client.

## What hashes do and do not prove

Hashes establish byte consistency. They do not establish authenticity or truth.

A malicious producer can fabricate a complete bundle and recompute every internal hash. An `--expected-bundle-sha256` value stored by a separate trusted process can detect later modification of that pinned state, but it cannot make the original bundle truthful.

The `subject_sha256` binds the exact verification question and its core inputs. It intentionally ignores unrelated supplemental manifested artifacts. The `bundle_sha256` commits to the full case manifest.

## Source trust

A source quote is checked against supplied text bytes at the declared byte offset. This does not prove:

- that those bytes came from the claimed publisher or repository;
- that a PDF-to-text extraction retained all glyphs correctly;
- that the formalization preserves every source assumption;
- that another version or supplement does not change the claim.

`capture_status: captured` is contextual metadata, not cryptographic authentication. The report therefore keeps `paper_error_established: false` even when the formalization-level counterexample is exact.

`paper-audit` is an untrusted discovery layer outside the proof boundary. Its optional PDF parser runs in a separate worker with a 20-second wall timeout, 15-second CPU limit and 768 MiB address-space limit where POSIX resource limits are supported. The worker receives a private temporary copy of the bounded source file. This is not an OS sandbox: it shares the caller's user permissions and kernel, and parser operations can still fail in ways the limits do not anticipate. Do not use it as a hostile-document sandbox. It performs no OCR, and parser failure or resource-limit outcomes do not run numeric detectors.

## Filesystem threat model

ResearchWitness rejects symlinks and hard links and uses `O_NOFOLLOW` where the platform exposes it. It verifies the opened file is regular and checks its size while reading.

It does **not** claim protection from an attacker who controls:

- the Python interpreter;
- the operating system or kernel;
- filesystem mounts;
- the installed ResearchWitness code;
- parent-directory replacement races during evaluation.

The supported deployment assumes a trusted local process and a bundle directory that is not being concurrently mutated.

## Resource limits

The parser and checkers contain explicit structural and arithmetic limits intended to keep malformed input bounded. These are engineering controls, not a formally proved denial-of-service defense. POSIX CPU and address-space limits are best-effort process quotas; other systems rely on the wall timeout and input/output bounds. This limitation especially applies to `pypdf` when processing complex PDFs.

Do not add an unbounded CAS, SMT solver, optimizer, PDF parser, or arbitrary repository execution path to the trusted core without a separate threat model.

## Private data

`pack` exports only manifested artifacts plus canonical `case.json` and `report.json`. This prevents accidental recursive collection of unrelated files, but an operator can still deliberately manifest sensitive material.

Review the manifest before sharing a package. Keep unpublished manuscripts, private correspondence, personal contact details and credentials out of public repositories.

## External actions

The deterministic core cannot send mail, publish findings or authorize contact. The MVP product layer can generate a local draft only after conservative readiness checks; it never sends it. Reports contain:

```text
external_actions: OUT_OF_SCOPE
```

Any future integration capable of external communication must remain outside the verifier and must not interpret a formalization-level result as permission to contact a person.

## Supported versions

| Version | Security fixes |
|---|---|
| 0.2.x | Yes |
| < 0.2 | No |

## Reporting a vulnerability

Do **not** file a public issue for a vulnerability that could expose confidential research material, credentials, personal information, or a practical integrity bypass. Use GitHub's private vulnerability-reporting / security-advisory flow when it is available for this repository. If that private option is unavailable, contact the repository owner through the contact methods on their GitHub profile before sharing sensitive details.

For non-sensitive hardening bugs, a public issue with a synthetic reproducer is welcome. Synthetic fixtures are preferred for parser or verifier defects; real unpublished manuscripts are not required.

Please include the affected version, threat scenario, a minimal reproducer, and the expected security property. Maintainers will acknowledge triage as repository availability permits; this research-preview project does not promise a fixed response SLA.
