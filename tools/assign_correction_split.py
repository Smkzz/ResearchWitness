"""Deterministically allocate newly discovered correction leads before review.

This tool hashes only stable source identifiers. It must be run before reading
the correction body, corrected operands, or any detector output for a new lead.
It does not retrieve sources or invoke ResearchWitness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from typing import Any


PROTOCOL = "researchwitness-correction-split-v1"
RESERVED_BUCKET = 0
BUCKET_COUNT = 5
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_NAMESPACE = re.compile(r"^(doi|pmid|pmcid|arxiv|europepmc):\s*", re.IGNORECASE)


def canonical_identifier(value: str) -> str:
    """Normalize a DOI or namespaced bibliographic identifier, fail closed."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source identifier must be a non-empty string")
    raw = value.strip()
    raw = _DOI_PREFIX.sub("", raw, count=1).strip()
    if raw.casefold().startswith("10."):
        if "/" not in raw or any(char.isspace() for char in raw):
            raise ValueError("DOI is malformed or contains whitespace")
        canonical = "doi:" + raw.casefold()
    else:
        match = _NAMESPACE.match(raw)
        if not match:
            raise ValueError("non-DOI identifiers must include a recognized namespace")
        namespace = match.group(1).casefold()
        identifier = raw[match.end():].strip()
        if not identifier or any(char.isspace() for char in identifier):
            raise ValueError("source identifier is empty or contains whitespace")
        canonical = f"{namespace}:{identifier.casefold()}"
    return canonical


def allocate(original_identifier: str, correction_identifier: str) -> dict[str, Any]:
    """Return an immutable hash bucket and its prespecified pool assignment."""
    original = canonical_identifier(original_identifier)
    correction = canonical_identifier(correction_identifier)
    payload = f"{PROTOCOL}\n{original}\n{correction}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    bucket = int(digest[:8], 16) % BUCKET_COUNT
    return {
        "protocol": PROTOCOL,
        "original_identifier": original,
        "correction_identifier": correction,
        "sha256": digest,
        "bucket": bucket,
        "assignment": "RESERVED_FOR_FUTURE_EVALUATION" if bucket == RESERVED_BUCKET else "DEVELOPMENT",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-id", required=True)
    parser.add_argument("--correction-id", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(allocate(args.original_id, args.correction_id), sort_keys=True))
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
