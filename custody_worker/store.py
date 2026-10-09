"""Private source-bound offline evidence store with versioned review contracts."""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any

from .policy import (
    IMPORT_VERSION, REVIEW_VERSION, SEAL_VERSION, SUMMARY_VERSION,
    PUBLIC_SUMMARY_VERSION, MAX_ITEMS, MAX_SOURCE_BYTES, MAX_ANCHOR_CHARS,
    MAX_JSON_BYTES, CustodyError, reject, id_valid, hash_valid, source_name,
    require_keys, bounded_int, computed_percent, canonical_bytes,
    sha256_bytes, strict_json_bytes, checked_read, read_json, guarded_stat,
    safe_source_file, authorize_store_root, normalize_doi, normalize_source_id,
    validate_span, require_nested_span, parse_count_span, parse_percent_span,
    validate_source_provenance, validate_utc_timestamp, utc_now,
    within, DEV_PARENT, PRODUCTION_ROOT,
)

MAX_BATCH_BYTES = 64 * 1024 * 1024
MAX_LEDGER_RECORDS = 10_000
MAX_LEDGER_BYTES = 256 * 1024 * 1024
MAX_SOURCE_OBJECTS = 10_000
MAX_SOURCE_STORE_BYTES = 2 * 1024 * 1024 * 1024
MAX_SEAL_BYTES = 16 * 1024 * 1024
TEXT_SOURCE_EXTENSIONS = {".txt", ".md", ".xml", ".csv", ".tsv"}
SUBDIRS = (
    "incoming", "sources", "corrections", "sealed-labels", "manifests",
    "audit", "objects", "objects/sha256", "manifests/imports",
    "manifests/reviews",
)
ROLES = {"original", "correction", "supplement"}
REVIEW_ROLES = {"CORRECTION_POSITIVE", "CORRECT_NEGATIVE_RELATION", "OTHER"}
REVIEW_ELIGIBILITY = {"ELIGIBLE", "INELIGIBLE", "UNRESOLVED"}
RELATION_FIELDS = {"numerator", "denominator", "percentage"}
SOURCE_VERSION_STATUS = "CUSTODIAN_CONFIRMED_SOURCE_VERSION"
SCOPE_STATUS = "CUSTODIAN_CONFIRMED_SAME_SCOPE"
CORRECTION_STATUS = "CUSTODIAN_CONFIRMED_EXACT_CORRECTION"
PUBLIC_EXPORT_VERSION = "rw-custody-public-export/2"
REVIEW_RECORD_VERSION = "rw-custody-review-record/5"
LEGACY_REVIEW_RECORD_VERSION = "rw-custody-review-record/4"


def _authorize_path(path: Path) -> Path:
    """Resolve a requested storage path to its fixed production or synthetic root."""
    candidate = Path(os.path.abspath(path))
    if within(candidate, PRODUCTION_ROOT):
        return authorize_store_root(PRODUCTION_ROOT)
    if within(candidate, DEV_PARENT):
        relative = Path(os.path.relpath(candidate, DEV_PARENT))
        if not relative.parts or relative.parts[0] in ("", "."):
            reject("PATH_OUTSIDE_ALLOWED_ROOT")
        return authorize_store_root(DEV_PARENT / relative.parts[0])
    reject("PATH_OUTSIDE_ALLOWED_ROOT")


def _new_commitment_key(path: Path) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    except FileExistsError:
        return
    except OSError:
        reject("COMMITMENT_KEY_CREATE_FAILED")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(secrets.token_bytes(32))
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        reject("COMMITMENT_KEY_CREATE_FAILED")


def _commitment_key(root: Path) -> bytes:
    path = root / "audit" / "commitment-key.bin"
    guarded_stat(path, file=True)
    key = checked_read(path, max_bytes=32)
    if len(key) != 32:
        reject("COMMITMENT_KEY_INVALID")
    return key


def make_store(root: Path) -> None:
    root = authorize_store_root(root)
    _make_store(root)


def _make_store(root: Path) -> None:
    guarded_stat(root, file=False)
    for rel in SUBDIRS:
        path = root / rel
        if path.exists() or path.is_symlink():
            guarded_stat(path, file=False)
        else:
            try:
                path.mkdir()
            except OSError:
                reject("STORE_DIRECTORY_CREATE_FAILED")
            guarded_stat(path, file=False)
    key_path = root / "audit" / "commitment-key.bin"
    if key_path.exists() or key_path.is_symlink():
        guarded_stat(key_path, file=True)
        _commitment_key(root)
    else:
        _new_commitment_key(key_path)
        guarded_stat(key_path, file=True)
        _commitment_key(root)


@contextlib.contextmanager
def store_lock(root: Path):
    root = authorize_store_root(root)
    with _store_lock(root):
        yield


@contextlib.contextmanager
def _store_lock(root: Path):
    lock = root / "audit" / ".exclusive-lock"
    guarded_stat(root / "audit", file=False)
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    except FileExistsError:
        reject("STORE_LOCK_HELD_MANUAL_REVIEW_REQUIRED")
    except OSError:
        reject("STORE_LOCK_FAILED")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"OFFLINE_WORKER_LOCK_V2\n")
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        try:
            if lock.is_file() and not lock.is_symlink():
                lock.unlink()
        except OSError:
            reject("STORE_LOCK_CLEANUP_FAILED")


def _immutable_write(root: Path, path: Path, data: bytes) -> str:
    if not within(path, root) or len(data) > MAX_SOURCE_BYTES:
        reject("PATH_OUTSIDE_STORE" if not within(path, root) else "FILE_TOO_LARGE")
    guarded_stat(path.parent, file=False)
    digest = sha256_bytes(data)
    if path.exists() or path.is_symlink():
        previous = checked_read(path, max_bytes=MAX_SOURCE_BYTES)
        if previous != data:
            reject("IMMUTABLE_RECORD_CONFLICT")
        return digest
    try:
        fd, name = tempfile.mkstemp(prefix=".rw-tmp-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            guarded_stat(temporary, file=True)
            if sha256_bytes(checked_read(temporary, max_bytes=MAX_SOURCE_BYTES)) != digest:
                reject("TEMPORARY_WRITE_INTEGRITY_FAILURE")
            if path.exists() or path.is_symlink():
                reject("IMMUTABLE_RECORD_CONFLICT")
            os.rename(temporary, path)
            guarded_stat(path, file=True)
        finally:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
    except CustodyError:
        raise
    except OSError:
        reject("RECORD_WRITE_FAILED")
    return digest


def immutable_write(path: Path, data: bytes) -> str:
    """Lower-level write API; it repeats store authorization instead of trusting CLI preflight."""
    root = _authorize_path(path)
    return _immutable_write(root, path, data)


def _manifest_validation(raw: object, *, synthetic_only: bool) -> dict:
    obj = require_keys(raw, {"schema_version", "batch_id", "files"})
    if obj["schema_version"] != IMPORT_VERSION:
        reject("UNSUPPORTED_MANIFEST_VERSION")
    id_valid(obj["batch_id"])
    entries = obj["files"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ITEMS:
        reject("INVALID_MANIFEST_FILES")
    names: set[str] = set()
    canonical_records: set[tuple[str, str, str, str]] = set()
    total_bytes = 0
    for item in entries:
        require_keys(item, {
            "name", "role", "size", "sha256", "document_id",
            "source_id", "source_version", "provenance",
        })
        validate_source_provenance(item["provenance"], synthetic_only=synthetic_only)
        name = source_name(item["name"])
        if not isinstance(item["role"], str) or item["role"] not in ROLES:
            reject("INVALID_SOURCE_ROLE")
        bounded_int(item["size"], minimum=1, maximum=MAX_SOURCE_BYTES)
        total_bytes += item["size"]
        if total_bytes > MAX_BATCH_BYTES:
            reject("BATCH_TOTAL_SIZE_LIMIT")
        hash_valid(item["sha256"])
        document_id = normalize_doi(item["document_id"])
        source_id = normalize_source_id(item["source_id"])
        if item["document_id"] != document_id or item["source_id"] != source_id:
            reject("IDENTIFIER_NOT_CANONICAL")
        version = item["source_version"]
        if not isinstance(version, str) or not 1 <= len(version) <= 160 or "\x00" in version:
            reject("INVALID_SOURCE_VERSION")
        folded_name = name.casefold()
        if folded_name in names:
            reject("DUPLICATE_MANIFEST_SOURCE_NAME")
        names.add(folded_name)
        identity = (document_id, source_id, version, item["role"])
        if identity in canonical_records:
            reject("DUPLICATE_SOURCE_VERSION_RECORD")
        canonical_records.add(identity)
    return obj


def _iter_json_files(directory: Path, pattern: str, *, max_file_bytes: int = MAX_JSON_BYTES) -> list[Path]:
    guarded_stat(directory, file=False)
    result: list[Path] = []
    total_bytes = 0
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(result) >= MAX_LEDGER_RECORDS:
                    reject("INVENTORY_LIMIT_EXCEEDED")
                path = directory / entry.name
                if not re.fullmatch(pattern, path.name):
                    reject("UNEXPECTED_INVENTORY_ENTRY")
                info = guarded_stat(path, file=True)
                if info.st_size > max_file_bytes:
                    reject("INVENTORY_FILE_TOO_LARGE")
                total_bytes += info.st_size
                if total_bytes > MAX_LEDGER_BYTES:
                    reject("INVENTORY_LIMIT_EXCEEDED")
                result.append(path)
    except CustodyError:
        raise
    except OSError:
        reject("INVENTORY_READ_FAILED")
    result.sort(key=lambda path: path.name)
    return result


def _source_index(root: Path) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    directory = root / "manifests" / "imports"
    unique_sizes: dict[str, int] = {}
    version_bindings: dict[tuple[str, str, str, str], str] = {}
    record_count = 0
    unique_total_bytes = 0
    for path in _iter_json_files(directory, r"[a-z][a-z0-9-]{2,63}\.json"):
        manifest = _manifest_validation(
            read_json(path), synthetic_only=within(root, DEV_PARENT),
        )
        if path.stem != manifest["batch_id"] or checked_read(path) != canonical_bytes(manifest):
            reject("IMPORT_LEDGER_CORRUPT")
        for item in manifest["files"]:
            record_count += 1
            digest = item["sha256"]
            version_identity = (
                item["document_id"], item["source_id"],
                item["source_version"], item["role"],
            )
            prior_digest = version_bindings.get(version_identity)
            if prior_digest is not None and prior_digest != digest:
                reject("SOURCE_VERSION_CONTENT_CONFLICT")
            version_bindings[version_identity] = digest
            previous_size = unique_sizes.get(digest)
            if previous_size is not None and previous_size != item["size"]:
                reject("SOURCE_SIZE_METADATA_CONFLICT")
            if previous_size is None:
                unique_sizes[digest] = item["size"]
                unique_total_bytes += item["size"]
            if record_count > MAX_SOURCE_OBJECTS or unique_total_bytes > MAX_SOURCE_STORE_BYTES:
                reject("SOURCE_INVENTORY_LIMIT_EXCEEDED")
            index.setdefault(digest, []).append(item)
    object_dir = root / "objects" / "sha256"
    object_names: set[str] = set()
    object_bytes = 0
    try:
        with os.scandir(object_dir) as entries:
            for entry in entries:
                if len(object_names) >= MAX_SOURCE_OBJECTS:
                    reject("SOURCE_INVENTORY_LIMIT_EXCEEDED")
                name = entry.name
                if not re.fullmatch(r"[0-9a-f]{64}", name, re.ASCII):
                    reject("UNEXPECTED_SOURCE_OBJECT")
                info = guarded_stat(object_dir / name, file=True)
                object_bytes += info.st_size
                if object_bytes > MAX_SOURCE_STORE_BYTES:
                    reject("SOURCE_INVENTORY_LIMIT_EXCEEDED")
                object_names.add(name)
    except CustodyError:
        raise
    except OSError:
        reject("SOURCE_OBJECT_DIRECTORY_UNAVAILABLE")
    if object_names != set(unique_sizes):
        reject("UNREFERENCED_SOURCE_OBJECT")
    for digest, expected_size in unique_sizes.items():
        object_path = root / "objects" / "sha256" / digest
        data = checked_read(object_path, max_bytes=MAX_SOURCE_BYTES)
        if len(data) != expected_size or sha256_bytes(data) != digest:
            reject("SOURCE_OBJECT_INTEGRITY_FAILURE")
    return index


def imported_hashes(root: Path) -> set[str]:
    root = authorize_store_root(root)
    with _store_lock(root):
        return set(_source_index(root))


def imported_roles(root: Path) -> dict[str, set[str]]:
    root = authorize_store_root(root)
    with _store_lock(root):
        roles: dict[str, set[str]] = {}
        for digest, entries in _source_index(root).items():
            roles[digest] = {entry["role"] for entry in entries}
        return roles


def _matching_source(root: Path, source_index: dict[str, list[dict[str, Any]]],
                     digest: object, role: str, document_id: str,
                     version: object) -> tuple[dict[str, Any], bytes]:
    digest = hash_valid(digest)
    if not isinstance(version, str) or not version:
        reject("INVALID_SOURCE_VERSION")
    matches = [
        entry for entry in source_index.get(digest, [])
        if entry["role"] == role and entry["document_id"] == document_id
        and entry["source_version"] == version
    ]
    if not matches:
        reject("SOURCE_VERSION_NOT_IMPORTED")
    names = {entry["name"].rsplit(".", 1)[-1].casefold() for entry in matches}
    source_ids = {entry["source_id"] for entry in matches}
    if len(names) != 1 or len(source_ids) != 1:
        reject("SOURCE_MAPPING_AMBIGUOUS")
    extension = "." + next(iter(names))
    if extension not in TEXT_SOURCE_EXTENSIONS:
        reject("SOURCE_FORMAT_NOT_BOUND_FOR_TEXT_REVIEW")
    data = checked_read(root / "objects" / "sha256" / digest, max_bytes=MAX_SOURCE_BYTES)
    if sha256_bytes(data) != digest:
        reject("OBJECT_INTEGRITY_FAILURE")
    return matches[0], data


def _normalize_context(value: str) -> str:
    return " ".join(value.casefold().split())


def _canonical_table_locator(value: str) -> str:
    normalized = _normalize_context(value)
    match = re.fullmatch(r"table\s+0*([0-9]+)", normalized)
    if match and int(match.group(1)) > 0:
        return f"table {int(match.group(1))}"
    return normalized


def _line_bounds(source: bytes, start: int) -> tuple[int, int]:
    line_start = source.rfind(b"\n", 0, start) + 1
    line_end = source.find(b"\n", start)
    if line_end < 0:
        line_end = len(source)
    if line_end > line_start and source[line_end - 1:line_end] == b"\r":
        line_end -= 1
    return line_start, line_end


def _has_explicit_count_cue(source: bytes, numerator: tuple[str, int, int]) -> bool:
    """Require the selected numerator to follow a literal count field label."""
    prefix = source[_line_bounds(source, numerator[1])[0]:numerator[1]]
    return re.search(rb"(?i)(?<![a-z0-9_])count\s*[:=]?\s*$", prefix) is not None


def _normalized_row_identity(source: bytes, context: tuple[str, int, int],
                             fields: list[tuple[str, tuple[str, int, int]]]) -> list[str]:
    """Return the validated physical row with selected numeric values masked.

    Keeping the nonnumeric source text distinguishes separate groups/scopes while
    masking printed operands makes precision aliases (for example 6% and 5.9%)
    identify the same row. Exact duplicate normalized rows intentionally collapse
    conservatively because their distinct meaning cannot be established from bytes.
    """
    cursor = context[1]
    parts = []
    for name, span in sorted(fields, key=lambda item: item[1][1]):
        if span[1] < cursor or span[2] > context[2]:
            reject("RELATION_VALUE_SPANS_OVERLAP")
        try:
            text = source[cursor:span[1]].decode("utf-8")
        except UnicodeDecodeError:
            reject("SOURCE_ENCODING_INVALID")
        parts.extend((" ".join(text.casefold().split()), name))
        cursor = span[2]
    try:
        tail = source[cursor:context[2]].decode("utf-8")
    except UnicodeDecodeError:
        reject("SOURCE_ENCODING_INVALID")
    parts.append(" ".join(tail.casefold().split()))
    return parts


def _legacy_relationship_key(document_id: str, relation: dict[str, Any]) -> str:
    percentage_value = str(relation["percentage"])
    if "." in percentage_value:
        whole, _, fraction = percentage_value.partition(".")
        fraction = fraction.rstrip("0")
        percentage_value = whole + ("." + fraction if fraction else "")
    return sha256_bytes(canonical_bytes({
        "document_id": document_id,
        "numerator": relation["numerator"],
        "denominator": relation["denominator"],
        "percentage": percentage_value,
    }))


def _validate_relationship(source: bytes, raw: object, *,
                          additional_numeric_spans: tuple[tuple[str, int, int], ...] = ()) -> dict[str, Any]:
    relation = require_keys(raw, {
        "table_locator_span", "object_locator_span", "context_span",
        "numerator_span", "denominator_span", "percentage_span",
        "scope_span", "scope_status",
    })
    if (not isinstance(relation["scope_status"], str)
        or relation["scope_status"] not in {SCOPE_STATUS, "UNRESOLVED", "DISPUTED"}):
        reject("INVALID_SCOPE_STATUS")
    context = validate_span(source, relation["context_span"])
    table_locator = validate_span(source, relation["table_locator_span"])
    object_locator = validate_span(source, relation["object_locator_span"])
    numerator = validate_span(source, relation["numerator_span"])
    denominator = validate_span(source, relation["denominator_span"])
    percentage = validate_span(source, relation["percentage_span"])
    scope = validate_span(source, relation["scope_span"])
    for span in (table_locator, object_locator, numerator, denominator, percentage, scope):
        require_nested_span(context, span)

    # The v5 eligibility profile is deliberately narrow: a complete relation
    # must occupy one physical source line. Every decimal digit must be covered
    # by the table identifier, one selected operand, or (for a correction)
    # one explicitly mapped old value. This prevents borrowing operands from
    # another row or leaving a competing numeric value hidden in a broad quote.
    if b"\n" in context[0].encode("utf-8") or b"\r" in context[0].encode("utf-8"):
        reject("RELATION_CONTEXT_NOT_EXACT_SOURCE_LINE")
    if _line_bounds(source, context[1]) != (context[1], context[2]):
        reject("RELATION_CONTEXT_NOT_EXACT_SOURCE_LINE")
    if not re.fullmatch(r"(?i)(?:supplementary\s+)?table\s+(?:s?[0-9]+|[ivxlcdm]+)[a-z]?", table_locator[0]):
        reject("TABLE_LOCATOR_NOT_EXPLICIT")
    if re.search(r"[0-9%]", object_locator[0] + scope[0]):
        reject("NUMERIC_OBJECT_OR_SCOPE_LABEL_UNRESOLVED")
    numeric_operands = sorted((numerator, denominator, percentage, *additional_numeric_spans),
                              key=lambda item: item[1])
    if any(first[2] > second[1] for first, second in zip(numeric_operands, numeric_operands[1:])):
        reject("RELATION_VALUE_SPANS_OVERLAP")
    if any(max(table_locator[1], value[1]) < min(table_locator[2], value[2])
           for value in numeric_operands):
        reject("TABLE_LOCATOR_OVERLAPS_RELATION_VALUE")
    if not _has_explicit_count_cue(source, numerator):
        reject("NUMERATOR_COUNT_CUE_NOT_EXPLICIT")
    for extra in additional_numeric_spans:
        require_nested_span(context, extra)

    covered = bytearray(context[2] - context[1])
    for selected in (table_locator, numerator, denominator, percentage, *additional_numeric_spans):
        begin = selected[1] - context[1]
        end = selected[2] - context[1]
        covered[begin:end] = b"\x01" * (end - begin)
    context_bytes = source[context[1]:context[2]]
    if any((48 <= value <= 57 or value == ord("%")) and not covered[index]
           for index, value in enumerate(context_bytes)):
        reject("SOURCE_RELATION_HAS_UNMAPPED_NUMERIC_VALUE")

    n = parse_count_span(numerator[0])
    d = parse_count_span(denominator[0], explicit_denominator=True)
    printed, places = parse_percent_span(percentage[0])
    arithmetic = computed_percent(n, d, printed, places)
    row_identity = _normalized_row_identity(source, context, [
        ("table", table_locator),
        ("numerator", numerator),
        ("denominator", denominator),
        ("percentage", percentage),
        *((f"correction-old-{index}", span) for index, span in enumerate(
            sorted(additional_numeric_spans, key=lambda item: item[1]))),
    ])
    return {
        "table_locator": _normalize_context(table_locator[0]),
        "object_locator": _normalize_context(object_locator[0]),
        "context": _normalize_context(context[0]),
        "scope": _normalize_context(scope[0]),
        "operand_spans": {
            "numerator": [numerator[1], numerator[2]],
            "denominator": [denominator[1], denominator[2]],
            "percentage": [percentage[1], percentage[2]],
        },
        "numerator": n,
        "denominator": d,
        "percentage": printed,
        "decimals": places,
        "row_identity": row_identity,
        "arithmetic": arithmetic,
    }


def _parse_changed_value(field: str, span: tuple[str, int, int]) -> Any:
    if field == "numerator":
        return parse_count_span(span[0])
    if field == "denominator":
        return parse_count_span(span[0], explicit_denominator=True)
    if field == "percentage":
        return parse_percent_span(span[0])
    reject("INVALID_CORRECTION_FIELD")


def _review_validation(raw: object, root: Path,
                       source_index: dict[str, list[dict[str, Any]]]) -> tuple[dict, dict]:
    obj = require_keys(raw, {
        "schema_version", "review_id", "role", "eligibility", "document_id",
        "source_sha256", "source_version", "correction_sha256",
        "correction_source_version", "source_version_status", "relationship",
        "correction_binding", "objections",
    })
    if obj["schema_version"] != REVIEW_VERSION:
        reject("UNSUPPORTED_REVIEW_VERSION")
    id_valid(obj["review_id"])
    if (not isinstance(obj["role"], str) or obj["role"] not in REVIEW_ROLES
        or not isinstance(obj["eligibility"], str) or obj["eligibility"] not in REVIEW_ELIGIBILITY):
        reject("INVALID_REVIEW_CLASSIFICATION")
    document_id = normalize_doi(obj["document_id"])
    if obj["document_id"] != document_id:
        reject("IDENTIFIER_NOT_CANONICAL")
    objections = obj["objections"]
    if not isinstance(objections, list) or len(objections) > 24 or any(
        not isinstance(value, str) or len(value) > MAX_ANCHOR_CHARS or "\x00" in value
        for value in objections
    ):
        reject("INVALID_OBJECTIONS")
    source_record, source = _matching_source(
        root, source_index, obj["source_sha256"], "original",
        document_id, obj["source_version"],
    )
    relation = _validate_relationship(source, obj["relationship"])
    expected_use = (
        "NOT_APPLICABLE_SYNTHETIC" if within(root, DEV_PARENT)
        else "CUSTODIAN_CONFIRMED_PUBLIC_USE"
    )
    if not isinstance(obj["source_version_status"], str) or obj["source_version_status"] not in {
        SOURCE_VERSION_STATUS, "UNRESOLVED", "DISPUTED",
    }:
        reject("INVALID_SOURCE_VERSION_STATUS")
    if obj["eligibility"] == "ELIGIBLE":
        if (obj["source_version_status"] != SOURCE_VERSION_STATUS
            or obj["relationship"]["scope_status"] != SCOPE_STATUS
            or objections):
            reject("ELIGIBILITY_NOT_ESTABLISHED")
        if source_record["provenance"]["public_use_status"] != expected_use:
            reject("SOURCE_PUBLIC_USE_NOT_ESTABLISHED")

    correction_digest = obj["correction_sha256"]
    correction_version = obj["correction_source_version"]
    correction_relation = None
    correction_arithmetic = None
    correction_source_record = None
    if obj["role"] == "CORRECTION_POSITIVE":
        if correction_digest is None or not isinstance(correction_version, str) or not correction_version:
            reject("CORRECTION_EVIDENCE_REQUIRED")
        correction_source_record, correction_source = _matching_source(
            root, source_index, correction_digest, "correction",
            document_id, correction_version,
        )
        if (obj["eligibility"] == "ELIGIBLE"
            and correction_source_record["provenance"]["public_use_status"] != expected_use):
            reject("CORRECTION_PUBLIC_USE_NOT_ESTABLISHED")
        binding = obj["correction_binding"]
        if obj["eligibility"] == "ELIGIBLE":
            binding = require_keys(binding, {
                "statement_span", "corrected_relation", "old_value_spans",
                "changed_fields", "mapping_status",
            })
            statement = validate_span(correction_source, binding["statement_span"])
            if (b"\n" in statement[0].encode("utf-8") or b"\r" in statement[0].encode("utf-8")
                    or _line_bounds(correction_source, statement[1]) != (statement[1], statement[2])):
                reject("CORRECTION_STATEMENT_NOT_EXACT_SOURCE_LINE")
            changed = binding["changed_fields"]
            old_spans = binding["old_value_spans"]
            if (not isinstance(changed, list) or not changed
                or any(not isinstance(field, str) for field in changed)
                or len(changed) != len(set(changed))
                or set(changed) - RELATION_FIELDS
                or not isinstance(old_spans, dict) or set(old_spans) != set(changed)):
                reject("INVALID_CORRECTION_CHANGED_FIELDS")
            corrected_raw = require_keys(binding["corrected_relation"], {
                "table_locator_span", "object_locator_span", "context_span",
                "numerator_span", "denominator_span", "percentage_span",
                "scope_span", "scope_status",
            })
            corrected_context = validate_span(
                correction_source, corrected_raw["context_span"],
            )
            require_nested_span(statement, corrected_context)
            corrected_span_names = {
                "numerator": "numerator_span",
                "denominator": "denominator_span",
                "percentage": "percentage_span",
            }
            validated_old_spans = {}
            for field, raw_span in old_spans.items():
                old_span = validate_span(correction_source, raw_span)
                require_nested_span(statement, old_span)
                corrected_span = validate_span(correction_source, corrected_raw[corrected_span_names[field]])
                if max(old_span[1], corrected_span[1]) < min(old_span[2], corrected_span[2]):
                    reject("CORRECTION_OLD_VALUE_OVERLAPS_CORRECTED_VALUE")
                validated_old_spans[field] = old_span
            correction_relation = _validate_relationship(
                correction_source, corrected_raw,
                additional_numeric_spans=tuple(validated_old_spans.values()),
            )
            if binding["corrected_relation"]["scope_status"] != SCOPE_STATUS:
                reject("CORRECTION_SCOPE_NOT_CONFIRMED")
            if (relation["table_locator"] != correction_relation["table_locator"]
                or relation["object_locator"] != correction_relation["object_locator"]
                or relation["scope"] != correction_relation["scope"]):
                reject("CORRECTION_RELATION_SCOPE_MISMATCH")
            if binding["mapping_status"] != CORRECTION_STATUS:
                reject("CORRECTION_MAPPING_NOT_CONFIRMED")
            old_values = {
                "numerator": relation["numerator"],
                "denominator": relation["denominator"],
                "percentage": (relation["percentage"], relation["decimals"]),
            }
            new_values = {
                "numerator": correction_relation["numerator"],
                "denominator": correction_relation["denominator"],
                "percentage": (correction_relation["percentage"], correction_relation["decimals"]),
            }
            if any(old_values[field] == new_values[field] for field in changed):
                reject("CORRECTION_DOES_NOT_CHANGE_RELATION")
            actual_changed = {field for field in RELATION_FIELDS if old_values[field] != new_values[field]}
            if set(changed) != actual_changed:
                reject("CORRECTION_CHANGED_FIELDS_NOT_EXACT")
            for field in changed:
                old_span = validated_old_spans[field]
                corrected_field_span = validate_span(
                    correction_source,
                    binding["corrected_relation"][{
                        "numerator": "numerator_span",
                        "denominator": "denominator_span",
                        "percentage": "percentage_span",
                    }[field]],
                )
                require_nested_span(statement, corrected_field_span)
                expected_old = old_values[field]
                expected_new = new_values[field]
                if _parse_changed_value(field, old_span) != expected_old:
                    reject("CORRECTION_OLD_VALUE_NOT_IN_ORIGINAL")
                if _parse_changed_value(field, corrected_field_span) != expected_new:
                    reject("CORRECTION_NEW_VALUE_NOT_IN_CORRECTED_RELATION")
                if expected_old == expected_new:
                    reject("CORRECTION_DOES_NOT_CHANGE_RELATION")
            if relation["arithmetic"]["matches"]:
                reject("POSITIVE_HAS_NO_ORIGINAL_ARITHMETIC_DISCREPANCY")
            if not correction_relation["arithmetic"]["matches"]:
                reject("CORRECTION_DOES_NOT_RESOLVE_ARITHMETIC")
            correction_arithmetic = correction_relation["arithmetic"]
        elif binding is not None:
            reject("CORRECTION_BINDING_REQUIRES_ELIGIBILITY")
    else:
        if correction_digest is not None or correction_version is not None or obj["correction_binding"] is not None:
            reject("UNEXPECTED_CORRECTION_EVIDENCE")
        if obj["role"] == "CORRECT_NEGATIVE_RELATION" and obj["eligibility"] == "ELIGIBLE":
            if not relation["arithmetic"]["matches"]:
                reject("NEGATIVE_LABEL_NOT_ARITHMETICALLY_CORRECT")
        elif obj["role"] == "OTHER" and obj["eligibility"] == "ELIGIBLE":
            reject("OTHER_RELATION_CANNOT_BE_ELIGIBLE")

    if obj["role"] == "CORRECTION_POSITIVE" and obj["eligibility"] == "ELIGIBLE":
        if not correction_relation:
            reject("CORRECTION_MAPPING_REQUIRED")
    if obj["eligibility"] == "ELIGIBLE" and obj["role"] not in {
        "CORRECTION_POSITIVE", "CORRECT_NEGATIVE_RELATION",
    }:
        reject("OTHER_RELATION_CANNOT_BE_ELIGIBLE")

    # Identity comes from the immutable source row, not reviewer-selected spans
    # or only its numeric tuple. This keeps equal-valued, differently labelled
    # rows distinct and collapses precision aliases of the same row.
    canonical_table = _canonical_table_locator(relation["table_locator"])
    row_content_key = sha256_bytes(canonical_bytes({
        "document_id": document_id,
        "source_row": relation["row_identity"],
    }))
    fingerprint_material = {
        "document_id": document_id,
        # Table locators are selected and validated against the physical row,
        # but are masked in row_identity alongside the numeric operands. Keep
        # the validated locator as a separate identity component so otherwise
        # identical rows in different tables remain distinct.
        "source_table": canonical_table,
        "source_row": relation["row_identity"],
    }
    relationship_key = sha256_bytes(canonical_bytes(fingerprint_material))
    legacy_relationship_key = _legacy_relationship_key(document_id, relation)
    version_key = (document_id, obj["source_version"])
    table_key = (document_id, obj["source_version"], canonical_table)
    positive_issue_key = None
    if correction_source_record is not None:
        # Without an independently validated correction-article identifier,
        # multiple correction source IDs for one paper cannot be treated as
        # distinct issues. Count at most one positive issue per DOI document.
        positive_issue_key = document_id
    details = {
        "relationship_key": relationship_key,
        "legacy_relationship_key": legacy_relationship_key,
        "row_content_key": row_content_key,
        "canonical_table_locator": canonical_table,
        "version_key": version_key,
        "table_key": table_key,
        "positive_issue_key": positive_issue_key,
        "source_document_id": document_id,
        "original_arithmetic": relation["arithmetic"],
        "corrected_arithmetic": correction_arithmetic,
    }
    return obj, details


def _read_existing_reviews(root: Path, source_index: dict[str, list[dict[str, Any]]]) -> list[dict]:
    result = []
    directory = root / "manifests" / "reviews"
    synthetic_only = within(root, DEV_PARENT)
    expected_actor = "SYNTHETIC_DEVELOPMENT" if synthetic_only else "rw-custodian"
    for path in _iter_json_files(directory, r"[a-z][a-z0-9-]{2,63}\.json"):
        record = require_keys(read_json(path), {
            "schema_version", "review", "checked", "recorded_by", "recorded_at_utc",
        })
        record_version = record["schema_version"]
        if record_version not in {LEGACY_REVIEW_RECORD_VERSION, REVIEW_RECORD_VERSION}:
            reject("REVIEW_RECORD_VERSION_UNSUPPORTED")
        if record["recorded_by"] != expected_actor:
            reject("REVIEW_RECORD_ACTOR_INVALID")
        validate_utc_timestamp(record["recorded_at_utc"])
        review, details = _review_validation(record["review"], root, source_index)
        if review["review_id"] != path.stem or checked_read(path) != canonical_bytes(record):
            reject("REVIEW_LEDGER_CORRUPT")
        expected = {
            "original_arithmetic": details["original_arithmetic"],
            "corrected_arithmetic": details["corrected_arithmetic"],
            "relationship_key": (
                details["legacy_relationship_key"]
                if record_version == LEGACY_REVIEW_RECORD_VERSION
                else details["relationship_key"]
            ),
        }
        if record["checked"] != expected:
            reject("REVIEW_LEDGER_CORRUPT")
        result.append({
            "review": review, "details": details, "record_version": record_version,
        })
    return result


def _reject_duplicate_current_relationship_keys(rows: list[dict]) -> None:
    # V4 records may contain precision aliases the old key kept separate.
    # Preserve and verify those immutable records, then collapse them in the
    # aggregate set. A duplicate involving a new v5 key is an integrity error.
    entries_by_key: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        key = row["details"]["relationship_key"]
        entries_by_key.setdefault(key, []).append((
            row["record_version"], row["details"]["legacy_relationship_key"],
        ))
    for entries in entries_by_key.values():
        if len(entries) <= 1:
            continue
        if any(version == REVIEW_RECORD_VERSION for version, _ in entries):
            reject("DUPLICATE_CANONICAL_RELATIONSHIP")
        legacy_keys = [legacy_key for _, legacy_key in entries]
        if len(legacy_keys) != len(set(legacy_keys)):
            reject("DUPLICATE_CANONICAL_RELATIONSHIP")

    # If otherwise identical rows are present in more than one source version,
    # a changed table label cannot be treated as either a new relation or a
    # duplicate without an independently established table lineage. Refuse to
    # aggregate that ambiguous version pair instead of inflating the count.
    locations_by_row: dict[str, dict[tuple[str, str], set[str]]] = {}
    for row in rows:
        details = row["details"]
        versions = locations_by_row.setdefault(details["row_content_key"], {})
        versions.setdefault(details["version_key"], set()).add(
            details["canonical_table_locator"],
        )
    for locations in locations_by_row.values():
        if len(locations) > 1 and len({tuple(sorted(value)) for value in locations.values()}) > 1:
            reject("SOURCE_TABLE_LINEAGE_UNRESOLVED")


def _existing_relationship_keys(root: Path, source_index: dict[str, list[dict[str, Any]]],
                                candidate: dict[str, Any] | None = None) -> set[str]:
    rows = _read_existing_reviews(root, source_index)
    _reject_duplicate_current_relationship_keys(rows + ([candidate] if candidate else []))
    return {row["details"]["relationship_key"] for row in rows}


def import_batch(root: Path, batch_id: str) -> dict:
    root = authorize_store_root(root)
    id_valid(batch_id)
    with _store_lock(root):
        manifest_path = root / "incoming" / (batch_id + ".json")
        manifest = _manifest_validation(
            read_json(safe_source_file(manifest_path, root / "incoming")),
            synthetic_only=within(root, DEV_PARENT),
        )
        if manifest["batch_id"] != batch_id:
            reject("BATCH_ID_MISMATCH")
        manifest_bytes = canonical_bytes(manifest)
        existing_path = root / "manifests" / "imports" / (batch_id + ".json")
        if existing_path.exists():
            if checked_read(existing_path) != manifest_bytes:
                reject("IMMUTABLE_RECORD_CONFLICT")
            _verify_all(root)
            return {
                "status": "ALREADY_IMPORTED",
                "file_count": len(manifest["files"]),
                "manifest_sha256": sha256_bytes(manifest_bytes),
            }
        current_sources = _source_index(root)
        current_versions: dict[tuple[str, str, str, str], set[str]] = {}
        for digest, entries in current_sources.items():
            for entry in entries:
                key = (
                    entry["document_id"], entry["source_id"],
                    entry["source_version"], entry["role"],
                )
                current_versions.setdefault(key, set()).add(digest)
        for item in manifest["files"]:
            key = (
                item["document_id"], item["source_id"],
                item["source_version"], item["role"],
            )
            prior = current_versions.get(key, set())
            if prior and item["sha256"] not in prior:
                reject("SOURCE_VERSION_CONTENT_CONFLICT")
        blobs: dict[str, bytes] = {}
        for item in manifest["files"]:
            path = safe_source_file(root / "incoming" / item["name"], root / "incoming")
            data = checked_read(path, max_bytes=MAX_SOURCE_BYTES)
            if len(data) != item["size"] or sha256_bytes(data) != item["sha256"]:
                reject("SOURCE_HASH_OR_SIZE_MISMATCH")
            blobs[item["sha256"]] = data
        for digest, data in sorted(blobs.items()):
            _immutable_write(root, root / "objects" / "sha256" / digest, data)
        _immutable_write(root, existing_path, manifest_bytes)
        return {
            "status": "IMPORTED",
            "file_count": len(manifest["files"]),
            "manifest_sha256": sha256_bytes(manifest_bytes),
        }


def record_review(root: Path, review_id: str) -> dict:
    root = authorize_store_root(root)
    id_valid(review_id)
    with _store_lock(root):
        raw = read_json(safe_source_file(root / "incoming" / (review_id + ".json"), root / "incoming"))
        source_index = _source_index(root)
        review, details = _review_validation(raw, root, source_index)
        if review["review_id"] != review_id:
            reject("REVIEW_ID_MISMATCH")
        candidate = {"details": details, "record_version": REVIEW_RECORD_VERSION}
        if details["relationship_key"] in _existing_relationship_keys(root, source_index, candidate):
            reject("DUPLICATE_CANONICAL_RELATIONSHIP")
        record = {
            "schema_version": REVIEW_RECORD_VERSION,
            "review": review,
            "checked": {
                "original_arithmetic": details["original_arithmetic"],
                "corrected_arithmetic": details["corrected_arithmetic"],
                "relationship_key": details["relationship_key"],
            },
            "recorded_by": "SYNTHETIC_DEVELOPMENT" if within(root, DEV_PARENT) else "rw-custodian",
            "recorded_at_utc": utc_now(),
        }
        _immutable_write(
            root, root / "manifests" / "reviews" / (review_id + ".json"),
            canonical_bytes(record),
        )
        return {"status": "RECORDED"}


def verify_all(root: Path) -> dict:
    root = authorize_store_root(root)
    with _store_lock(root):
        return _verify_all(root)


def _verify_all(root: Path) -> dict:
    source_index = _source_index(root)
    file_count = sum(len(entries) for entries in source_index.values())
    source_documents = {
        item["document_id"] for entries in source_index.values() for item in entries
    }
    versions = {
        (item["document_id"], item["source_version"])
        for entries in source_index.values() for item in entries if item["role"] == "original"
    }
    rows = _read_existing_reviews(root, source_index)
    _reject_duplicate_current_relationship_keys(rows)

    positive_relations: set[str] = set()
    positive_issues: set[str] = set()
    negative_relations: set[str] = set()
    negative_document_ids: set[str] = set()
    negative_tables: set[tuple[str, str, str]] = set()
    negative_versions: set[tuple[str, str]] = set()
    arithmetic_mismatches = 0
    unresolved = 0
    ineligible = 0
    for row in rows:
        review = row["review"]
        details = row["details"]
        if review["eligibility"] == "UNRESOLVED":
            unresolved += 1
        elif review["eligibility"] == "INELIGIBLE":
            ineligible += 1
        elif review["eligibility"] == "ELIGIBLE":
            if review["role"] == "CORRECTION_POSITIVE":
                positive_relations.add(details["relationship_key"])
                positive_issues.add(details["positive_issue_key"])
                arithmetic_mismatches += 1
            elif review["role"] == "CORRECT_NEGATIVE_RELATION":
                negative_relations.add(details["relationship_key"])
                negative_document_ids.add(details["source_document_id"])
                negative_tables.add(details["table_key"])
                negative_versions.add(details["version_key"])

    return {
        "schema_version": SUMMARY_VERSION,
        "import_batches": len(_iter_json_files(root / "manifests" / "imports", r"[a-z][a-z0-9-]{2,63}\.json")),
        "import_files": file_count,
        "source_documents": len(source_documents),
        "source_versions": len(versions),
        "reviews": len(rows),
        "eligible_positive_issues": len(positive_issues),
        "eligible_positive_relations": len(positive_relations),
        "eligible_negative_relations": len(negative_relations),
        "eligible_negative_document_ids": len(negative_document_ids),
        "eligible_negative_tables": len(negative_tables),
        "eligible_negative_versions": len(negative_versions),
        "arithmetic_mismatches": arithmetic_mismatches,
        "unresolved": unresolved,
        "ineligible": ineligible,
        "meaning": "Custodian-adjudicated source-bound relationships; not detector results or source authentication",
    }


def _inventory_snapshot(root: Path, counts: dict) -> dict:
    entries = []
    for directory in ("imports", "reviews"):
        for path in _iter_json_files(
            root / "manifests" / directory, r"[a-z][a-z0-9-]{2,63}\.json"
        ):
            entries.append({
                "path": f"manifests/{directory}/{path.name}",
                "sha256": sha256_bytes(checked_read(path)),
            })
    return {"schema_version": SEAL_VERSION, "inventory_records": entries, "inventory_counts": counts}


def _inventory_commitment(root: Path, snapshot: dict) -> str:
    return hmac.new(_commitment_key(root), canonical_bytes(snapshot), hashlib.sha256).hexdigest()


def seal_inventory(root: Path) -> dict:
    root = authorize_store_root(root)
    with _store_lock(root):
        counts = _verify_all(root)
        snapshot = _inventory_snapshot(root, counts)
        digest = _inventory_commitment(root, snapshot)
        content = canonical_bytes({
            "schema_version": SEAL_VERSION,
            "commitment": digest,
            "snapshot": snapshot,
        })
        _immutable_write(root, root / "sealed-labels" / ("seal-" + digest + ".json"), content)
        return {"status": "SEALED", "seal_sha256": digest,
                "inventory_record_count": len(snapshot["inventory_records"])}


def _validate_summary(summary: object) -> dict:
    keys = {
        "schema_version", "import_batches", "import_files", "source_documents",
        "source_versions", "reviews", "eligible_positive_issues",
        "eligible_positive_relations", "eligible_negative_relations",
        "eligible_negative_document_ids", "eligible_negative_tables",
        "eligible_negative_versions", "arithmetic_mismatches", "unresolved",
        "ineligible", "meaning", "seal_count", "current_inventory_sealed",
        "current_seal_commitment",
    }
    obj = require_keys(summary, keys)
    if obj["schema_version"] != SUMMARY_VERSION or not isinstance(obj["meaning"], str):
        reject("SUMMARY_SCHEMA_INVALID")
    for key in keys - {"schema_version", "meaning"}:
        if key in {"current_inventory_sealed", "current_seal_commitment"}:
            continue
        bounded_int(obj[key], maximum=1_000_000_000)
    if type(obj["current_inventory_sealed"]) is not bool:
        reject("SUMMARY_SCHEMA_INVALID")
    commitment = obj["current_seal_commitment"]
    if commitment is not None:
        hash_valid(commitment)
    return obj


def summarize(root: Path) -> dict:
    root = authorize_store_root(root)
    with _store_lock(root):
        return _summarize(root)


def _summarize(root: Path) -> dict:
    counts = _verify_all(root)
    seal_files = _iter_json_files(
        root / "sealed-labels", r"seal-[0-9a-f]{64}\.json", max_file_bytes=MAX_SEAL_BYTES
    )
    current_commitment = _inventory_commitment(root, _inventory_snapshot(root, counts))
    known: set[str] = set()
    for path in seal_files:
        data = checked_read(path, max_bytes=MAX_SEAL_BYTES)
        digest = path.stem.removeprefix("seal-")
        record = require_keys(strict_json_bytes(data), {"schema_version", "commitment", "snapshot"})
        if record["schema_version"] != SEAL_VERSION or record["commitment"] != digest:
            reject("SEAL_UNSUPPORTED_OR_CORRUPT")
        snapshot = require_keys(record["snapshot"], {"schema_version", "inventory_records", "inventory_counts"})
        if snapshot["schema_version"] != SEAL_VERSION or _inventory_commitment(root, snapshot) != digest:
            reject("SEAL_CORRUPT")
        known.add(digest)
    has_current = current_commitment in known
    result = {
        **counts,
        "seal_count": len(known),
        "current_inventory_sealed": has_current,
        "current_seal_commitment": current_commitment if has_current else None,
    }
    return result


def export_public_summary(root: Path) -> dict:
    """Export only schema-checked threshold aggregates and a keyed commitment."""
    root = authorize_store_root(root)
    with _store_lock(root):
        summary = _validate_summary(_summarize(root))
        if not summary["current_inventory_sealed"]:
            reject("PUBLIC_EXPORT_REQUIRES_SEALED_INVENTORY")
        positives = summary["eligible_positive_issues"] >= 1
        negatives = summary["eligible_negative_relations"] >= 50
        document_ids = summary["eligible_negative_document_ids"] >= 15
        if not (positives and negatives and document_ids):
            reject("PUBLIC_EXPORT_THRESHOLDS_NOT_MET")
        public = {
            "schema_version": PUBLIC_SUMMARY_VERSION,
            "eligible_positive_cases": "AT_LEAST_1" if positives else "BELOW_1",
            "eligible_negative_relationships": "AT_LEAST_50" if negatives else "BELOW_50",
            "distinct_negative_document_ids": "AT_LEAST_15" if document_ids else "BELOW_15",
            "minimum_count_thresholds_met": positives and negatives and document_ids,
            "inventory_sealed": True,
            "integrity_commitment": summary["current_seal_commitment"],
            "meaning": "Counts distinct custodian-supplied DOI IDs, not alias-resolved independent works; not a Wave 3 result or performance claim",
        }
        _validate_public_summary(public)
        export_path = root / "audit" / "public-export.json"
        record = {
            "schema_version": PUBLIC_EXPORT_VERSION,
            "inventory_commitment": summary["current_seal_commitment"],
            "public_summary": public,
        }
        if export_path.exists() or export_path.is_symlink():
            existing = require_keys(read_json(export_path), {
                "schema_version", "inventory_commitment", "public_summary",
            })
            if existing != record:
                reject("PUBLIC_EXPORT_ALREADY_ISSUED")
            return _validate_public_summary(existing["public_summary"])
        _immutable_write(root, export_path, canonical_bytes(record))
        return public


def _validate_public_summary(value: object) -> dict:
    public = require_keys(value, {
        "schema_version", "eligible_positive_cases", "eligible_negative_relationships",
        "distinct_negative_document_ids", "minimum_count_thresholds_met",
        "inventory_sealed", "integrity_commitment", "meaning",
    })
    if public["schema_version"] != PUBLIC_SUMMARY_VERSION:
        reject("PUBLIC_SUMMARY_SCHEMA_INVALID")
    if public["eligible_positive_cases"] not in {"AT_LEAST_1", "BELOW_1"}:
        reject("PUBLIC_SUMMARY_SCHEMA_INVALID")
    if public["eligible_negative_relationships"] not in {"AT_LEAST_50", "BELOW_50"}:
        reject("PUBLIC_SUMMARY_SCHEMA_INVALID")
    if public["distinct_negative_document_ids"] not in {"AT_LEAST_15", "BELOW_15"}:
        reject("PUBLIC_SUMMARY_SCHEMA_INVALID")
    if (type(public["minimum_count_thresholds_met"]) is not bool
        or public["inventory_sealed"] is not True):
        reject("PUBLIC_SUMMARY_SCHEMA_INVALID")
    hash_valid(public["integrity_commitment"])
    if not isinstance(public["meaning"], str) or len(public["meaning"]) > 240:
        reject("PUBLIC_SUMMARY_SCHEMA_INVALID")
    meets = (
        public["eligible_positive_cases"] == "AT_LEAST_1"
        and public["eligible_negative_relationships"] == "AT_LEAST_50"
        and public["distinct_negative_document_ids"] == "AT_LEAST_15"
    )
    if public["minimum_count_thresholds_met"] is not meets:
        reject("PUBLIC_SUMMARY_SCHEMA_INVALID")
    return public
