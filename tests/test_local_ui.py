"""Stdlib-only acceptance for the JATS presentation adapter, adapted from PR #12."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import quote
import zipfile

from researchwitness import jats_product
from researchwitness.__main__ import main
from researchwitness_ui import server as ui
from tools import make_release, quality_gate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "examples/synthetic-jats/article.xml").read_bytes()


@contextmanager
def running_server(root: Path):
    server = ui.create_server(root)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


class LocalUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = running_server(self.root / "state")
        self.server = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def request(self, method, path, body=None, headers=None, *, token=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        values = {"Host": f"127.0.0.1:{self.server.server_port}"}
        if token:
            values["X-RW-Token"] = self.server.token
        values.update(headers or {})
        try:
            connection.request(method, path, body, values)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def upload(self, source=SOURCE, filename="article.xml", document_id="synthetic", flags=None):
        return self.request("POST", "/api/jobs", source, {
            "X-RW-Filename": quote(filename), "X-RW-Document-ID": document_id,
            "X-RW-Slices": json.dumps(flags or {}),
        })

    def wait(self, job_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            status, _, body = self.request("GET", f"/api/jobs/{job_id}")
            self.assertEqual(status, 200)
            job = json.loads(body)["job"]
            if job["status"] not in {"queued", "running"}:
                return job
            time.sleep(.01)
        self.fail("Audit did not finish within eight seconds")

    def completed(self, **kwargs):
        status, _, data = self.upload(**kwargs)
        self.assertEqual(status, 202, data)
        job = self.wait(json.loads(data)["job"]["job_id"])
        self.assertEqual(job["status"], "done", job)
        return job

    def test_empty_history_and_static_assets(self):
        status, headers, body = self.request("GET", "/", token=False)
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), body)
        self.assertIn(b"not a custody boundary", body)
        self.assertIn(b"sandbox", body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", headers["Content-Security-Policy"])
        for name in ("app.js", "style.css"):
            self.assertEqual(self.request("GET", "/" + name, token=False)[0], 200)
        self.assertEqual(json.loads(self.request("GET", "/api/jobs")[2]), {"jobs": []})
        self.assertEqual(self.request("GET", "/missing")[0], 404)

    def test_host_origin_fetch_site_and_token_guards(self):
        for method, path, headers, token in (
            ("GET", "/", {"Host": "evil.example"}, False),
            ("GET", "/api/jobs", {}, False),
            ("GET", "/api/jobs", {"X-RW-Token": "wrong"}, True),
            ("GET", "/api/jobs", {"Origin": "https://evil.example"}, True),
            ("POST", "/api/jobs", {"Sec-Fetch-Site": "cross-site"}, True),
            ("GET", "/", {"Sec-Fetch-Site": "same-site"}, False),
        ):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(method, path, headers=headers, token=token)[0], 403)
        self.assertEqual(self.request("GET", "/api/jobs", headers={
            "Origin": f"http://127.0.0.1:{self.server.server_port}",
            "Sec-Fetch-Site": "same-origin",
        })[0], 200)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        try:
            connection.putrequest("GET", "/")
            connection.putheader("Host", f"127.0.0.1:{self.server.server_port}")
            connection.endheaders()
            self.assertEqual(connection.getresponse().status, 403)
        finally:
            connection.close()

    def test_upload_report_deterministic_export_and_pinned_replay(self):
        job = self.completed(flags={name: True for name in ui.SLICE_FLAGS})
        job_id = job["job_id"]
        self.assertFalse(job["paper_error_established"])
        self.assertEqual(job["summary"], {
            "arithmetic_matches": 1, "mismatch_candidates": 1, "abstentions": 1,
        })
        status, headers, html = self.request("GET", f"/api/jobs/{job_id}/report")
        self.assertEqual(status, 200)
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        self.assertNotIn("script-src", headers["Content-Security-Policy"])
        self.assertIn(b"synthetic", html)
        status, headers, data = self.request("GET", f"/api/jobs/{job_id}/export")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        self.assertEqual(data, self.request("GET", f"/api/jobs/{job_id}/export")[2])
        output = self.root / "extracted"
        output.mkdir()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(set(archive.namelist()), set(ui.BUNDLE_FILES) | {"REPLAY.txt"})
            self.assertIn(f"researchwitness replay-jats <dir> --expected-manifest-sha256 {job['manifest_sha256']}".encode(), archive.read("REPLAY.txt"))
            self.assertEqual(hashlib.sha256(archive.read("manifest.json")).hexdigest(), job["manifest_sha256"])
            for name in ui.BUNDLE_FILES:
                (output / name).write_bytes(archive.read(name))
        self.assertEqual(jats_product.replay_bundle(output, job["manifest_sha256"])["status"], "verified")
        content = json.loads((output / "report.json").read_bytes())
        self.assertIn("table_projection", content)
        self.assertIn("denominator_evidence_trace", content)
        self.assertFalse(content["paper_error_established"])

    def test_non_jats_empty_oversize_and_invalid_metadata(self):
        for filename in ("paper.txt", "paper.md", "paper.pdf"):
            status, _, body = self.upload(filename=filename)
            self.assertEqual(status, 415)
            self.assertIn(b"JATS XML only on this version", body)
        self.assertEqual(self.upload(source=b"")[0], 413)
        status, _, _ = self.request("POST", "/api/jobs", b"", {
            "Content-Length": str(ui.MAX_SOURCE_BYTES + 1), "X-RW-Filename": "article.xml",
        })
        self.assertEqual(status, 413)
        self.assertEqual(self.upload(document_id="../../outside")[0], 400)
        self.assertEqual(self.upload(flags={"include_made_up": True})[0], 400)
        self.assertEqual(self.upload(flags={"include_structure": "yes"})[0], 400)
        for filename in ("../outside.xml", "%2e%2e%2foutside.xml", "bad\nname.xml"):
            self.assertEqual(self.upload(filename=filename)[0], 400)
        self.assertEqual(self.request("GET", "/api/jobs/" + "a" * 32)[0], 404)
        self.assertEqual(self.server.store.list_jobs(), [])

    def test_failed_audit_and_report_not_ready(self):
        status, _, data = self.upload(source=b"not XML")
        self.assertEqual(status, 202)
        job_id = json.loads(data)["job"]["job_id"]
        job = self.wait(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertIn("JATS", job["error"])
        self.assertEqual(self.request("GET", f"/api/jobs/{job_id}/report")[0], 409)
        self.assertEqual(self.request("GET", f"/api/jobs/{job_id}/export")[0], 409)

    def test_delete_retention_and_reopen_history(self):
        self.server.store.max_jobs = 1
        first = self.completed()
        second = self.completed(document_id="second")
        self.assertEqual(self.request("GET", f"/api/jobs/{first['job_id']}")[0], 404)
        self.assertFalse((self.server.store.root / first["job_id"]).exists())
        self.server.store.close()
        reopened = ui.LocalAuditStore(self.server.store.root)
        try:
            self.assertEqual(reopened.list_jobs()[0]["job_id"], second["job_id"])
            self.assertEqual(reopened.export(second["job_id"]), self.server.store.export(second["job_id"]))
        finally:
            reopened.close()
        self.assertEqual(self.request("DELETE", f"/api/jobs/{second['job_id']}")[0], 200)
        self.assertEqual(self.server.store.list_jobs(), [])

    def test_cancel_only_queued_and_never_delete_running(self):
        entered, release = threading.Event(), threading.Event()
        original = jats_product.audit_source

        def blocking(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise ValueError("test worker timed out")
            return original(*args, **kwargs)

        with mock.patch.object(jats_product, "audit_source", side_effect=blocking):
            try:
                first = json.loads(self.upload()[2])["job"]
                self.assertTrue(entered.wait(3))
                second = json.loads(self.upload(document_id="queued")[2])["job"]
                self.assertEqual(self.request("POST", f"/api/jobs/{first['job_id']}/cancel")[0], 409)
                self.assertEqual(self.request("DELETE", f"/api/jobs/{first['job_id']}")[0], 409)
                status, _, body = self.request("POST", f"/api/jobs/{second['job_id']}/cancel")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["job"]["status"], "cancelled")
                self.assertEqual(self.request("DELETE", f"/api/jobs/{second['job_id']}")[0], 200)
            finally:
                release.set()
            self.assertEqual(self.wait(first["job_id"])["status"], "done")

    def test_tampered_or_linked_bundle_fails_closed(self):
        job = self.completed()
        path = self.server.store.root / job["job_id"] / "bundle" / "report.html"
        original = path.read_bytes()
        path.write_bytes(original + b"changed")
        self.assertEqual(self.request("GET", f"/api/jobs/{job['job_id']}/export")[0], 409)
        path.unlink()
        target = self.root / "outside.html"
        target.write_bytes(original)
        try:
            path.symlink_to(target)
        except OSError:
            return
        self.assertEqual(self.request("GET", f"/api/jobs/{job['job_id']}/report")[0], 400)

    def test_bounded_http_workers_and_retention_bytes(self):
        for _ in range(ui.MAX_HTTP_WORKERS):
            self.assertTrue(self.server.slots.acquire(False))
        try:
            with self.assertRaises((OSError, http.client.HTTPException)):
                self.request("GET", "/")
        finally:
            for _ in range(ui.MAX_HTTP_WORKERS):
                self.server.slots.release()
        with mock.patch.object(ui, "MAX_STORE_BYTES", 1):
            self.assertEqual(self.upload()[0], 429)


class LocalUIContractTests(unittest.TestCase):
    def test_cli_port_and_lazy_dispatch(self):
        with mock.patch.object(ui, "serve_ui", return_value=0) as serve:
            self.assertEqual(main(["ui", "--port", "0", "--no-browser", "--state-dir", "private"]), 0)
            serve.assert_called_once_with(port=0, open_browser=False, state_dir=Path("private"))
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["ui", "--port", "65536"]), 2)

    def test_core_scan_unchanged_and_ui_scan_rejects_forbidden_primitives(self):
        quality_gate.scan_core()
        quality_gate.scan_ui()
        for source in ("import http.client", "import urllib.request", "from urllib import request",
                       "import socket", "import subprocess", "import requests", "import pickle",
                       "import ctypes", "eval('1')", "exec('pass')", "compile('1', '', 'eval')",
                       "__import__('socket')", "LocalUIHTTPServer(('0.0.0.0', 0), None, '')"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "researchwitness_ui").mkdir()
                (root / "researchwitness_ui/server.py").write_text(source)
                with mock.patch.object(quality_gate, "ROOT", root), self.assertRaises(RuntimeError):
                    quality_gate.scan_ui()

    def test_release_inventory_includes_ui_and_assets(self):
        selected = {path.relative_to(ROOT).as_posix() for path in make_release.included_files()}
        for name in ("__init__.py", "server.py", "webui/index.html", "webui/app.js", "webui/style.css"):
            self.assertIn("researchwitness_ui/" + name, selected)

    def test_restart_marks_interrupted_job_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ui.LocalAuditStore(Path(directory))
            blocker = threading.Event()
            executor = ThreadPoolExecutor(max_workers=1)
            executor.submit(blocker.wait, 3)
            store.executor.shutdown()
            store.executor = executor
            try:
                job = store.submit(SOURCE, "article.xml", "synthetic", {})
                store.get(job["job_id"]).future.cancel()
            finally:
                blocker.set()
                store.close()
            reopened = ui.LocalAuditStore(Path(directory))
            try:
                self.assertEqual(reopened.list_jobs()[0]["status"], "failed")
                self.assertIn("Server stopped", reopened.list_jobs()[0]["error"])
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
