"""Local preview adapted from PR #12; not a protected custody boundary."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import hmac
import http.server
import io
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import threading
import time
from urllib.parse import unquote_to_bytes
import webbrowser
import zipfile

from researchwitness import jats_product
from researchwitness._jats_files import read_regular

MAX_SOURCE_BYTES = jats_product.MAX_SOURCE_BYTES
MAX_JOBS = 10
MAX_STORE_BYTES = 512 * 1024 * 1024
MAX_HTTP_WORKERS = 8
MAX_METADATA_BYTES = 64 * 1024
SLICE_FLAGS = (
    "include_structure", "include_odds_ratio", "include_prose_flows",
    "include_prisma_flows", "include_count_totals", "include_sd_se_n",
    "include_denominator_trace",
)
BUNDLE_FILES = ("source.xml", "report.json", "report.html", "manifest.json")
FILE_LIMITS = dict(zip(BUNDLE_FILES, (
    MAX_SOURCE_BYTES, jats_product.MAX_REPORT_BYTES,
    jats_product.MAX_REPORT_BYTES, jats_product.MAX_MANIFEST_BYTES,
)))
JOB_ID = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
TERMINAL = {"done", "failed", "cancelled"}


class LocalUIError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _directory(path: Path, *, create: bool = False) -> None:
    for component in reversed((path, *path.parents)):
        if create and not component.exists() and not component.is_symlink():
            component.mkdir(mode=0o700)
        info = component.lstat()
        if (not stat.S_ISDIR(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise LocalUIError("State path must contain only real directories", 500)


def default_state_directory() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "ResearchWitness" / "jats-preview"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "researchwitness" / "jats-preview"


def _filename(encoded: str) -> str:
    if not encoded or len(encoded) > 1536 or re.search(r"%(?![0-9a-fA-F]{2})", encoded):
        raise LocalUIError("Invalid filename")
    try:
        name = unquote_to_bytes(encoded).decode("utf-8")
    except UnicodeError as exc:
        raise LocalUIError("Invalid filename") from exc
    if (len(name) > 255 or any(ord(c) < 32 for c in name)
            or "/" in name or "\\" in name or re.search(r"%[0-9a-fA-F]{2}", name)):
        raise LocalUIError("Invalid filename")
    if Path(name).suffix.lower() not in {".xml", ".nxml"}:
        raise LocalUIError("JATS XML only on this version", 415)
    return name


@dataclass
class AuditJob:
    job_id: str
    filename: str
    document_id: str
    flags: dict
    source_sha256: str
    created: float = field(default_factory=time.time)
    status: str = "queued"
    summary: dict = field(default_factory=dict)
    manifest_sha256: str | None = None
    error: str | None = None
    future: object = field(default=None, repr=False)

    def public(self) -> dict:
        return {key: value for key, value in vars(self).items() if key != "future"} | {
            "paper_error_established": False,
        }


class LocalAuditStore:
    def __init__(self, root: Path, *, max_jobs: int = MAX_JOBS):
        self.root = Path(os.path.abspath(root.expanduser()))
        _directory(self.root, create=True)
        if os.name != "nt":
            self.root.chmod(0o700)
        self.max_jobs = max_jobs
        self.lock = threading.RLock()
        self.jobs: dict[str, AuditJob] = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jats-preview")
        try:
            self._load()
        except Exception:
            self.executor.shutdown(wait=True)
            raise

    def _path(self, job_id: str) -> Path:
        if not JOB_ID.fullmatch(job_id):
            raise LocalUIError("Job not found", 404)
        _directory(self.root)
        path = self.root / job_id
        _directory(path)
        return path

    def _save(self, job: AuditJob) -> None:
        path = self._path(job.job_id)
        pending = path / ("job-" + secrets.token_hex(8) + ".pending")
        data = jats_product.canonical_json(job.public())
        with pending.open("xb") as stream:
            stream.write(data)
        os.replace(pending, path / "job.json")

    def _load(self) -> None:
        for path in self.root.iterdir():
            if not JOB_ID.fullmatch(path.name):
                continue
            try:
                job = self._load_job(path)
                self._job_size(job.job_id)
                if job.status in {"queued", "running"}:
                    job.status, job.error = "failed", "Server stopped before this audit completed; upload again."
                    self._save(job)
            except (LocalUIError, OSError, ValueError, TypeError, KeyError):
                self._discard_partial(path)
                continue
            self.jobs[job.job_id] = job
        self._retain(0)

    def _load_job(self, path: Path) -> AuditJob:
        _directory(path)
        row = jats_product.strict_json(read_regular(path / "job.json", MAX_METADATA_BYTES))
        expected = (set(AuditJob.__dataclass_fields__) - {"future"}) | {"paper_error_established"}
        if (set(row) != expected
                or row.get("job_id") != path.name or row.get("status") not in TERMINAL | {"queued", "running"}
                or type(row.get("created")) not in (float, int)
                or type(row.get("document_id")) is not str
                or not jats_product.IDENTIFIER.fullmatch(row["document_id"])
                or type(row.get("source_sha256")) is not str
                or not jats_product.HASH.fullmatch(row["source_sha256"])
                or type(row.get("filename")) is not str
                or (row.get("manifest_sha256") is not None
                    and (type(row["manifest_sha256"]) is not str
                         or not jats_product.HASH.fullmatch(row["manifest_sha256"])))
                or type(row.get("flags")) is not dict
                or set(row["flags"]) - set(SLICE_FLAGS)
                or any(type(value) is not bool for value in row["flags"].values())
                or type(row.get("summary")) is not dict):
            raise LocalUIError("Invalid saved job metadata", 500)
        return AuditJob(**{key: row[key] for key in AuditJob.__dataclass_fields__ if key != "future"})

    def _discard_partial(self, path: Path) -> None:
        if path.parent != self.root or not JOB_ID.fullmatch(path.name):
            return
        try:
            _directory(path)
            shutil.rmtree(path)
        except (OSError, LocalUIError):
            return

    def _job_size(self, job_id: str) -> int:
        total = 0
        for item in self._path(job_id).iterdir():
            if item.name == "bundle":
                _directory(item)
                children = list(item.iterdir())
            else:
                children = [item]
            for child in children:
                info = child.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise LocalUIError("Unsafe state file", 500)
                total += info.st_size
        return total

    def _size(self) -> int:
        return sum(self._job_size(job_id) for job_id in self.jobs)

    def _retain(self, reserve: int) -> None:
        while len(self.jobs) + bool(reserve) > self.max_jobs or self._size() + reserve > MAX_STORE_BYTES:
            old = sorted((job for job in self.jobs.values() if job.status in TERMINAL), key=lambda job: job.created)
            if not old:
                raise LocalUIError("Local retention limit reached; wait for active jobs", 429)
            self.delete(old[0].job_id)

    def submit(self, source: bytes, filename: str, document_id: str, flags: dict) -> dict:
        filename = _filename(filename)
        if not source or len(source) > MAX_SOURCE_BYTES:
            raise LocalUIError("Source is empty or exceeds the JATS upload limit", 413)
        if not jats_product.IDENTIFIER.fullmatch(document_id):
            raise LocalUIError("Document ID must be 1–120 ASCII letters, digits, dot, underscore, colon or hyphen; start with a letter or digit")
        if type(flags) is not dict or set(flags) - set(SLICE_FLAGS) or any(type(v) is not bool for v in flags.values()):
            raise LocalUIError("Invalid JATS slice flags")
        with self.lock:
            self._retain(len(source) * 2 + 2 * jats_product.MAX_REPORT_BYTES + MAX_METADATA_BYTES * 2)
            job = AuditJob(secrets.token_hex(16), filename, document_id, flags, hashlib.sha256(source).hexdigest())
            path = self.root / job.job_id
            path.mkdir(mode=0o700)
            try:
                with (path / "upload.xml").open("xb") as stream:
                    stream.write(source)
                self.jobs[job.job_id] = job
                self._save(job)
                job.future = self.executor.submit(self._run, job)
            except Exception:
                job.status = "failed"
                self.jobs.pop(job.job_id, None)
                self._discard_partial(path)
                raise
            return job.public()

    def _run(self, job: AuditJob) -> None:
        try:
            with self.lock:
                if job.status != "queued":
                    return
                job.status = "running"
                self._save(job)
            path = self._path(job.job_id)
            result = jats_product.audit_source(
                path / "upload.xml", path / "bundle", job.document_id,
                expected_source_sha256=job.source_sha256, **job.flags,
            )
            with self.lock:
                job.summary = result["summary"]
                job.manifest_sha256 = result["manifest_sha256"]
                job.status = "done"
                self._save(job)
        except Exception:
            with self.lock:
                job.status = "failed"
                job.error = "JATS audit failed: use well-formed supported JATS XML and a private, unchanged state directory."
                try:
                    self._save(job)
                except (OSError, LocalUIError):
                    pass

    def get(self, job_id: str) -> AuditJob:
        if not JOB_ID.fullmatch(job_id) or job_id not in self.jobs:
            raise LocalUIError("Job not found", 404)
        return self.jobs[job_id]

    def list_jobs(self) -> list[dict]:
        with self.lock:
            return [job.public() for job in sorted(self.jobs.values(), key=lambda job: job.created, reverse=True)]

    def cancel(self, job_id: str) -> dict:
        with self.lock:
            job = self.get(job_id)
            if job.status != "queued":
                raise LocalUIError("Only queued jobs can be cancelled; running audits cannot be interrupted", 409)
            job.status = "cancelled"
            job.future.cancel()
            self._save(job)
            return job.public()

    def delete(self, job_id: str) -> None:
        with self.lock:
            job = self.get(job_id)
            if job.status not in TERMINAL:
                raise LocalUIError("Wait for completion or cancel a queued job before deleting", 409)
            path = self._path(job_id)
            self._size()
            shutil.rmtree(path)
            del self.jobs[job_id]

    def bundle(self, job_id: str) -> dict[str, bytes]:
        job = self.get(job_id)
        if job.status != "done":
            raise LocalUIError("Report is not ready", 409)
        path = self._path(job_id) / "bundle"
        _directory(path)
        data = {name: read_regular(path / name, FILE_LIMITS[name]) for name in BUNDLE_FILES}
        if hashlib.sha256(data["manifest.json"]).hexdigest() != job.manifest_sha256:
            raise LocalUIError("Bundle integrity check failed", 409)
        manifest = jats_product.strict_json(data["manifest.json"])
        for name in jats_product.PAYLOADS:
            if manifest["files"][name] != {"sha256": hashlib.sha256(data[name]).hexdigest(), "bytes": len(data[name])}:
                raise LocalUIError("Bundle integrity check failed", 409)
        return data

    def report(self, job_id: str) -> bytes:
        with self.lock:
            return self.bundle(job_id)["report.html"]

    def export(self, job_id: str) -> bytes:
        with self.lock:
            data = {f"bundle/{name}": value for name, value in self.bundle(job_id).items()}
            pin = self.get(job_id).manifest_sha256
            data["REPLAY.txt"] = (
                "Extract this ZIP, open a terminal in the extracted directory, and run\n"
                "with the same ResearchWitness installation:\n\n"
                f"researchwitness replay-jats bundle --expected-manifest-sha256 {pin}\n\n"
                "This is a local preview, not a custody boundary or scientific error finding.\n"
            ).encode("ascii")
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                for name in sorted(data):
                    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = 0o100600 << 16
                    archive.writestr(info, data[name])
            return output.getvalue()

    def close(self) -> None:
        self.executor.shutdown(wait=True)


class LocalUIHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], store: LocalAuditStore, token: str):
        if address[0] != "127.0.0.1":
            raise ValueError("Local UI must bind only to 127.0.0.1")
        self.store, self.token = store, token
        self.slots = threading.BoundedSemaphore(MAX_HTTP_WORKERS)
        super().__init__(address, LocalUIRequestHandler)

    def process_request(self, request, client_address) -> None:
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def server_close(self) -> None:
        super().server_close()
        self.store.close()


class LocalUIRequestHandler(http.server.BaseHTTPRequestHandler):
    server: LocalUIHTTPServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, _format: str, *args: object) -> None:
        return

    def _send(self, status: int, body: bytes, mime: str, *, report: bool = False, attachment: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        csp = ("sandbox; default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'" if report else
               "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Frame-Options", "SAMEORIGIN" if report else "DENY")
        if attachment:
            self.send_header("Content-Disposition", "attachment; filename=researchwitness-jats.zip")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, jats_product.canonical_json(data), "application/json; charset=utf-8")

    def _guard(self, *, api: bool = False) -> None:
        if self.client_address[0] != "127.0.0.1":
            raise LocalUIError("Loopback only", 403)
        host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get_all("Host") != [host]:
            raise LocalUIError("Host not allowed", 403)
        origins = self.headers.get_all("Origin", [])
        if origins not in ([], [f"http://{host}"]):
            raise LocalUIError("Cross-origin request rejected", 403)
        if self.headers.get_all("Sec-Fetch-Site", []) not in ([], ["same-origin"], ["none"]):
            raise LocalUIError("Cross-origin request rejected", 403)
        if api:
            tokens = self.headers.get_all("X-RW-Token", [])
            if len(tokens) != 1 or not hmac.compare_digest(tokens[0].encode("utf-8"), self.server.token.encode("ascii")):
                raise LocalUIError("Session token invalid", 403)

    def _dispatch(self) -> None:
        self._guard()
        if self.command == "GET" and self.path in ("/", "/app.js", "/style.css"):
            name, mime = {
                "/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
            }[self.path]
            body = (Path(__file__).with_name("webui") / name).read_bytes()
            body = body.replace(b"__RW_SESSION_TOKEN__", self.server.token.encode("ascii"))
            self._send(200, body, mime + "; charset=utf-8")
            return
        self._guard(api=True)
        store = self.server.store
        if self.path == "/api/jobs":
            if self.command == "GET":
                self._json(200, {"jobs": store.list_jobs()})
                return
            if self.command == "POST":
                if self.headers.get("Transfer-Encoding") is not None:
                    raise LocalUIError("Chunked uploads are not supported")
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                    raise LocalUIError("One Content-Length is required", 411)
                size = int(lengths[0])
                if not 0 < size <= MAX_SOURCE_BYTES:
                    raise LocalUIError("Source is empty or exceeds the JATS upload limit", 413)
                filename = self.headers.get("X-RW-Filename", "")
                _filename(filename)
                document_id = self.headers.get("X-RW-Document-ID", "")
                encoded_flags = self.headers.get("X-RW-Slices", "{}")
                if len(encoded_flags) > 2048:
                    raise LocalUIError("Invalid JATS slice flags")
                flags = jats_product.strict_json(encoded_flags.encode("ascii"))
                source = self.rfile.read(size)
                if len(source) != size:
                    raise LocalUIError("Incomplete upload")
                self._json(202, {"job": store.submit(source, filename, document_id, flags)})
                return
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})(?:/(report|export|cancel))?", self.path)
        if match:
            job_id, action = match.groups()
            if self.command == "GET" and action == "report":
                self._send(200, store.report(job_id), "text/html; charset=utf-8", report=True)
                return
            if self.command == "GET" and action == "export":
                self._send(200, store.export(job_id), "application/zip", attachment=True)
                return
            if self.command == "POST" and action == "cancel":
                self._json(200, {"job": store.cancel(job_id)})
                return
            if action is None and self.command == "GET":
                with store.lock:
                    self._json(200, {"job": store.get(job_id).public()})
                return
            if action is None and self.command == "DELETE":
                store.delete(job_id)
                self._json(200, {"deleted": True})
                return
        raise LocalUIError("Not found", 404)

    def _handle(self) -> None:
        try:
            self._dispatch()
        except LocalUIError as exc:
            self._json(exc.status, {"error": str(exc)})
        except (OSError, ValueError, KeyError, TypeError):
            self._json(400, {"error": "Local operation failed; check the input and private state directory"})

    do_GET = _handle
    do_POST = _handle
    do_DELETE = _handle


def create_server(state_dir: Path | None = None, *, port: int = 0) -> LocalUIHTTPServer:
    store = LocalAuditStore(state_dir if state_dir is not None else default_state_directory())
    try:
        return LocalUIHTTPServer(("127.0.0.1", port), store, secrets.token_hex(32))
    except Exception:
        store.close()
        raise


def serve_ui(*, port: int = 8765, open_browser: bool = True, state_dir: Path | None = None) -> int:
    with create_server(state_dir, port=port) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"ResearchWitness local preview: {url}", flush=True)
        print("Not a custody boundary; running audits cannot be interrupted.", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
