# Synthetic-only offline custody worker

Ported from PR #12 at `78b26e2`. Synthetic engineering code only; not
custody-qualified. Protected custody **NOT RUN**. Production is disabled
pending Sami's separate security review. No historical installation or
qualification claims are carried forward.

The standard-library runtime rehearses hash-pinned source imports, exact
UTF-8 byte-span percentage reviews, verification, inventory seals and
threshold-only public summaries. It does not fetch papers, run detectors,
authenticate publications or establish independent custody. DOI counts do not
establish independent works; scope and licensing fields remain attestations.
The narrow v5 review profile requires one physical line with an explicit count
cue and complete numeric-span accounting. General tables remain unsupported.

## Synthetic engineering checks

    python -m unittest discover -s tests -p test_custody_worker.py -v
    python tools/qualify_custody_zipapp.py
    python custody_worker/build_release.py

Development dependencies supply jsonschema for tests. Pytest discovers these
unittest cases on the existing CI matrix. The zipapp builder emits its explicit
source/schema/LICENSE allowlist, manifest and sidecar under custody_worker/dist/.
The researchwitness wheel excludes this package.

Every CLI command requires --dev-root, a marked child under the system temp
directory's rw-custody-synthetic-only directory. Its .synthetic-only file must
contain RESEARCHWITNESS_SYNTHETIC_ONLY_V1 followed by a newline. Use only the
checked-in synthetic examples; the tests create roots and rehearse the workflow.
Missing --dev-root refuses before production preflight; invalid roots fail
closed without a production fallback. See the other documents in this directory.
