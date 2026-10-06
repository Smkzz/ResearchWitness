#!/usr/bin/env python3
"""Score a locked ResearchWitness paper-audit wave-2 run after lock commit.

The scorer fails closed unless LOCK.json and every listed raw output are
tracked, committed, unchanged, and hash-valid. It verifies all listed output
hashes before opening either the separate ground-truth file or the separate
post-lock adjudication file. It never reads source papers or extracted text.

CLI:

    python tools/score_paper_audit_wave_2.py \
      --lock validation/paper-audit-wave-2/results/LOCK.json \
      --ground-truth /separate/custody/GROUND_TRUTH.json \
      --adjudication /separate/custody/ADJUDICATION.json \
      --output validation/paper-audit-wave-2/results/scoring-summary.json

The lock contract is recorded in
validation/paper-audit-wave-2/SCORING_RULES.json. In brief, the lock names
opaque paper IDs and a ``raw_outputs`` array. Every raw-output record has a
repository-relative ``path``, exact-byte lowercase SHA-256 ``sha256``, and
``kind`` (``report_json``, ``report_html``, ``run_metadata``, or
``source_metadata``). Report records also have ``paper_id`` and ``run_id``;
each paper must have JSON and HTML reports for both ``run-1`` and ``run-2``.

Ground truth supplies paper roles and positive issues with target candidate
types, exact operand fields, and required source anchors. Adjudication binds to
the lock bytes through ``lock_sha256`` and supplies one disposition for every
run-1 candidate plus one of useful/benign/misleading/false for every run-1
scope note. The primary scoring run is run-1; run-2 is used for exact-byte
repeatability comparisons.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


EVALUATION_WAVE = "paper-audit-wave-2"
BASELINE_COMMIT = "3042b3d62b8f20cc646b0c121dff376bfdd201cb"
BASELINE_TREE_SHA = "a19c53c2c2e6c400ee8b0d7feb0d0261f0cf009f"
SCORING_RULES_VERSION = "1.0"
LOCK_VERSION = 1
INPUT_SCHEMA_VERSION = 1
PAPER_AUDIT_VERSION = "0.2"
RUN_IDS = ("run-1", "run-2")
RUNNER_PATH = "tools/run_paper_audit_wave_2_blind.py"
PACKAGE_VERSION = "0.4.0.dev0"
LOCK_FIELDS = frozenset((
    "lock_version", "evaluation_wave", "status", "frozen_baseline_commit",
    "frozen_baseline_tree_sha", "package_version", "paper_audit_schema_version",
    "execution_environment", "renderer_version", "renderer_sha256", "source_manifest",
    "source_manifest_path", "source_manifest_sha256", "runner", "runner_path",
    "runner_sha256", "papers", "raw_outputs", "output_root", "raw_output_count",
    "lock_policy",
))
RUN_METADATA_FIELDS = frozenset((
    "metadata_version", "paper_id", "run_id", "source", "frozen_baseline",
    "execution_environment", "runtime_seconds", "decision", "extraction_status",
    "extraction_warnings", "checks_attempted", "unsupported_checks", "candidate_count",
    "candidate_types", "candidate_type_counts", "file_sha256", "repeatability",
))
RUN_METADATA_SOURCE_FIELDS = frozenset((
    "source_kind", "source_sha256", "staged_input_sha256", "source_version_token",
    "renderer_version", "renderer_sha256",
))
RUN_METADATA_BASELINE_FIELDS = frozenset((
    "commit", "tree_sha", "package_version", "paper_audit_schema_version",
))
EXECUTION_ENVIRONMENT_FIELDS = frozenset(("python_version", "platform", "pypdf_version"))
REPEATABILITY_FIELDS = frozenset((
    "report_json_identical", "report_html_identical", "decision_identical",
    "candidate_types_identical", "repeatable",
))
LOCK_POLICY = (
    "Only report.json, report.html, and per-paper run metadata are retained under output_root; "
    "CLI source copies and extracted text are discarded with temporary directories. The committed "
    "source-only manifest is separately hash-locked as source_metadata."
)
REPORT_KINDS = ("report_json", "report_html")
RAW_KINDS = frozenset((*REPORT_KINDS, "run_metadata", "source_metadata"))
EXTRACTION_STATUSES = frozenset((
    "TEXT_AVAILABLE",
    "PARTIAL_TEXT",
    "NO_EXTRACTABLE_TEXT",
    "PARSER_UNAVAILABLE",
    "MALFORMED_OR_UNSUPPORTED",
    "LIMIT_OR_UNSUPPORTED",
    "RESOURCE_LIMIT_OR_TIMEOUT",
    "WORKER_FAILED",
    "WORKER_PROTOCOL_ERROR",
))
EXTRACTION_FAILURE_STATUSES = frozenset((
    "RESOURCE_LIMIT_OR_TIMEOUT",
    "WORKER_FAILED",
    "WORKER_PROTOCOL_ERROR",
))
EXTRACTION_OUTCOME_STATUSES = {
    "success": frozenset(("TEXT_AVAILABLE",)),
    "degraded": frozenset(("PARTIAL_TEXT",)),
    "unsupported": frozenset((
        "NO_EXTRACTABLE_TEXT",
        "PARSER_UNAVAILABLE",
        "MALFORMED_OR_UNSUPPORTED",
        "LIMIT_OR_UNSUPPORTED",
    )),
    "failed": EXTRACTION_FAILURE_STATUSES,
}
SCOPE_CLASSIFICATIONS = ("useful", "benign", "misleading", "false")
WILSON_Z_95 = 1.959963984540054
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ScoringError(ValueError):
    """An invalid, incomplete, or untrustworthy scoring input."""


def _fail(message: str) -> None:
    raise ScoringError(message)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _nonempty_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{where} must be a non-empty string")
    return value


def _validate_relative_path(value: Any, where: str) -> str:
    value = _nonempty_string(value, where)
    if value.startswith("/") or "\\" in value:
        _fail(f"{where} must be a normalized repository-relative POSIX path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        _fail(f"{where} must be a normalized repository-relative POSIX path")
    return value


def _json_constant(value: str) -> None:
    _fail(f"non-standard JSON numeric value is not allowed: {value}")


def _load_json_bytes(data: bytes, where: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"), parse_constant=_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"{where} is not valid UTF-8 JSON: {exc}")


def _read_json(path: Path, where: str) -> tuple[Any, bytes]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        _fail(f"cannot read {where}: {exc}")
    return _load_json_bytes(data, where), data


def _git_bytes(repo: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        _fail(f"cannot run git while checking committed inputs: {exc}")
    if result.returncode != 0:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        _fail("git could not verify a committed scoring input" + (f": {details}" if details else ""))
    return result.stdout


def _repo_root(lock_path: Path) -> Path:
    if lock_path.is_symlink():
        _fail("LOCK.json must not be a symlink")
    try:
        result = subprocess.run(
            ["git", "-C", str(lock_path.parent.resolve()), "rev-parse", "--show-toplevel"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        _fail(f"cannot run git while checking LOCK.json: {exc}")
    if result.returncode != 0:
        _fail("LOCK.json must be inside a git worktree")
    return Path(result.stdout.strip()).resolve()


def _committed_file_bytes(path: Path, repo: Path, description: str) -> tuple[Path, bytes]:
    try:
        absolute = path.absolute()
        relative = absolute.relative_to(repo)
    except (OSError, ValueError) as exc:
        _fail(f"{description} must exist inside the repository: {path} ({exc})")
    current = repo
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail(f"{description} must not use symlinks: {current}")
    try:
        resolved = absolute.resolve(strict=True)
        resolved.relative_to(repo)
    except (OSError, ValueError) as exc:
        _fail(f"{description} must resolve inside the repository: {path} ({exc})")
    relative_posix = relative.as_posix()
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", relative_posix],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if tracked.returncode != 0:
        _fail(f"{description} is not tracked by git: {relative_posix}")
    committed = _git_bytes(repo, "show", f"HEAD:{relative_posix}")
    try:
        current = resolved.read_bytes()
    except OSError as exc:
        _fail(f"cannot read {description}: {exc}")
    if current != committed:
        _fail(f"{description} differs from its committed HEAD bytes: {relative_posix}")
    return resolved, committed


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_lock(lock: Any) -> tuple[list[str], list[dict[str, Any]]]:
    if not isinstance(lock, dict):
        _fail("LOCK.json top level must be an object")
    if set(lock) != LOCK_FIELDS:
        _fail(f"LOCK.json must contain exactly the runner fields: {sorted(LOCK_FIELDS)}")
    if lock.get("lock_version") != LOCK_VERSION:
        _fail(f"LOCK.json lock_version must equal {LOCK_VERSION}")
    if lock.get("evaluation_wave") != EVALUATION_WAVE:
        _fail(f"LOCK.json evaluation_wave must equal {EVALUATION_WAVE!r}")
    if lock.get("status") != "RAW_OUTPUTS_LOCKED_BEFORE_ADJUDICATION":
        _fail("LOCK.json status must identify the pre-adjudication raw-output lock")
    if lock.get("frozen_baseline_commit") != BASELINE_COMMIT:
        _fail("LOCK.json does not identify the frozen baseline commit")
    if lock.get("frozen_baseline_tree_sha") != BASELINE_TREE_SHA:
        _fail("LOCK.json does not identify the frozen baseline tree")
    if lock.get("package_version") != PACKAGE_VERSION or lock.get("paper_audit_schema_version") != PAPER_AUDIT_VERSION:
        _fail("LOCK.json package or paper-audit schema version differs from the frozen baseline")
    if lock.get("lock_policy") != LOCK_POLICY:
        _fail("LOCK.json lock_policy differs from the frozen runner policy")
    lock_environment = lock.get("execution_environment")
    if not isinstance(lock_environment, dict) or set(lock_environment) != EXECUTION_ENVIRONMENT_FIELDS:
        _fail("LOCK.json execution_environment has unexpected or missing fields")
    _nonempty_string(lock.get("renderer_version"), "LOCK.json renderer_version")
    renderer_hash = lock.get("renderer_sha256")
    if not isinstance(renderer_hash, str) or SHA256_RE.fullmatch(renderer_hash) is None:
        _fail("LOCK.json renderer_sha256 must be a lowercase SHA-256 hex string")
    source_manifest_path = lock.get("source_manifest_path")
    source_manifest_hash = lock.get("source_manifest_sha256")
    source_manifest_path = _validate_relative_path(source_manifest_path, "LOCK.json source_manifest_path")
    if not isinstance(source_manifest_hash, str) or SHA256_RE.fullmatch(source_manifest_hash) is None:
        _fail("LOCK.json source_manifest_sha256 must be a lowercase SHA-256 hex string")
    manifest_pin = lock.get("source_manifest")
    if not isinstance(manifest_pin, dict) or set(manifest_pin) != {"path", "sha256"}:
        _fail("LOCK.json source_manifest must contain only path and sha256")
    if manifest_pin != {"path": source_manifest_path, "sha256": source_manifest_hash}:
        _fail("LOCK.json source_manifest nested pin disagrees with its top-level fields")
    runner_hash = lock.get("runner_sha256")
    if not isinstance(runner_hash, str) or SHA256_RE.fullmatch(runner_hash) is None:
        _fail("LOCK.json runner_sha256 must be a lowercase SHA-256 hex string")
    if lock.get("runner_path") != RUNNER_PATH:
        _fail(f"LOCK.json runner_path must equal {RUNNER_PATH!r}")
    runner_pin = lock.get("runner")
    if not isinstance(runner_pin, dict) or set(runner_pin) != {"path", "sha256"}:
        _fail("LOCK.json runner must contain only path and sha256")
    if runner_pin != {"path": RUNNER_PATH, "sha256": runner_hash}:
        _fail("LOCK.json runner nested pin disagrees with its top-level fields")
    _validate_relative_path(lock.get("output_root"), "LOCK.json output_root")
    papers = lock.get("papers")
    if not isinstance(papers, list) or not papers:
        _fail("LOCK.json papers must be a non-empty array")
    paper_ids: list[str] = []
    for index, entry in enumerate(papers):
        where = f"LOCK.json papers[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"paper_id"}:
            _fail(f"{where} must contain only paper_id (the lock carries no labels)")
        paper_ids.append(_nonempty_string(entry["paper_id"], f"{where}.paper_id"))
    if len(paper_ids) != len(set(paper_ids)):
        _fail("LOCK.json contains duplicate paper IDs")

    records = lock.get("raw_outputs")
    if not isinstance(records, list) or not records:
        _fail("LOCK.json raw_outputs must be a non-empty array")
    if not _is_int(lock.get("raw_output_count")) or lock["raw_output_count"] != len(records):
        _fail("LOCK.json raw_output_count must equal the number of raw_outputs entries")
    seen_paths: set[str] = set()
    report_slots: dict[tuple[str, str, str], dict[str, Any]] = {}
    run_metadata_slots: dict[tuple[str, str], dict[str, Any]] = {}
    paper_set = set(paper_ids)
    for index, record in enumerate(records):
        where = f"LOCK.json raw_outputs[{index}]"
        if not isinstance(record, dict):
            _fail(f"{where} must be an object")
        path_value = _validate_relative_path(record.get("path"), f"{where}.path")
        if path_value in seen_paths:
            _fail(f"duplicate raw-output path: {path_value}")
        seen_paths.add(path_value)
        digest = record.get("sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            _fail(f"{where}.sha256 must be a lowercase SHA-256 hex string")
        kind = record.get("kind")
        if not isinstance(kind, str) or kind not in RAW_KINDS:
            _fail(f"{where}.kind must be one of {sorted(RAW_KINDS)}")
        expected_record_fields = (
            {"path", "sha256", "kind", "paper_id", "run_id"}
            if kind in REPORT_KINDS or kind == "run_metadata"
            else {"path", "sha256", "kind"}
        )
        if set(record) != expected_record_fields:
            _fail(f"{where} must contain exactly these fields: {sorted(expected_record_fields)}")
        if kind in REPORT_KINDS:
            paper_id = _nonempty_string(record.get("paper_id"), f"{where}.paper_id")
            run_id = _nonempty_string(record.get("run_id"), f"{where}.run_id")
            if paper_id not in paper_set:
                _fail(f"{where} references a paper absent from LOCK.json papers")
            if run_id not in RUN_IDS:
                _fail(f"{where}.run_id must be one of {RUN_IDS}")
            slot = (paper_id, run_id, kind)
            if slot in report_slots:
                _fail(f"duplicate raw-output report slot: {slot}")
            report_slots[slot] = record
        else:
            paper_id = record.get("paper_id")
            run_id = record.get("run_id")
            if paper_id is not None and paper_id not in paper_set:
                _fail(f"{where}.paper_id is absent from LOCK.json papers")
            if run_id is not None and run_id not in RUN_IDS:
                _fail(f"{where}.run_id must be one of {RUN_IDS}")
            if kind == "run_metadata":
                paper_id = _nonempty_string(paper_id, f"{where}.paper_id")
                run_id = _nonempty_string(run_id, f"{where}.run_id")
                slot = (paper_id, run_id)
                if slot in run_metadata_slots:
                    _fail(f"duplicate run-metadata slot: {slot}")
                run_metadata_slots[slot] = record

    expected_slots = {
        (paper_id, run_id, kind)
        for paper_id in paper_ids
        for run_id in RUN_IDS
        for kind in REPORT_KINDS
    }
    missing_slots = expected_slots - set(report_slots)
    if missing_slots:
        _fail("LOCK.json is missing required report slots: " + repr(sorted(missing_slots)))
    expected_run_metadata = {(paper_id, run_id) for paper_id in paper_ids for run_id in RUN_IDS}
    missing_metadata = expected_run_metadata - set(run_metadata_slots)
    if missing_metadata:
        _fail("LOCK.json is missing required run-metadata slots: " + repr(sorted(missing_metadata)))
    source_manifest_records = [
        record for record in records
        if record["kind"] == "source_metadata"
        and record["path"] == source_manifest_path
        and record["sha256"] == source_manifest_hash
    ]
    all_source_metadata_records = [record for record in records if record["kind"] == "source_metadata"]
    if len(source_manifest_records) != 1 or len(all_source_metadata_records) != 1:
        _fail("raw_outputs must contain exactly one source_metadata entry, and it must be the pinned source manifest")
    return paper_ids, records


def _verify_all_locked_outputs(
    records: list[dict[str, Any]], repo: Path
) -> tuple[dict[str, bytes], dict[str, Path]]:
    """Read and hash every manifest artifact before any label file is opened."""
    bytes_by_relative_path: dict[str, bytes] = {}
    paths_by_relative_path: dict[str, Path] = {}
    for record in records:
        relative = record["path"]
        path = repo.joinpath(*PurePosixPath(relative).parts)
        resolved, data = _committed_file_bytes(path, repo, "locked raw output")
        actual = _digest(data)
        if actual != record["sha256"]:
            _fail(f"raw-output SHA-256 mismatch for {relative}: expected {record['sha256']}, got {actual}")
        bytes_by_relative_path[relative] = data
        paths_by_relative_path[relative] = resolved
    return bytes_by_relative_path, paths_by_relative_path


def _verify_pinned_manifest_and_runner(
    lock: dict[str, Any],
    paper_ids: list[str],
    records: list[dict[str, Any]],
    raw_bytes: dict[str, bytes],
    repo: Path,
) -> dict[tuple[str, str], dict[str, Any]]:
    manifest_path = lock["source_manifest_path"]
    manifest_data = raw_bytes[manifest_path]
    if _digest(manifest_data) != lock["source_manifest_sha256"]:
        _fail("source manifest SHA-256 does not match LOCK.json")
    runner_path = repo.joinpath(*PurePosixPath(RUNNER_PATH).parts)
    _runner_resolved, runner_data = _committed_file_bytes(runner_path, repo, "wave-2 runner")
    if _digest(runner_data) != lock["runner_sha256"]:
        _fail("wave-2 runner SHA-256 does not match LOCK.json")

    manifest = _load_json_bytes(manifest_data, "committed source-only manifest")
    if not isinstance(manifest, dict) or set(manifest) != {"renderer", "papers"}:
        _fail("source-only manifest may contain only renderer and papers; labels are not allowed")
    if not isinstance(manifest.get("renderer"), str) or not manifest["renderer"]:
        _fail("source-only manifest must have a non-empty renderer string")
    if manifest["renderer"] != lock["renderer_version"]:
        _fail("LOCK.json renderer_version differs from the committed source manifest")
    manifest_papers = manifest.get("papers")
    if not isinstance(manifest_papers, list):
        _fail("source-only manifest papers must be an array")
    source_records: dict[str, dict[str, str]] = {}
    for index, row in enumerate(manifest_papers):
        where = f"source-only manifest papers[{index}]"
        if not isinstance(row, dict):
            _fail(f"{where} must be an object")
        if set(row) != {"paper_id", "source"}:
            _fail(f"{where} may contain only paper_id and source")
        paper_id = _nonempty_string(row.get("paper_id"), f"{where}.paper_id")
        source = row.get("source")
        source_fields = {
            "source_kind", "snapshot_name", "source_url", "retrieved_at",
            "sha256", "source_version", "license",
        }
        if not isinstance(source, dict) or set(source) != source_fields:
            _fail(f"{where}.source must have the source-only manifest fields and no label fields")
        source_sha256 = source.get("sha256")
        if not isinstance(source_sha256, str) or SHA256_RE.fullmatch(source_sha256) is None:
            _fail(f"{where}.source.sha256 must be a lowercase SHA-256 hex string")
        source_kind = _nonempty_string(source.get("source_kind"), f"{where}.source.source_kind")
        if paper_id in source_records:
            _fail(f"duplicate source-manifest paper ID: {paper_id}")
        source_records[paper_id] = {"sha256": source_sha256, "source_kind": source_kind}
    if set(source_records) != set(paper_ids):
        _fail("source-only manifest paper IDs do not exactly match LOCK.json papers")

    metadata_by_slot: dict[tuple[str, str], dict[str, Any]] = {}
    report_hashes = {
        (record["paper_id"], record["run_id"], record["kind"]): record["sha256"]
        for record in records
        if record["kind"] in REPORT_KINDS
    }
    for record in records:
        if record["kind"] != "run_metadata":
            continue
        paper_id = record["paper_id"]
        run_id = record["run_id"]
        metadata = _load_json_bytes(raw_bytes[record["path"]], f"locked run metadata {record['path']}")
        if not isinstance(metadata, dict) or set(metadata) != RUN_METADATA_FIELDS:
            _fail(f"run metadata {record['path']} must contain exactly the frozen runner fields")
        if metadata.get("metadata_version") != 1 or metadata.get("paper_id") != paper_id:
            _fail(f"run metadata {record['path']} does not identify its locked paper_id")
        if metadata.get("run_id") != run_id:
            _fail(f"run metadata {record['path']} run_id differs from its lock entry")
        source = metadata.get("source")
        if not isinstance(source, dict) or set(source) != RUN_METADATA_SOURCE_FIELDS:
            _fail(f"run metadata {record['path']} source must contain exactly the frozen source fields")
        original_sha256 = source.get("source_sha256")
        if original_sha256 != source_records[paper_id]["sha256"]:
            _fail(f"run metadata {record['path']} source hash differs from the source-only manifest")
        if source.get("source_kind") != source_records[paper_id]["source_kind"]:
            _fail(f"run metadata {record['path']} source kind differs from the source-only manifest")
        staged_sha256 = source.get("staged_input_sha256")
        if not isinstance(staged_sha256, str) or SHA256_RE.fullmatch(staged_sha256) is None:
            _fail(f"run metadata {record['path']} source.staged_input_sha256 is invalid")
        _nonempty_string(source.get("source_version_token"), f"run metadata {record['path']} source.source_version_token")
        frozen = metadata.get("frozen_baseline")
        if not isinstance(frozen, dict) or set(frozen) != RUN_METADATA_BASELINE_FIELDS:
            _fail(f"run metadata {record['path']} frozen_baseline must contain exactly the frozen baseline fields")
        if frozen.get("commit") != BASELINE_COMMIT or frozen.get("tree_sha") != BASELINE_TREE_SHA:
            _fail(f"run metadata {record['path']} frozen baseline differs from the preregistered baseline")
        if frozen.get("package_version") != PACKAGE_VERSION or frozen.get("paper_audit_schema_version") != PAPER_AUDIT_VERSION:
            _fail(f"run metadata {record['path']} package/schema pins differ from the frozen baseline")
        environment = metadata.get("execution_environment")
        if not isinstance(environment, dict) or set(environment) != EXECUTION_ENVIRONMENT_FIELDS:
            _fail(f"run metadata {record['path']} execution_environment has unexpected or missing fields")
        if environment != lock["execution_environment"]:
            _fail(f"run metadata {record['path']} environment differs from LOCK.json")
        file_hashes = metadata.get("file_sha256")
        if not isinstance(file_hashes, dict) or set(file_hashes) != {"report.json", "report.html"}:
            _fail(f"run metadata {record['path']} file_sha256 must pin report.json and report.html")
        expected_json_hash = report_hashes[(paper_id, run_id, "report_json")]
        expected_html_hash = report_hashes[(paper_id, run_id, "report_html")]
        if file_hashes.get("report.json") != expected_json_hash or file_hashes.get("report.html") != expected_html_hash:
            _fail(f"run metadata {record['path']} report hashes differ from raw_outputs")
        repeatability = metadata.get("repeatability")
        if not isinstance(repeatability, dict) or set(repeatability) != REPEATABILITY_FIELDS:
            _fail(f"run metadata {record['path']} repeatability has unexpected or missing fields")
        slot = (paper_id, run_id)
        if slot in metadata_by_slot:
            _fail(f"duplicate run metadata for {slot}")
        metadata_by_slot[slot] = metadata
    expected_slots = {(paper_id, run_id) for paper_id in paper_ids for run_id in RUN_IDS}
    if set(metadata_by_slot) != expected_slots:
        _fail("run metadata does not cover every locked paper/run pair")
    for paper_id in paper_ids:
        first = metadata_by_slot[(paper_id, RUN_IDS[0])]
        second = metadata_by_slot[(paper_id, RUN_IDS[1])]
        if first["source"] != second["source"]:
            _fail(f"run metadata source pins differ between repeated runs for {paper_id}")
        if first["frozen_baseline"] != second["frozen_baseline"]:
            _fail(f"run metadata baseline pins differ between repeated runs for {paper_id}")
    return metadata_by_slot


def _validate_ground_truth(ground_truth: Any, lock_paper_ids: list[str]) -> tuple[dict[str, str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(ground_truth, dict):
        _fail("ground-truth top level must be an object")
    if ground_truth.get("schema_version") != INPUT_SCHEMA_VERSION:
        _fail(f"ground-truth schema_version must equal {INPUT_SCHEMA_VERSION}")
    if ground_truth.get("evaluation_wave") != EVALUATION_WAVE:
        _fail("ground-truth evaluation_wave is incorrect")
    paper_rows = ground_truth.get("papers")
    if not isinstance(paper_rows, list):
        _fail("ground-truth papers must be an array")
    roles: dict[str, str] = {}
    for index, row in enumerate(paper_rows):
        where = f"ground-truth papers[{index}]"
        if not isinstance(row, dict):
            _fail(f"{where} must be an object")
        paper_id = _nonempty_string(row.get("paper_id"), f"{where}.paper_id")
        role = row.get("role")
        if role not in ("positive", "negative"):
            _fail(f"{where}.role must be positive or negative")
        if paper_id in roles:
            _fail(f"duplicate ground-truth paper ID: {paper_id}")
        roles[paper_id] = role
    if set(roles) != set(lock_paper_ids):
        _fail("ground-truth paper IDs do not exactly match the output lock paper IDs")

    issue_rows = ground_truth.get("positive_issues")
    if not isinstance(issue_rows, list):
        _fail("ground-truth positive_issues must be an array")
    issues: dict[str, dict[str, Any]] = {}
    targets: dict[str, dict[str, Any]] = {}
    for index, issue in enumerate(issue_rows):
        where = f"ground-truth positive_issues[{index}]"
        if not isinstance(issue, dict):
            _fail(f"{where} must be an object")
        issue_id = _nonempty_string(issue.get("issue_id"), f"{where}.issue_id")
        paper_id = _nonempty_string(issue.get("paper_id"), f"{where}.paper_id")
        if issue_id in issues:
            _fail(f"duplicate positive issue ID: {issue_id}")
        if paper_id not in roles or roles[paper_id] != "positive":
            _fail(f"{where}.paper_id must identify a positive paper")
        supportability = issue.get("supportability")
        if supportability not in ("eligible", "unsupported_by_frozen_screens"):
            _fail(f"{where}.supportability is invalid")
        target_rows = issue.get("targets")
        if not isinstance(target_rows, list):
            _fail(f"{where}.targets must be an array")
        if supportability == "eligible" and not target_rows:
            _fail(f"{where}.targets must contain at least one item for an eligible issue")
        issue_targets: list[str] = []
        for target_index, target in enumerate(target_rows):
            target_where = f"{where}.targets[{target_index}]"
            if not isinstance(target, dict):
                _fail(f"{target_where} must be an object")
            target_id = _nonempty_string(target.get("target_id"), f"{target_where}.target_id")
            if target_id in targets:
                _fail(f"duplicate target ID: {target_id}")
            candidate_type = _nonempty_string(target.get("candidate_type"), f"{target_where}.candidate_type")
            operands = target.get("operands")
            if not isinstance(operands, dict) or not operands:
                _fail(f"{target_where}.operands must be a non-empty object")
            anchors = target.get("required_anchors")
            if not isinstance(anchors, list) or not anchors:
                _fail(f"{target_where}.required_anchors must contain at least one anchor")
            clean_anchors: list[dict[str, Any]] = []
            for anchor_index, anchor in enumerate(anchors):
                anchor_where = f"{target_where}.required_anchors[{anchor_index}]"
                if not isinstance(anchor, dict):
                    _fail(f"{anchor_where} must be an object")
                if set(anchor) - {"quote", "section", "page_number"}:
                    _fail(f"{anchor_where} may contain only quote, section, and page_number")
                quote = _nonempty_string(anchor.get("quote"), f"{anchor_where}.quote")
                spec = {"quote": quote}
                if "section" in anchor:
                    spec["section"] = _nonempty_string(anchor["section"], f"{anchor_where}.section")
                if "page_number" in anchor:
                    if not _is_int(anchor["page_number"]) or anchor["page_number"] < 1:
                        _fail(f"{anchor_where}.page_number must be a positive integer")
                    spec["page_number"] = anchor["page_number"]
                clean_anchors.append(spec)
            target_record = {
                "target_id": target_id,
                "issue_id": issue_id,
                "paper_id": paper_id,
                "candidate_type": candidate_type,
                "operands": operands,
                "required_anchors": clean_anchors,
            }
            targets[target_id] = target_record
            issue_targets.append(target_id)
        issues[issue_id] = {
            "issue_id": issue_id,
            "paper_id": paper_id,
            "supportability": supportability,
            "target_ids": issue_targets,
        }
    issues_per_paper = {paper_id: 0 for paper_id in roles}
    for issue in issues.values():
        issues_per_paper[issue["paper_id"]] += 1
    for paper_id, role in roles.items():
        if role == "positive" and issues_per_paper[paper_id] == 0:
            _fail(f"positive paper {paper_id!r} has no positive issue")
        if role == "negative" and issues_per_paper[paper_id] != 0:
            _fail(f"negative paper {paper_id!r} has a positive issue")
    return roles, issues, targets


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        _fail(f"value is not valid JSON data: {exc}")


def _normalized_quote(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _candidate_matches_target(candidate: dict[str, Any], target: dict[str, Any]) -> bool:
    if candidate.get("type") != target["candidate_type"]:
        return False
    for field, expected_value in target["operands"].items():
        if field not in candidate or _canonical_json(candidate[field]) != _canonical_json(expected_value):
            return False
    candidate_anchors = candidate.get("source_anchors")
    if not isinstance(candidate_anchors, list):
        return False
    unused = list(candidate_anchors)
    for expected in target["required_anchors"]:
        found_index = None
        for index, actual in enumerate(unused):
            if not isinstance(actual, dict) or not isinstance(actual.get("quote"), str):
                continue
            if _normalized_quote(actual["quote"]) != _normalized_quote(expected["quote"]):
                continue
            if "section" in expected and actual.get("section") != expected["section"]:
                continue
            if "page_number" in expected and actual.get("page_number") != expected["page_number"]:
                continue
            found_index = index
            break
        if found_index is None:
            return False
        unused.pop(found_index)
    return True


def _parse_report(
    data: bytes,
    where: str,
    paper_id: str,
    run_id: str,
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    report = _load_json_bytes(data, where)
    if not isinstance(report, dict):
        _fail(f"{where} top level must be an object")
    if report.get("paper_audit_version") != PAPER_AUDIT_VERSION:
        _fail(f"{where}.paper_audit_version differs from the frozen paper-audit schema")
    source_report = report.get("source")
    if not isinstance(source_report, dict):
        _fail(f"{where}.source must be an object")
    metadata_source = run_metadata["source"]
    if source_report.get("identifier") != paper_id:
        _fail(f"{where}.source.identifier differs from its opaque paper_id")
    if source_report.get("version") != metadata_source["source_version_token"]:
        _fail(f"{where}.source.version differs from locked run metadata")
    if source_report.get("sha256") != metadata_source["staged_input_sha256"]:
        _fail(f"{where}.source.sha256 differs from the locked staged-input hash")
    extraction = report.get("extraction")
    if not isinstance(extraction, dict) or extraction.get("status") not in EXTRACTION_STATUSES:
        _fail(f"{where}.extraction.status is missing or unknown")
    discovery = report.get("discovery")
    if not isinstance(discovery, dict) or type(discovery.get("scan_complete")) is not bool:
        _fail(f"{where}.discovery.scan_complete is missing or not boolean")
    candidates = report.get("candidate_anomalies")
    scopes = report.get("possible_scope_differences")
    unsupported = report.get("unsupported_checks")
    verified = report.get("verified_findings")
    for field, value in (("candidate_anomalies", candidates), ("possible_scope_differences", scopes),
                         ("unsupported_checks", unsupported), ("verified_findings", verified)):
        if not isinstance(value, list):
            _fail(f"{where}.{field} must be an array")
    candidate_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        item_where = f"{where}.candidate_anomalies[{index}]"
        if not isinstance(candidate, dict):
            _fail(f"{item_where} must be an object")
        candidate_id = _nonempty_string(candidate.get("id"), f"{item_where}.id")
        _nonempty_string(candidate.get("type"), f"{item_where}.type")
        if candidate_id in candidate_ids:
            _fail(f"{where} contains duplicate candidate id {candidate_id!r}")
        candidate_ids.add(candidate_id)
        if not isinstance(candidate.get("source_anchors"), list):
            _fail(f"{item_where}.source_anchors must be an array")
    scope_ids: set[str] = set()
    for index, note in enumerate(scopes):
        item_where = f"{where}.possible_scope_differences[{index}]"
        if not isinstance(note, dict):
            _fail(f"{item_where} must be an object")
        note_id = _nonempty_string(note.get("id"), f"{item_where}.id")
        if note_id in scope_ids:
            _fail(f"{where} contains duplicate scope-note id {note_id!r}")
        scope_ids.add(note_id)
    return report


def _report_index(
    records: list[dict[str, Any]],
    data_by_path: dict[str, bytes],
    metadata_by_slot: dict[tuple[str, str], dict[str, Any]],
) -> tuple[dict[tuple[str, str, str], bytes], dict[tuple[str, str], dict[str, Any]]]:
    report_bytes: dict[tuple[str, str, str], bytes] = {}
    reports: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if record["kind"] not in REPORT_KINDS:
            continue
        key = (record["paper_id"], record["run_id"], record["kind"])
        data = data_by_path[record["path"]]
        report_bytes[key] = data
        if record["kind"] == "report_json":
            reports[(record["paper_id"], record["run_id"])] = _parse_report(
                data,
                f"{record['path']} ({record['paper_id']}/{record['run_id']})",
                record["paper_id"],
                record["run_id"],
                metadata_by_slot[(record["paper_id"], record["run_id"])],
            )
    return report_bytes, reports


def _validate_adjudication(
    adjudication: Any,
    lock_sha256: str,
    roles: dict[str, str],
    issues: dict[str, dict[str, Any]],
    targets: dict[str, dict[str, Any]],
    primary_reports: dict[str, dict[str, Any]],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], str]]:
    if not isinstance(adjudication, dict):
        _fail("adjudication top level must be an object")
    if adjudication.get("schema_version") != INPUT_SCHEMA_VERSION:
        _fail(f"adjudication schema_version must equal {INPUT_SCHEMA_VERSION}")
    if adjudication.get("evaluation_wave") != EVALUATION_WAVE:
        _fail("adjudication evaluation_wave is incorrect")
    if adjudication.get("lock_sha256") != lock_sha256:
        _fail("adjudication lock_sha256 does not bind to the committed LOCK.json bytes")

    actual_candidates: dict[tuple[str, str], dict[str, Any]] = {}
    actual_scopes: dict[tuple[str, str], dict[str, Any]] = {}
    for paper_id, report in primary_reports.items():
        for item in report["candidate_anomalies"]:
            actual_candidates[(paper_id, item["id"])] = item
        for item in report["possible_scope_differences"]:
            actual_scopes[(paper_id, item["id"])] = item

    candidate_rows = adjudication.get("candidate_items")
    scope_rows = adjudication.get("scope_notes")
    if not isinstance(candidate_rows, list) or not isinstance(scope_rows, list):
        _fail("adjudication candidate_items and scope_notes must be arrays")
    candidate_decisions: dict[tuple[str, str], dict[str, Any]] = {}
    assigned_targets: set[str] = set()
    for index, row in enumerate(candidate_rows):
        where = f"adjudication candidate_items[{index}]"
        if not isinstance(row, dict):
            _fail(f"{where} must be an object")
        paper_id = _nonempty_string(row.get("paper_id"), f"{where}.paper_id")
        candidate_id = _nonempty_string(row.get("candidate_id"), f"{where}.candidate_id")
        key = (paper_id, candidate_id)
        if key not in actual_candidates:
            _fail(f"{where} references no run-1 candidate: {key}")
        if key in candidate_decisions:
            _fail(f"duplicate candidate adjudication for {key}")
        disposition = row.get("disposition")
        candidate = actual_candidates[key]
        decision: dict[str, Any] = {"disposition": disposition}
        if disposition == "matches_known_issue":
            if set(row) != {"paper_id", "candidate_id", "disposition", "target_id"}:
                _fail(f"{where} matching a known issue must provide only target_id in addition to its decision fields")
            target_id = _nonempty_string(row.get("target_id"), f"{where}.target_id")
            target = targets.get(target_id)
            if target is None or target["paper_id"] != paper_id:
                _fail(f"{where}.target_id must identify a target on the same paper")
            if target_id in assigned_targets:
                _fail(f"target {target_id!r} is assigned to more than one candidate item")
            if not _candidate_matches_target(candidate, target):
                _fail(f"{where} claims a known issue but candidate does not match target {target_id!r}")
            if roles[paper_id] != "positive":
                _fail(f"negative-paper candidate {key} cannot match a known positive issue")
            assigned_targets.add(target_id)
            decision["target_id"] = target_id
        elif disposition in (
            "false_candidate",
            "unresolved",
            "legitimate_nonbenchmark_discrepancy",
        ):
            if set(row) != {"paper_id", "candidate_id", "disposition"}:
                _fail(f"{where} non-match decision must not name a target")
        else:
            _fail(
                f"{where}.disposition must be matches_known_issue, false_candidate, unresolved, "
                "or legitimate_nonbenchmark_discrepancy"
            )
        candidate_decisions[key] = decision
    missing_candidates = set(actual_candidates) - set(candidate_decisions)
    extra_candidates = set(candidate_decisions) - set(actual_candidates)
    if missing_candidates or extra_candidates:
        _fail(f"candidate adjudication coverage mismatch; missing={sorted(missing_candidates)}, extra={sorted(extra_candidates)}")

    scope_decisions: dict[tuple[str, str], str] = {}
    for index, row in enumerate(scope_rows):
        where = f"adjudication scope_notes[{index}]"
        if not isinstance(row, dict) or set(row) != {"paper_id", "scope_note_id", "classification"}:
            _fail(f"{where} must contain paper_id, scope_note_id, and classification only")
        paper_id = _nonempty_string(row.get("paper_id"), f"{where}.paper_id")
        note_id = _nonempty_string(row.get("scope_note_id"), f"{where}.scope_note_id")
        key = (paper_id, note_id)
        if key not in actual_scopes:
            _fail(f"{where} references no run-1 scope note: {key}")
        if key in scope_decisions:
            _fail(f"duplicate scope-note adjudication for {key}")
        classification = row.get("classification")
        if classification not in SCOPE_CLASSIFICATIONS:
            _fail(f"{where}.classification must be one of {SCOPE_CLASSIFICATIONS}")
        scope_decisions[key] = classification
    missing_scopes = set(actual_scopes) - set(scope_decisions)
    extra_scopes = set(scope_decisions) - set(actual_scopes)
    if missing_scopes or extra_scopes:
        _fail(f"scope-note adjudication coverage mismatch; missing={sorted(missing_scopes)}, extra={sorted(extra_scopes)}")
    return candidate_decisions, scope_decisions


def _wilson_95(numerator: int, denominator: int) -> dict[str, float] | None:
    if denominator == 0:
        return None
    if not 0 <= numerator <= denominator:
        _fail("a binomial proportion has a numerator outside its denominator")
    n = denominator
    p = numerator / n
    z2 = WILSON_Z_95 * WILSON_Z_95
    scale = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / scale
    margin = WILSON_Z_95 * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n))) / scale
    return {"lower": round(max(0.0, center - margin), 9), "upper": round(min(1.0, center + margin), 9)}


def _fraction(numerator: int, denominator: int, *, wilson: bool = False) -> dict[str, Any]:
    estimate = None if denominator == 0 else numerator / denominator
    result: dict[str, Any] = {
        "numerator": numerator,
        "denominator": denominator,
        "raw_fraction": f"{numerator}/{denominator}",
        "estimate": None if estimate is None else round(estimate, 9),
    }
    if wilson:
        result["wilson_95_ci"] = _wilson_95(numerator, denominator)
    return result


def _score(
    paper_ids: list[str],
    roles: dict[str, str],
    issues: dict[str, dict[str, Any]],
    targets: dict[str, dict[str, Any]],
    reports: dict[tuple[str, str], dict[str, Any]],
    report_bytes: dict[tuple[str, str, str], bytes],
    candidate_decisions: dict[tuple[str, str], dict[str, Any]],
    scope_decisions: dict[tuple[str, str], str],
    lock_sha256: str,
    output_lock_commit: str,
) -> dict[str, Any]:
    primary = {paper_id: reports[(paper_id, "run-1")] for paper_id in paper_ids}
    positive_issue_ids = [issue_id for issue_id, issue in issues.items()]
    eligible_issue_ids = [
        issue_id for issue_id, issue in issues.items() if issue["supportability"] == "eligible"
    ]
    issue_rediscovered: dict[str, bool] = {}
    for issue_id, issue in issues.items():
        issue_rediscovered[issue_id] = bool(issue["target_ids"]) and all(
            any(
                paper_id == issue["paper_id"]
                and decision.get("target_id") == target_id
                and decision["disposition"] == "matches_known_issue"
                for (paper_id, _candidate_id), decision in candidate_decisions.items()
            )
            for target_id in issue["target_ids"]
        )

    all_positive_detected = sum(issue_rediscovered[issue_id] for issue_id in positive_issue_ids)
    eligible_detected = sum(issue_rediscovered[issue_id] for issue_id in eligible_issue_ids)

    candidate_total = sum(len(report["candidate_anomalies"]) for report in primary.values())
    candidate_true = sum(
        decision["disposition"] == "matches_known_issue"
        for decision in candidate_decisions.values()
    )
    negative_ids = [paper_id for paper_id in paper_ids if roles[paper_id] == "negative"]
    negative_with_candidates = sum(bool(primary[paper_id]["candidate_anomalies"]) for paper_id in negative_ids)
    false_candidates_negative = sum(
        decision["disposition"] == "false_candidate" and roles[paper_id] == "negative"
        for (paper_id, _candidate_id), decision in candidate_decisions.items()
    )
    negative_unresolved_candidates = sum(
        decision["disposition"] == "unresolved" and roles[paper_id] == "negative"
        for (paper_id, _candidate_id), decision in candidate_decisions.items()
    )
    negative_candidate_total = sum(len(primary[paper_id]["candidate_anomalies"]) for paper_id in negative_ids)
    candidate_disposition_counts = {
        disposition: sum(decision["disposition"] == disposition for decision in candidate_decisions.values())
        for disposition in (
            "matches_known_issue",
            "false_candidate",
            "unresolved",
            "legitimate_nonbenchmark_discrepancy",
        )
    }

    scope_total = sum(len(report["possible_scope_differences"]) for report in primary.values())
    scope_class_counts = {classification: 0 for classification in SCOPE_CLASSIFICATIONS}
    for classification in scope_decisions.values():
        scope_class_counts[classification] += 1
    papers_with_scope_notes = sum(bool(primary[paper_id]["possible_scope_differences"]) for paper_id in paper_ids)

    unsupported_issue_ids = [
        issue_id for issue_id, issue in issues.items()
        if issue["supportability"] == "unsupported_by_frozen_screens"
    ]
    unsupported_checks = sum(len(report["unsupported_checks"]) for report in primary.values())
    unsupported_check_papers = sum(bool(report["unsupported_checks"]) for report in primary.values())

    extraction_status_counts = {status: 0 for status in sorted(EXTRACTION_STATUSES)}
    extraction_outcome_counts = {outcome: 0 for outcome in EXTRACTION_OUTCOME_STATUSES}
    extraction_failures = 0
    degraded_status_papers = 0
    degraded_or_incomplete_papers = 0
    scan_incomplete = 0
    extraction_warning_count = 0
    verified_findings_count = 0
    papers_with_verified_findings = 0
    for report in primary.values():
        extraction = report["extraction"]
        status = extraction["status"]
        extraction_status_counts[status] += 1
        for outcome, statuses in EXTRACTION_OUTCOME_STATUSES.items():
            extraction_outcome_counts[outcome] += status in statuses
        extraction_failures += status in EXTRACTION_FAILURE_STATUSES
        scan_complete = report["discovery"]["scan_complete"]
        scan_incomplete += not scan_complete
        degraded_status_papers += status == "PARTIAL_TEXT"
        degraded_or_incomplete_papers += status == "PARTIAL_TEXT" or not scan_complete
        warnings = extraction.get("warnings", [])
        if isinstance(warnings, list):
            extraction_warning_count += len(warnings)
        verified_count = len(report["verified_findings"])
        verified_findings_count += verified_count
        papers_with_verified_findings += verified_count > 0
    if verified_findings_count > candidate_total:
        _fail("verified_findings count exceeds candidate item count, so promotion rate is not defined")

    json_repeatable = 0
    html_repeatable = 0
    for paper_id in paper_ids:
        json_repeatable += report_bytes[(paper_id, "run-1", "report_json")] == report_bytes[(paper_id, "run-2", "report_json")]
        html_repeatable += report_bytes[(paper_id, "run-1", "report_html")] == report_bytes[(paper_id, "run-2", "report_html")]
    joint_repeatable = sum(
        report_bytes[(paper_id, "run-1", "report_json")] == report_bytes[(paper_id, "run-2", "report_json")]
        and report_bytes[(paper_id, "run-1", "report_html")] == report_bytes[(paper_id, "run-2", "report_html")]
        for paper_id in paper_ids
    )

    classifications = {
        classification: {
            "count": scope_class_counts[classification],
            "fraction_of_scope_notes": _fraction(scope_class_counts[classification], scope_total),
        }
        for classification in SCOPE_CLASSIFICATIONS
    }
    return {
        "schema_version": 1,
        "evaluation_wave": EVALUATION_WAVE,
        "scoring_rules_version": SCORING_RULES_VERSION,
        "frozen_baseline_commit": BASELINE_COMMIT,
        "output_lock_commit": output_lock_commit,
        "output_lock_sha256": lock_sha256,
        "primary_run_id": "run-1",
        "metrics": {
            "positive_issue_rediscovery_all": _fraction(
                all_positive_detected, len(positive_issue_ids), wilson=True
            ),
            "positive_issue_rediscovery_detector_eligible": _fraction(
                eligible_detected, len(eligible_issue_ids), wilson=True
            ),
            "candidate_precision_by_adjudicated_item": _fraction(
                candidate_true, candidate_total, wilson=True
            ),
            "negative_papers_with_candidates": _fraction(
                negative_with_candidates, len(negative_ids), wilson=True
            ),
            "confirmed_false_candidates_per_negative_paper": _fraction(
                false_candidates_negative, len(negative_ids)
            ),
            "candidate_adjudication": {
                "disposition_counts": {
                    disposition: {
                        "count": count,
                        "fraction_of_candidate_items": _fraction(count, candidate_total),
                    }
                    for disposition, count in candidate_disposition_counts.items()
                },
                "unresolved_candidates": {
                    "count": candidate_disposition_counts["unresolved"],
                    "fraction_of_candidate_items": _fraction(
                        candidate_disposition_counts["unresolved"], candidate_total
                    ),
                },
                "negative_unresolved_candidates": {
                    "count": negative_unresolved_candidates,
                    "fraction_of_negative_candidate_items": _fraction(
                        negative_unresolved_candidates, negative_candidate_total
                    ),
                },
            },
            "scope_notes": {
                "count": scope_total,
                "notes_per_paper": _fraction(scope_total, len(paper_ids)),
                "papers_with_one_or_more": _fraction(papers_with_scope_notes, len(paper_ids)),
                "classifications": classifications,
            },
            "unsupported_positive_issues": {
                "count": len(unsupported_issue_ids),
                "fraction_of_positive_issues": _fraction(len(unsupported_issue_ids), len(positive_issue_ids)),
            },
            "reported_unsupported_checks": {
                "count": unsupported_checks,
                "papers_with_one_or_more": _fraction(unsupported_check_papers, len(paper_ids)),
            },
            "extraction": {
                "status_counts": extraction_status_counts,
                "outcome_buckets": {
                    outcome: {
                        "statuses": sorted(statuses),
                        "count": extraction_outcome_counts[outcome],
                        "fraction_of_papers": _fraction(extraction_outcome_counts[outcome], len(paper_ids)),
                    }
                    for outcome, statuses in EXTRACTION_OUTCOME_STATUSES.items()
                },
                "failure_papers": _fraction(extraction_failures, len(paper_ids)),
                "degraded_status_papers": _fraction(degraded_status_papers, len(paper_ids)),
                "degraded_or_incomplete_papers": _fraction(degraded_or_incomplete_papers, len(paper_ids)),
                "scan_incomplete_papers": _fraction(scan_incomplete, len(paper_ids)),
                "warning_count": extraction_warning_count,
                "failure_and_scan_incompleteness_may_overlap": True,
            },
            "confidence_interval_notes": {
                "candidate_precision": "Wilson interval treats candidate items as Bernoulli units; within-paper clustering may make it too narrow.",
                "negative_paper_candidate_rate": "Wilson interval uses papers as Bernoulli units.",
            },
            "repeatability": {
                "json_reports_identical": _fraction(json_repeatable, len(paper_ids)),
                "html_reports_identical": _fraction(html_repeatable, len(paper_ids)),
                "both_reports_identical": _fraction(joint_repeatable, len(paper_ids)),
            },
            "verified_promotion_rate": {
                "promoted_findings": verified_findings_count,
                "papers_with_promotions": papers_with_verified_findings,
                "fraction_of_candidate_items": _fraction(verified_findings_count, candidate_total),
            },
        },
    }


def score(
    lock_path: Path,
    ground_truth_path: Path,
    adjudication_path: Path,
) -> tuple[dict[str, Any], set[Path]]:
    """Verify the committed lock and all raw files before opening label inputs."""
    lock_path = lock_path.absolute()
    if lock_path.name != "LOCK.json":
        _fail("--lock must point to a file named LOCK.json")
    repo = _repo_root(lock_path)
    committed_lock_path, lock_bytes = _committed_file_bytes(lock_path, repo, "LOCK.json")
    head = _git_bytes(repo, "rev-parse", "HEAD").decode("ascii").strip()
    frozen_tree = _git_bytes(repo, "rev-parse", f"{BASELINE_COMMIT}^{{tree}}").decode("ascii").strip()
    if frozen_tree != BASELINE_TREE_SHA:
        _fail("repository frozen-baseline tree does not match the preregistered tree")
    _git_bytes(repo, "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD")
    lock = _load_json_bytes(lock_bytes, "committed LOCK.json")
    paper_ids, raw_records = _validate_lock(lock)
    lock_parent = committed_lock_path.relative_to(repo).parent.as_posix()
    if lock["output_root"] != lock_parent:
        _fail("LOCK.json output_root must be the repository-relative directory containing LOCK.json")

    # All lock-listed bytes are verified as committed and hash-correct before
    # either ground-truth or adjudication bytes are read.
    raw_bytes, raw_paths = _verify_all_locked_outputs(raw_records, repo)
    metadata_by_slot = _verify_pinned_manifest_and_runner(lock, paper_ids, raw_records, raw_bytes, repo)
    report_bytes, reports = _report_index(raw_records, raw_bytes, metadata_by_slot)
    lock_hash = _digest(lock_bytes)

    input_paths = {committed_lock_path.resolve()}
    input_paths.update(path.resolve() for path in raw_paths.values())
    input_paths.add(repo.joinpath(*PurePosixPath(lock["source_manifest_path"]).parts).resolve())
    input_paths.add(repo.joinpath(*PurePosixPath(RUNNER_PATH).parts).resolve())
    ground_truth_resolved = ground_truth_path.resolve()
    adjudication_resolved = adjudication_path.resolve()
    if ground_truth_resolved == adjudication_resolved or ground_truth_resolved in input_paths or adjudication_resolved in input_paths:
        _fail("ground truth and adjudication must be separate files from the lock and all locked raw outputs")

    ground_truth, _ground_truth_bytes = _read_json(ground_truth_path, "separate ground-truth file")
    adjudication, _adjudication_bytes = _read_json(adjudication_path, "separate post-lock adjudication file")
    roles, issues, targets = _validate_ground_truth(ground_truth, paper_ids)
    primary_reports = {paper_id: reports[(paper_id, "run-1")] for paper_id in paper_ids}
    candidate_decisions, scope_decisions = _validate_adjudication(
        adjudication,
        lock_hash,
        roles,
        issues,
        targets,
        primary_reports,
    )
    summary = _score(
        paper_ids,
        roles,
        issues,
        targets,
        reports,
        report_bytes,
        candidate_decisions,
        scope_decisions,
        lock_hash,
        head,
    )
    input_paths.add(ground_truth_resolved)
    input_paths.add(adjudication_resolved)
    return summary, input_paths


def _write_summary(summary: dict[str, Any], output: Path | None, protected_inputs: set[Path]) -> None:
    text = json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if output is None or str(output) == "-":
        sys.stdout.write(text)
        return
    output = output.absolute()
    try:
        resolved = output.resolve(strict=False)
    except OSError as exc:
        _fail(f"cannot resolve --output path: {exc}")
    if resolved in protected_inputs or output.is_symlink():
        _fail("--output must not overwrite an input file or symlink")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    except OSError as exc:
        _fail(f"cannot write JSON summary: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True, help="committed output LOCK.json")
    parser.add_argument("--ground-truth", type=Path, required=True,
                        help="separate post-run ground-truth JSON (opened after all locked hashes verify)")
    parser.add_argument("--adjudication", type=Path, required=True,
                        help="separate post-lock adjudication JSON, bound to LOCK.json by lock_sha256")
    parser.add_argument("--output", type=Path,
                        help="summary JSON destination; defaults to stdout")
    args = parser.parse_args()
    try:
        summary, protected = score(args.lock, args.ground_truth, args.adjudication)
        _write_summary(summary, args.output, protected)
    except ScoringError as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
