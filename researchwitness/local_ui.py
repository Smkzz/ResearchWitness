"""Loopback-only, local-first paper-audit interface.

The UI performs no source retrieval, model call, or external request. Its small
HTTP surface accepts bounded local files and exposes only this user's local
run records. It is a convenience layer around the existing paper-audit
pipeline, not a custody or scientific-verification boundary.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import http.server
import ipaddress
import io
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import stat
import tempfile
import threading
from typing import Any
from urllib.parse import unquote_to_bytes
import webbrowser
import zipfile

from .paper_audit import (
    MAX_SOURCE_BYTES, PAPER_AUDIT_VERSION, PaperAuditCancelled,
    run_paper_audit,
)
from .strict import Invalid, canonical, text

UI_VERSION = "local-paper-audit/1"
MAX_JOBS = 10
MAX_STORE_BYTES = 512 * 1024 * 1024
MAX_METADATA_BYTES = 128 * 1024
MAX_API_REPORT_BYTES = 32 * 1024 * 1024
MAX_EXPORT_BYTES = 96 * 1024 * 1024
SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".xml", ".nxml", ".pdf"}
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$", re.ASCII)
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"}
ACTIVE_STATES = {"QUEUED", "ANALYZING", "CANCELLING"}
STAGES = {
    "queued": "Waiting for an analysis worker",
    "Reading source bytes": "Reading and hashing the selected file",
    "Extracting text and source structure": "Extracting text and recognizing supported structure",
    "Scanning explicit count statements": "Checking explicit count statements",
    "Checking Markdown table percentages": "Checking supported Markdown percentage cells",
    "Locating explicit exclusion-flow questions": "Locating unresolved sample-flow questions",
    "Checking structured JATS table percentages": "Checking source-mapped JATS tables",
    "Checking structured JATS ratios and summaries": "Checking other supported JATS numeric relationships",
    "Checking source-mapped flow relationships": "Checking source-mapped flow relationships",
    "Writing source copy and reproducible report": "Writing the source-bound report",
}


class LocalUIError(Exception):
    def __init__(self, code: str, http_status: int = 400):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _private_directory(path: Path) -> None:
    absolute = path.absolute()
    components = list(reversed((absolute, *absolute.parents)))
    for component in components:
        try:
            info = os.lstat(component)
        except FileNotFoundError:
            try:
                component.mkdir(mode=0o700)
            except FileExistsError:
                pass
            info = os.lstat(component)
        if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400):
            raise LocalUIError("LOCAL_DATA_PATH_IS_LINK", 500)
        if not stat.S_ISDIR(info.st_mode):
            raise LocalUIError("LOCAL_DATA_PATH_NOT_DIRECTORY", 500)
    if os.name != "nt":
        os.chmod(absolute, 0o700)


def default_data_directory() -> Path:
    override = os.environ.get("RESEARCHWITNESS_DATA_DIR")
    if override:
        return Path(override).expanduser().absolute()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "ResearchWitness" / "local-audit"
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base).expanduser() / "researchwitness" / "local-audit"
    return Path.home() / ".local" / "share" / "researchwitness" / "local-audit"


def _safe_filename(encoded: str) -> tuple[str, str]:
    if not encoded or len(encoded) > 1536 or re.search(r"%(?![0-9A-Fa-f]{2})", encoded):
        raise LocalUIError("FILENAME_INVALID")
    try:
        value = unquote_to_bytes(encoded).decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise LocalUIError("FILENAME_INVALID") from exc
    if (not value or len(value) > 255 or any(ord(ch) < 32 for ch in value)
        or "/" in value or "\\" in value or value in {".", ".."}):
        raise LocalUIError("FILENAME_INVALID")
    suffix = Path(value).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise LocalUIError("UNSUPPORTED_FILE_FORMAT")
    return value, suffix


def _decoded_header(value: str | None, *, limit: int, default: str | None = None) -> str | None:
    if value is None:
        return default
    if len(value) > limit * 3 or re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise LocalUIError("METADATA_INVALID")
    try:
        decoded = unquote_to_bytes(value).decode("utf-8", errors="strict").strip()
        return text(decoded, limit) if decoded else default
    except (UnicodeError, Invalid) as exc:
        raise LocalUIError("METADATA_INVALID") from exc


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(encoded) > MAX_METADATA_BYTES:
        raise LocalUIError("LOCAL_RECORD_LIMIT_EXCEEDED", 507)
    fd, name = tempfile.mkstemp(prefix=".rw-local-", suffix=".tmp", dir=path.parent)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclass
class AuditJob:
    job_id: str
    cache_key: str
    original_name: str
    suffix: str
    identifier: str
    source_version: str
    source_sha256: str
    source_bytes: int
    status: str = "QUEUED"
    stage: str = "queued"
    created_at_utc: str = field(default_factory=_utc_now)
    updated_at_utc: str = field(default_factory=_utc_now)
    decision: str | None = None
    candidate_count: int | None = None
    scope_question_count: int | None = None
    checks_attempted: list[str] = field(default_factory=list)
    extraction_status: str | None = None
    extraction_format: str | None = None
    scan_complete: bool | None = None
    unsupported_checks: list[str] = field(default_factory=list)
    detector_eligibility: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None
    duplicate: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    future: Future | None = field(default=None, repr=False)

    def record(self) -> dict[str, Any]:
        return {
            "ui_version": UI_VERSION,
            "job_id": self.job_id,
            "cache_key": self.cache_key,
            "original_name": self.original_name,
            "suffix": self.suffix,
            "identifier": self.identifier,
            "source_version": self.source_version,
            "source_sha256": self.source_sha256,
            "source_bytes": self.source_bytes,
            "status": self.status,
            "stage": self.stage,
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
            "decision": self.decision,
            "candidate_count": self.candidate_count,
            "scope_question_count": self.scope_question_count,
            "checks_attempted": self.checks_attempted,
            "extraction_status": self.extraction_status,
            "extraction_format": self.extraction_format,
            "scan_complete": self.scan_complete,
            "unsupported_checks": self.unsupported_checks,
            "detector_eligibility": self.detector_eligibility,
            "error_code": self.error_code,
        }

    def public(self) -> dict[str, Any]:
        row = self.record()
        row.pop("cache_key", None)
        row.pop("ui_version", None)
        row["stage_label"] = STAGES.get(self.stage, self.stage)
        return row


class LocalAuditStore:
    """Bounded local run cache. All paths are derived from opaque run IDs."""

    def __init__(self, root: Path | None = None):
        self.root = (root or default_data_directory()).absolute()
        _private_directory(self.root)
        self.runs = self.root / "runs"
        _private_directory(self.runs)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rw-local-audit")
        self.jobs: dict[str, AuditJob] = {}
        self.store_warning: str | None = None
        self._load_records()

    def _job_dir(self, job_id: str) -> Path:
        if not JOB_ID_RE.fullmatch(job_id):
            raise LocalUIError("RUN_NOT_FOUND", 404)
        return self.runs / job_id

    def _metadata_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "job.json"

    def _save(self, job: AuditJob) -> None:
        job.updated_at_utc = _utc_now()
        _atomic_json(self._metadata_path(job.job_id), job.record())

    def _load_records(self) -> None:
        try:
            with os.scandir(self.runs) as scan:
                names = []
                for entry in scan:
                    if len(names) >= MAX_JOBS * 2:
                        self.store_warning = "LOCAL_HISTORY_ENTRY_LIMIT_REQUIRES_MANUAL_REVIEW"
                        return
                    names.append(entry.name)
        except OSError:
            self.store_warning = "LOCAL_HISTORY_UNAVAILABLE"
            return
        for name in sorted(names):
            if not JOB_ID_RE.fullmatch(name):
                self.store_warning = "UNRECOGNIZED_LOCAL_DATA_REQUIRES_MANUAL_REVIEW"
                continue
            run_dir = self.runs / name
            try:
                info = os.lstat(run_dir)
                if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400) or not stat.S_ISDIR(info.st_mode):
                    self.store_warning = "UNSAFE_LOCAL_RUN_DIRECTORY"
                    continue
                meta_path = run_dir / "job.json"
                meta_info = os.lstat(meta_path)
                if not stat.S_ISREG(meta_info.st_mode) or meta_info.st_nlink != 1 or meta_info.st_size > MAX_METADATA_BYTES:
                    self.store_warning = "UNSAFE_LOCAL_RUN_RECORD"
                    continue
                row = json.loads(meta_path.read_text(encoding="utf-8"))
                if not isinstance(row, dict):
                    raise ValueError("run record must be an object")
                if row.get("ui_version") != UI_VERSION or row.get("job_id") != name:
                    self.store_warning = "UNSUPPORTED_LOCAL_RUN_RECORD"
                    continue
                if (row.get("status") not in ACTIVE_STATES | TERMINAL_STATES
                        or row.get("suffix") not in SUPPORTED_SUFFIXES
                        or not isinstance(row.get("source_bytes"), int)
                        or isinstance(row.get("source_bytes"), bool)
                        or not 0 < row["source_bytes"] <= MAX_SOURCE_BYTES
                        or not isinstance(row.get("source_sha256"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])):
                    self.store_warning = "UNSUPPORTED_LOCAL_RUN_RECORD"
                    continue
                job = AuditJob(
                    job_id=row["job_id"], cache_key=row["cache_key"], original_name=row["original_name"],
                    suffix=row["suffix"], identifier=row["identifier"], source_version=row["source_version"],
                    source_sha256=row["source_sha256"], source_bytes=row["source_bytes"],
                    status=row["status"], stage=row["stage"], created_at_utc=row["created_at_utc"],
                    updated_at_utc=row["updated_at_utc"], decision=row.get("decision"),
                    candidate_count=row.get("candidate_count"), scope_question_count=row.get("scope_question_count"),
                    checks_attempted=row.get("checks_attempted", []), extraction_status=row.get("extraction_status"),
                    extraction_format=row.get("extraction_format"), scan_complete=row.get("scan_complete"),
                    unsupported_checks=row.get("unsupported_checks", []),
                    detector_eligibility=row.get("detector_eligibility", []), error_code=row.get("error_code"),
                )
                self._validate_run_layout(run_dir, job.suffix)
                if job.status in ACTIVE_STATES:
                    job.status = "INTERRUPTED"
                    job.stage = "The previous app process stopped; retry will re-run the pinned local input"
                    job.error_code = "APP_RESTARTED"
                    self._save(job)
                self.jobs[job.job_id] = job
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                self.store_warning = "LOCAL_RUN_RECORD_REQUIRES_MANUAL_REVIEW"
            except LocalUIError as exc:
                self.store_warning = exc.code

    def _validate_run_layout(self, run_dir: Path, suffix: str) -> None:
        root_info = os.lstat(run_dir)
        if (stat.S_ISLNK(root_info.st_mode)
                or (getattr(root_info, "st_file_attributes", 0) & 0x400)
                or not stat.S_ISDIR(root_info.st_mode)):
            raise LocalUIError("UNSAFE_LOCAL_RUN_DIRECTORY", 500)
        allowed_top = {"job.json", "source" + suffix, "report-data"}
        try:
            with os.scandir(run_dir) as scan:
                top = []
                for entry in scan:
                    if len(top) >= 4:
                        raise LocalUIError("LOCAL_RUN_LAYOUT_REQUIRES_MANUAL_REVIEW", 409)
                    top.append(entry.name)
        except OSError as exc:
            raise LocalUIError("LOCAL_RUN_LAYOUT_UNAVAILABLE", 500) from exc
        if len(top) != len(set(name.casefold() for name in top)) or not set(top) <= allowed_top:
            raise LocalUIError("LOCAL_RUN_LAYOUT_REQUIRES_MANUAL_REVIEW", 409)
        if not {"job.json", "source" + suffix} <= set(top):
            raise LocalUIError("LOCAL_RUN_LAYOUT_REQUIRES_MANUAL_REVIEW", 409)
        report_dir = run_dir / "report-data"
        if "report-data" in top:
            info = os.lstat(report_dir)
            if (stat.S_ISLNK(info.st_mode)
                    or (getattr(info, "st_file_attributes", 0) & 0x400)
                    or not stat.S_ISDIR(info.st_mode)):
                raise LocalUIError("UNSAFE_LOCAL_RUN_DIRECTORY", 500)
            allowed_reports = {
                "report.json", "report.html", "extracted-text.txt", "paper-document.json",
                "source" + suffix,
            }
            try:
                with os.scandir(report_dir) as scan:
                    report_names = []
                    for entry in scan:
                        if len(report_names) >= len(allowed_reports) + 1:
                            raise LocalUIError("LOCAL_REPORT_LAYOUT_REQUIRES_MANUAL_REVIEW", 409)
                        report_names.append(entry.name)
            except OSError as exc:
                raise LocalUIError("LOCAL_REPORT_LAYOUT_UNAVAILABLE", 500) from exc
            if (len(report_names) != len(set(name.casefold() for name in report_names))
                    or not set(report_names) <= allowed_reports):
                raise LocalUIError("LOCAL_REPORT_LAYOUT_REQUIRES_MANUAL_REVIEW", 409)
        self._size_of(run_dir)

    def _size_of(self, path: Path, *, max_entries: int = 128) -> int:
        root_info = os.lstat(path)
        if (stat.S_ISLNK(root_info.st_mode)
                or (getattr(root_info, "st_file_attributes", 0) & 0x400)
                or not stat.S_ISDIR(root_info.st_mode)):
            raise LocalUIError("UNSAFE_LOCAL_HISTORY_ENTRY", 500)
        total = 0
        pending = [path]
        visited = 0
        while pending:
            current = pending.pop()
            try:
                scan = os.scandir(current)
            except OSError:
                raise LocalUIError("LOCAL_HISTORY_UNAVAILABLE", 500)
            with scan:
                for entry in scan:
                    visited += 1
                    if visited > max_entries:
                        raise LocalUIError("LOCAL_HISTORY_LIMIT_REQUIRES_DELETION", 507)
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400):
                        raise LocalUIError("UNSAFE_LOCAL_HISTORY_ENTRY", 500)
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(Path(entry.path))
                    elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                        total += info.st_size
                    else:
                        raise LocalUIError("UNSAFE_LOCAL_HISTORY_ENTRY", 500)
        return total

    def _evict_for(self, estimated_bytes: int = 0, *, preserve: set[str] | None = None) -> None:
        preserve = preserve or set()
        active = {job.job_id for job in self.jobs.values() if job.status in ACTIVE_STATES}
        rows = sorted(self.jobs.values(), key=lambda job: job.created_at_utc)
        for job in rows:
            self._validate_run_layout(self._job_dir(job.job_id), job.suffix)
        total = sum(self._size_of(self._job_dir(job.job_id)) for job in rows)
        while len(rows) >= MAX_JOBS or total + estimated_bytes > MAX_STORE_BYTES:
            victim = next((job for job in rows if job.job_id not in active
                           and job.job_id not in preserve and job.status in TERMINAL_STATES), None)
            if victim is None:
                raise LocalUIError("LOCAL_HISTORY_LIMIT_REACHED_DELETE_OLD_RUNS", 507)
            victim_dir = self._job_dir(victim.job_id)
            removed = self._size_of(victim_dir)
            shutil.rmtree(victim_dir)
            self.jobs.pop(victim.job_id, None)
            rows.remove(victim)
            total -= removed

    def _cache_key(self, source_hash: str, suffix: str, identifier: str, version: str) -> str:
        config = {
            "ui_version": UI_VERSION,
            "paper_audit_version": PAPER_AUDIT_VERSION,
            "source_sha256": source_hash,
            "suffix": suffix,
            "identifier": identifier,
            "source_version": version,
        }
        return _hash(canonical(config))

    def submit(self, original_name: str, suffix: str, source: bytes,
               identifier: str, version: str, *, force: bool = False) -> tuple[AuditJob, bool]:
        if not source:
            raise LocalUIError("EMPTY_FILE")
        if len(source) > MAX_SOURCE_BYTES:
            raise LocalUIError("FILE_TOO_LARGE", 413)
        source_hash = _hash(source)
        cache_key = self._cache_key(source_hash, suffix, identifier, version)
        with self.lock:
            if self.store_warning:
                raise LocalUIError("LOCAL_DATA_REQUIRES_MANUAL_REVIEW", 409)
            if not force:
                duplicate = next((job for job in self.jobs.values()
                                  if job.cache_key == cache_key and job.status in ACTIVE_STATES | {"COMPLETED"}), None)
                if duplicate is not None:
                    duplicate.duplicate = True
                    return duplicate, True
            self._evict_for(len(source))
            job_id = secrets.token_hex(16)
            job = AuditJob(
                job_id=job_id, cache_key=cache_key, original_name=original_name, suffix=suffix,
                identifier=identifier, source_version=version, source_sha256=source_hash,
                source_bytes=len(source),
            )
            run_dir = self._job_dir(job_id)
            run_dir.mkdir(mode=0o700)
            source_path = run_dir / ("source" + suffix)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            fd = os.open(source_path, flags, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(source)
                stream.flush()
                os.fsync(stream.fileno())
            self.jobs[job_id] = job
            self._save(job)
            job.future = self.executor.submit(self._run, job)
            return job, False

    def _run(self, job: AuditJob) -> None:
        run_dir = self._job_dir(job.job_id)
        source_path = run_dir / ("source" + job.suffix)
        output_dir = run_dir / "report-data"

        def progress(stage: str) -> None:
            with self.lock:
                if job.cancel_event.is_set():
                    raise PaperAuditCancelled()
                job.status = "ANALYZING"
                job.stage = stage
                self._save(job)

        try:
            with self.lock:
                if job.cancel_event.is_set():
                    job.status = "CANCELLED"
                    job.stage = "Cancelled before analysis started"
                    self._save(job)
                    return
                job.status = "ANALYZING"
                job.stage = "Reading source bytes"
                self._save(job)
            self._read_source(source_path, job.source_bytes, job.source_sha256)
            run_paper_audit(
                source_path, output_dir, job.identifier, job.source_version,
                progress_callback=progress, cancellation_check=job.cancel_event.is_set,
            )
            report_path = output_dir / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            with self.lock:
                if job.cancel_event.is_set():
                    shutil.rmtree(output_dir, ignore_errors=True)
                    job.status = "CANCELLED"
                    job.stage = "Cancelled; partial report removed"
                    self._save(job)
                    return
                job.status = "COMPLETED"
                job.stage = "Complete. Review the reported coverage and limitations."
                job.decision = report["decision"]
                job.candidate_count = len(report["candidate_anomalies"])
                job.scope_question_count = len(report["possible_scope_differences"])
                job.checks_attempted = report["checks_attempted"]
                job.extraction_status = report["extraction"]["status"]
                job.extraction_format = report["extraction"]["original_format"]
                job.scan_complete = report["discovery"]["scan_complete"]
                job.unsupported_checks = report["unsupported_checks"][:16]
                job.detector_eligibility = [
                    {"detector_id": item.get("detector_id"), "status": item.get("status"),
                     "checked_operands": item.get("checked_operands", 0),
                     "reasons": item.get("reasons", [])[:8]}
                    for item in report["detector_eligibility"][:32]
                ]
                self._save(job)
                self._evict_for(0, preserve={job.job_id})
        except PaperAuditCancelled:
            with self.lock:
                if output_dir.exists() and not output_dir.is_symlink():
                    shutil.rmtree(output_dir, ignore_errors=True)
                job.status = "CANCELLED"
                job.stage = "Cancelled at a safe analysis boundary; partial report removed"
                self._save(job)
        except LocalUIError as exc:
            self._fail(job, exc.code, output_dir)
        except Invalid:
            self._fail(job, "INPUT_UNSUPPORTED_OR_INVALID", output_dir)
        except OSError:
            self._fail(job, "LOCAL_OPERATION_FAILED", output_dir)
        except Exception:
            self._fail(job, "ANALYSIS_FAILED", output_dir)

    @staticmethod
    def _read_source(path: Path, expected_size: int, expected_hash: str) -> bytes:
        try:
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise LocalUIError("UNSAFE_LOCAL_SOURCE", 500)
            if info.st_size != expected_size or info.st_size > MAX_SOURCE_BYTES:
                raise LocalUIError("LOCAL_SOURCE_CHANGED", 409)
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as stream:
                data = stream.read(MAX_SOURCE_BYTES + 1)
            if len(data) != expected_size or _hash(data) != expected_hash:
                raise LocalUIError("LOCAL_SOURCE_CHANGED", 409)
            return data
        except LocalUIError:
            raise
        except OSError as exc:
            raise LocalUIError("LOCAL_SOURCE_UNAVAILABLE", 500) from exc

    def _fail(self, job: AuditJob, code: str, output_dir: Path) -> None:
        with self.lock:
            if output_dir.exists() and not output_dir.is_symlink():
                shutil.rmtree(output_dir, ignore_errors=True)
            job.status = "FAILED"
            job.stage = "The run stopped. Retry uses the same pinned input and settings."
            job.error_code = code
            self._save(job)

    def cancel(self, job_id: str) -> AuditJob:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise LocalUIError("RUN_NOT_FOUND", 404)
            if job.status not in ACTIVE_STATES:
                return job
            job.cancel_event.set()
            if job.future and job.future.cancel():
                job.status = "CANCELLED"
                job.stage = "Cancelled before analysis started"
            else:
                job.status = "CANCELLING"
                job.stage = "Stop requested; the current bounded stage is finishing"
            self._save(job)
            return job

    def retry(self, job_id: str) -> tuple[AuditJob, bool]:
        with self.lock:
            previous = self.jobs.get(job_id)
            if previous is None:
                raise LocalUIError("RUN_NOT_FOUND", 404)
            if previous.status in ACTIVE_STATES:
                raise LocalUIError("RUN_STILL_ACTIVE", 409)
            source_path = self._job_dir(job_id) / ("source" + previous.suffix)
            source = self._read_source(source_path, previous.source_bytes, previous.source_sha256)
            return self.submit(
                previous.original_name, previous.suffix, source,
                previous.identifier, previous.source_version, force=True,
            )

    def get(self, job_id: str) -> AuditJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise LocalUIError("RUN_NOT_FOUND", 404)
        return job

    def list_public(self) -> list[dict[str, Any]]:
        with self.lock:
            return [job.public() for job in sorted(self.jobs.values(),
                                                   key=lambda item: item.created_at_utc, reverse=True)]

    def report(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            job = self.get(job_id)
            if job.status != "COMPLETED":
                raise LocalUIError("REPORT_NOT_READY", 409)
            self._validate_run_layout(self._job_dir(job_id), job.suffix)
            report_dir = self._job_dir(job_id) / "report-data"
            report_path = report_dir / "report.json"
            html_path = report_dir / "report.html"
            self._validate_report_path(report_dir, directory=True)
            self._validate_report_path(report_path, max_bytes=MAX_API_REPORT_BYTES)
            self._validate_report_path(html_path, max_bytes=MAX_API_REPORT_BYTES)
            if report_path.stat().st_size > MAX_API_REPORT_BYTES or html_path.stat().st_size > MAX_API_REPORT_BYTES:
                raise LocalUIError("REPORT_TOO_LARGE_FOR_INTERFACE", 413)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")
            all_findings = report["candidate_anomalies"]
            all_scope_questions = report["possible_scope_differences"]
            findings = [{
                key: item.get(key) for key in (
                    "id", "type", "status", "numerator_exact", "denominator_exact",
                    "reported_percent", "recomputed_percent", "expected_included_exact",
                    "source_total_exact", "excluded_values_exact", "reported_included_exact",
                    "denominator_provenance", "table_id", "table", "cell_id", "precision",
                    "scope_label", "_possible_alternate_denominators",
                    "interpretation", "required_review", "source_anchors",
                ) if key in item
            } for item in all_findings[:256]]
            scope_questions = [{
                key: item.get(key) for key in (
                    "id", "type", "status", "values_exact", "reported_percent",
                    "numerator_exact", "column_denominator_exact",
                    "compatible_alternate_denominators_exact", "scope_label",
                    "table", "interpretation", "required_review", "source_anchors",
                ) if key in item
            } for item in all_scope_questions[:128]]
            return {
                "job": job.public(),
                "meaning": report["meaning"],
                "capture_status": report["source"]["capture_status"],
                "source_hash": report["source"]["sha256"],
                "extracted_text_hash": report["extraction"]["text_sha256"],
                "ocr_performed": report["extraction"]["ocr_performed"],
                "extraction_warnings": report["extraction"]["warnings"],
                "findings": findings,
                "findings_total": len(all_findings),
                "scope_questions": scope_questions,
                "scope_questions_total": len(all_scope_questions),
                "full_report_html": html,
            }

    @staticmethod
    def _validate_report_path(path: Path, *, directory: bool = False,
                              max_bytes: int = MAX_EXPORT_BYTES) -> os.stat_result:
        try:
            info = os.lstat(path)
        except OSError as exc:
            raise LocalUIError("LOCAL_REPORT_UNAVAILABLE", 500) from exc
        is_reparse = bool(getattr(info, "st_file_attributes", 0) & 0x400)
        if stat.S_ISLNK(info.st_mode) or is_reparse:
            raise LocalUIError("UNSAFE_LOCAL_REPORT", 500)
        if directory:
            if not stat.S_ISDIR(info.st_mode):
                raise LocalUIError("UNSAFE_LOCAL_REPORT", 500)
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > max_bytes:
            raise LocalUIError("UNSAFE_LOCAL_REPORT", 500)
        return info

    def export_zip(self, job_id: str) -> bytes:
        with self.lock:
            job = self.get(job_id)
            if job.status != "COMPLETED":
                raise LocalUIError("REPORT_NOT_READY", 409)
            run_dir = self._job_dir(job_id)
            self._validate_run_layout(run_dir, job.suffix)
            report_dir = run_dir / "report-data"
            output = io.BytesIO()
            command = (
                "After extracting this package, replay the source with:\n"
                + shlex.join(("python", "-m", "researchwitness", "paper-audit", "source" + job.suffix,
                              "--identifier", job.identifier, "--source-version", job.source_version,
                              "--output", "replay-report")) + "\n"
                "This reruns the local scanner; it is not an independent observation.\n"
            )
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for rel in ("report.json", "report.html", "extracted-text.txt", "paper-document.json"):
                    path = report_dir / rel
                    if path.exists():
                        self._validate_report_path(path)
                        archive.writestr(rel, path.read_bytes())
                source_name = "source" + job.suffix
                archive.writestr(source_name, self._read_source(
                    run_dir / source_name, job.source_bytes, job.source_sha256,
                ))
                archive.writestr("REPLAY.txt", command)
            data = output.getvalue()
            if len(data) > MAX_EXPORT_BYTES:
                raise LocalUIError("EXPORT_TOO_LARGE", 413)
            return data

    def delete_all(self) -> None:
        with self.lock:
            if any(job.status in ACTIVE_STATES for job in self.jobs.values()):
                raise LocalUIError("ACTIVE_RUNS_MUST_FINISH_OR_CANCEL", 409)
            if self.store_warning:
                raise LocalUIError("LOCAL_DATA_REQUIRES_MANUAL_REVIEW", 409)
            for job_id in list(self.jobs):
                path = self._job_dir(job_id)
                self._validate_run_layout(path, self.jobs[job_id].suffix)
                shutil.rmtree(path)
            self.jobs.clear()

    def close(self) -> None:
        with self.lock:
            for job in self.jobs.values():
                if job.status in ACTIVE_STATES:
                    job.cancel_event.set()
        self.executor.shutdown(wait=True, cancel_futures=True)


class LocalUIHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], store: LocalAuditStore, token: str):
        self.store = store
        self.token = token
        super().__init__(address, LocalUIRequestHandler)


class LocalUIRequestHandler(http.server.BaseHTTPRequestHandler):
    server: LocalUIHTTPServer
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, _format: str, *args: object) -> None:
        # Local filenames, identifiers, and paths must not spill into terminal logs.
        return

    def _send(self, status: int, body: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_API_REPORT_BYTES:
            self._error(LocalUIError("RESPONSE_TOO_LARGE", 413))
            return
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, error: LocalUIError) -> None:
        self._json(error.http_status, {"error": error.code})

    def _guard(self, *, api: bool = False, mutation: bool = False) -> None:
        try:
            address = ipaddress.ip_address(self.client_address[0])
        except ValueError as exc:
            raise LocalUIError("LOOPBACK_ONLY", 403) from exc
        if not address.is_loopback:
            raise LocalUIError("LOOPBACK_ONLY", 403)
        expected_host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host", "").casefold() != expected_host.casefold():
            raise LocalUIError("HOST_NOT_ALLOWED", 403)
        if api:
            supplied = self.headers.get("X-RW-Token", "")
            if not hmac.compare_digest(supplied, self.server.token):
                raise LocalUIError("SESSION_TOKEN_INVALID", 403)
        origin = self.headers.get("Origin")
        expected_origin = f"http://{expected_host}"
        if origin and origin != expected_origin:
            raise LocalUIError("CROSS_ORIGIN_REQUEST_REJECTED", 403)
        if mutation and self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise LocalUIError("CROSS_ORIGIN_REQUEST_REJECTED", 403)

    def do_GET(self) -> None:
        try:
            self._guard()
            if self.path == "/":
                template = (Path(__file__).with_name("webui") / "index.html").read_text(encoding="utf-8")
                body = template.replace("__RW_SESSION_TOKEN__", self.server.token).encode("utf-8")
                self._send(200, body, "text/html; charset=utf-8")
                return
            if self.path in {"/app.js", "/style.css"}:
                path = Path(__file__).with_name("webui") / self.path.lstrip("/")
                body = path.read_bytes()
                mime = "text/javascript; charset=utf-8" if self.path.endswith(".js") else "text/css; charset=utf-8"
                self._send(200, body, mime)
                return
            self._guard(api=True)
            if self.path == "/api/jobs":
                self._json(200, {"jobs": self.server.store.list_public(),
                                 "warning": self.server.store.store_warning})
                return
            match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})", self.path)
            if match:
                self._json(200, {"job": self.server.store.get(match.group(1)).public()})
                return
            match = re.fullmatch(r"/api/reports/([0-9a-f]{32})", self.path)
            if match:
                self._json(200, self.server.store.report(match.group(1)))
                return
            match = re.fullmatch(r"/api/exports/([0-9a-f]{32})\.zip", self.path)
            if match:
                data = self.server.store.export_zip(match.group(1))
                self._send(200, data, "application/zip", {
                    "Content-Disposition": f"attachment; filename=researchwitness-report-{match.group(1)[:8]}.zip",
                })
                return
            self._error(LocalUIError("NOT_FOUND", 404))
        except LocalUIError as exc:
            self._error(exc)
        except (OSError, ValueError, KeyError, TypeError):
            self._error(LocalUIError("LOCAL_OPERATION_FAILED", 500))

    def do_POST(self) -> None:
        try:
            self._guard(api=True, mutation=True)
            if self.path == "/api/jobs":
                self._submit()
                return
            match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/(cancel|retry)", self.path)
            if match:
                job_id, action = match.groups()
                if action == "cancel":
                    job = self.server.store.cancel(job_id)
                    self._json(200, {"job": job.public()})
                else:
                    job, duplicate = self.server.store.retry(job_id)
                    self._json(202, {"job": job.public(), "duplicate": duplicate})
                return
            self._error(LocalUIError("NOT_FOUND", 404))
        except LocalUIError as exc:
            self._error(exc)
        except (OSError, ValueError, KeyError, TypeError):
            self._error(LocalUIError("LOCAL_OPERATION_FAILED", 500))

    def do_DELETE(self) -> None:
        try:
            self._guard(api=True, mutation=True)
            if self.path != "/api/data":
                self._error(LocalUIError("NOT_FOUND", 404))
                return
            self.server.store.delete_all()
            self._json(200, {"status": "LOCAL_RUN_DATA_DELETED"})
        except LocalUIError as exc:
            self._error(exc)
        except OSError:
            self._error(LocalUIError("LOCAL_DELETE_FAILED", 500))

    def _submit(self) -> None:
        if self.headers.get("Transfer-Encoding"):
            raise LocalUIError("CHUNKED_UPLOAD_NOT_SUPPORTED", 411)
        if self.headers.get_content_type() != "application/octet-stream":
            raise LocalUIError("UPLOAD_CONTENT_TYPE_REQUIRED", 415)
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError as exc:
            raise LocalUIError("CONTENT_LENGTH_REQUIRED", 411) from exc
        if size <= 0:
            raise LocalUIError("EMPTY_FILE")
        if size > MAX_SOURCE_BYTES:
            raise LocalUIError("FILE_TOO_LARGE", 413)
        original_name, suffix = _safe_filename(self.headers.get("X-RW-Name", ""))
        identifier = _decoded_header(self.headers.get("X-RW-Identifier"), limit=2000,
                                     default="local:uploaded-paper")
        version = _decoded_header(self.headers.get("X-RW-Version"), limit=100,
                                  default="user-supplied/unverified")
        source = self.rfile.read(size)
        if len(source) != size:
            raise LocalUIError("UPLOAD_INCOMPLETE", 400)
        job, duplicate = self.server.store.submit(
            original_name, suffix, source, identifier or "local:uploaded-paper",
            version or "user-supplied/unverified",
        )
        self._json(200 if duplicate else 202, {"job": job.public(), "duplicate": duplicate})


def create_server(data_directory: Path | None = None, *, port: int = 0) -> LocalUIHTTPServer:
    store = LocalAuditStore(data_directory)
    token = secrets.token_urlsafe(32)
    try:
        return LocalUIHTTPServer(("127.0.0.1", port), store, token)
    except Exception:
        store.close()
        raise


def serve_ui(*, port: int = 8765, open_browser: bool = True) -> int:
    server = create_server(port=port)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"ResearchWitness local paper audit: {url}", flush=True)
    print("Local-only; no source retrieval or external requests. Press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url, new=2)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        server.store.close()
    return 0
