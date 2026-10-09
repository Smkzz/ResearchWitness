"""Loopback API and local-run lifecycle tests for the novice interface."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
import urllib.parse
import zipfile
from io import BytesIO
from unittest.mock import patch

from researchwitness.local_ui import (
    ACTIVE_STATES, LocalAuditStore, LocalUIError, LocalUIHTTPServer,
)
from researchwitness.paper_audit import PaperAuditCancelled, run_paper_audit


TABLE_PAPER = (
    "# Results\n\n"
    "| Outcome | Group A (n=30) |\n"
    "| --- | ---: |\n"
    "| At least 75%, n (%) | 23 (73.3) |\n"
).encode("utf-8")


class LocalUITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rw-local-ui-test-")
        self.root = Path(self.temporary.name) / "store"
        self.store = LocalAuditStore(self.root)
        self.server = None
        self.thread = None

    def start_server(self):
        token = "local-ui-test-token"
        try:
            self.server = LocalUIHTTPServer(("127.0.0.1", 0), self.store, token)
        except PermissionError as exc:
            self.skipTest(f"sandbox denies loopback socket binding: {exc}")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.token = token

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
        self.store.close()
        self.temporary.cleanup()

    def request(self, method, path, *, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        all_headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if path.startswith("/api/"):
            all_headers["X-RW-Token"] = self.token
        all_headers.update(headers or {})
        conn.request(method, path, body=body, headers=all_headers)
        response = conn.getresponse()
        data = response.read()
        result = response.status, response.getheaders(), data
        conn.close()
        return result

    def upload(self, content=TABLE_PAPER, *, filename="sample.md", identifier="synthetic:local-ui", version="fixture-v1"):
        return self.request(
            "POST", "/api/jobs", body=content,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(content)),
                "X-RW-Name": urllib.parse.quote(filename, safe=""),
                "X-RW-Identifier": urllib.parse.quote(identifier, safe=""),
                "X-RW-Version": urllib.parse.quote(version, safe=""),
            },
        )

    def wait_terminal(self, job_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status, _, body = self.request("GET", f"/api/jobs/{job_id}")
            self.assertEqual(status, 200)
            job = json.loads(body)["job"]
            if job["status"] not in ACTIVE_STATES:
                return job
            time.sleep(0.025)
        self.fail("local audit did not reach a terminal state within 10 seconds")

    def test_host_token_origin_and_filename_checks_fail_closed(self):
        self.start_server()
        status, _, page = self.request("GET", "/", host="attacker.invalid")
        self.assertEqual(status, 403)
        self.assertNotIn(self.token.encode(), page)

        status, _, body = self.request("GET", "/api/jobs", headers={"X-RW-Token": "wrong"})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "SESSION_TOKEN_INVALID")

        status, _, body = self.request(
            "GET", "/api/jobs", headers={"Origin": "https://attacker.invalid"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "CROSS_ORIGIN_REQUEST_REJECTED")

        status, _, body = self.upload(filename="..%2foutside.md")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "FILENAME_INVALID")

    def test_nested_percent_encoded_filenames_fail_closed(self):
        from researchwitness.local_ui import _safe_filename

        for encoded in (
            "..%252foutside.md",
            "..%255coutside.md",
            "%252e%252e%252foutside.md",
            "paper%250a.md",
        ):
            with self.subTest(encoded=encoded):
                with self.assertRaisesRegex(LocalUIError, "FILENAME_INVALID"):
                    _safe_filename(encoded)

        # Literal percentage signs that cannot be decoded as escapes remain valid.
        self.assertEqual(_safe_filename("100%25%20complete.md")[0], "100% complete.md")

    def test_upload_report_duplicate_export_replay_and_delete(self):
        job, duplicate = self.store.submit("sample.md", ".md", TABLE_PAPER,
                                           "synthetic:local-ui", "fixture-v1")
        self.assertFalse(duplicate)
        job.future.result(timeout=10)
        completed = job.public()
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["decision"], "CANDIDATES_FOUND")
        self.assertEqual(completed["candidate_count"], 1)

        report = self.store.report(job.job_id)
        self.assertEqual(report["source_hash"], hashlib.sha256(TABLE_PAPER).hexdigest())
        finding = report["findings"][0]
        self.assertEqual((finding["numerator_exact"], finding["denominator_exact"]), ("23", "30"))
        self.assertEqual(finding["reported_percent"], "73.3")
        self.assertEqual(finding["recomputed_percent"], "76.666667")
        self.assertIn("ResearchWitness paper screening report", report["full_report_html"])

        duplicate_job, is_duplicate = self.store.submit("renamed.md", ".md", TABLE_PAPER,
                                                        "synthetic:local-ui", "fixture-v1")
        self.assertTrue(is_duplicate)
        self.assertEqual(duplicate_job.job_id, job.job_id)

        body = self.store.export_zip(job.job_id)
        with zipfile.ZipFile(BytesIO(body)) as archive:
            self.assertEqual(archive.read("source.md"), TABLE_PAPER)
            self.assertIn("report.json", archive.namelist())
            replay = archive.read("REPLAY.txt").decode("utf-8")
            self.assertIn("--identifier synthetic:local-ui", replay)
            self.assertIn("not an independent observation", replay)

        replay_job, _ = self.store.retry(job.job_id)
        self.assertNotEqual(replay_job.job_id, job.job_id)
        replay_job.future.result(timeout=10)
        self.assertEqual(replay_job.status, "COMPLETED")

        self.store.delete_all()
        self.assertEqual(list((self.root / "runs").iterdir()), [])

    def test_report_api_discloses_truncation_and_scope_question_values(self):
        job, _ = self.store.submit("sample.md", ".md", TABLE_PAPER,
                                   "synthetic:scope-ui", "fixture-v1")
        job.future.result(timeout=10)
        report_path = self.root / "runs" / job.job_id / "report-data" / "report.json"
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        finding = report_data["candidate_anomalies"][0]
        report_data["candidate_anomalies"] = [finding] * 257
        anchor = {"quote": "Group A", "element_path": "/article/table-wrap[1]"}
        scope_question = {
            "id": "scope-example", "type": "POSSIBLE_ROW_SPECIFIC_DENOMINATOR",
            "status": "POSSIBLE_SAMPLE_FLOW_DIFFERENCE", "values_exact": ["23", "30"],
            "reported_percent": "73.3", "numerator_exact": "23",
            "column_denominator_exact": "30",
            "compatible_alternate_denominators_exact": ["31"],
            "scope_label": "Group A", "table": "Table 1",
            "interpretation": "Synthetic scope question.", "required_review": "Synthetic review.",
            "source_anchors": [anchor],
        }
        report_data["possible_scope_differences"] = [scope_question] * 129
        report_path.write_text(json.dumps(report_data), encoding="utf-8")

        response = self.store.report(job.job_id)
        self.assertEqual((len(response["findings"]), response["findings_total"]), (256, 257))
        self.assertEqual((len(response["scope_questions"]), response["scope_questions_total"]), (128, 129))
        first_scope = response["scope_questions"][0]
        self.assertEqual(first_scope["compatible_alternate_denominators_exact"], ["31"])
        self.assertEqual(first_scope["scope_label"], "Group A")
        self.assertEqual(first_scope["table"], "Table 1")
        self.assertEqual(first_scope["source_anchors"][0]["element_path"], "/article/table-wrap[1]")

    def test_restart_marks_active_job_interrupted_and_preserves_pinned_source(self):
        job, _ = self.store.submit("sample.md", ".md", TABLE_PAPER,
                                   "synthetic:restart", "fixture-v1")
        job.future.result(timeout=10)
        # Exercise the same persisted transition used when a process dies
        # between its last metadata write and completion.
        job.status = "ANALYZING"
        self.store._save(job)
        self.store.close()
        self.store = LocalAuditStore(self.root)
        recovered = self.store.get(job.job_id)
        self.assertEqual(recovered.status, "INTERRUPTED")
        self.assertEqual(recovered.error_code, "APP_RESTARTED")
        source = self.store._read_source(
            self.store._job_dir(job.job_id) / "source.md",
            len(TABLE_PAPER), hashlib.sha256(TABLE_PAPER).hexdigest(),
        )
        self.assertEqual(source, TABLE_PAPER)

    def test_changed_saved_source_cannot_be_retried(self):
        job, _ = self.store.submit("sample.md", ".md", TABLE_PAPER,
                                   "synthetic:tamper", "fixture-v1")
        job.future.result(timeout=10)
        path = self.store._job_dir(job.job_id) / "source.md"
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(LocalUIError, "LOCAL_SOURCE_CHANGED"):
            self.store.retry(job.job_id)

    def test_unrecognized_local_data_blocks_writes_and_delete(self):
        unknown = self.root / "runs" / "unrecognized.txt"
        unknown.write_text("leave this for manual review", encoding="utf-8")
        replacement = LocalAuditStore(self.root)
        try:
            self.assertEqual(replacement.store_warning, "UNRECOGNIZED_LOCAL_DATA_REQUIRES_MANUAL_REVIEW")
            with self.assertRaisesRegex(LocalUIError, "LOCAL_DATA_REQUIRES_MANUAL_REVIEW"):
                replacement.submit("sample.md", ".md", TABLE_PAPER,
                                   "synthetic:warning", "fixture-v1")
            with self.assertRaisesRegex(LocalUIError, "LOCAL_DATA_REQUIRES_MANUAL_REVIEW"):
                replacement.delete_all()
            self.assertEqual(unknown.read_text(encoding="utf-8"), "leave this for manual review")
        finally:
            replacement.close()

    def test_unknown_file_inside_run_is_not_deleted_as_application_data(self):
        job, _ = self.store.submit("sample.md", ".md", TABLE_PAPER,
                                   "synthetic:unknown-file", "fixture-v1")
        job.future.result(timeout=10)
        unknown = self.store._job_dir(job.job_id) / "manual-notes.txt"
        unknown.write_text("keep this unrecognized file", encoding="utf-8")
        replacement = LocalAuditStore(self.root)
        try:
            self.assertEqual(replacement.store_warning, "LOCAL_RUN_LAYOUT_REQUIRES_MANUAL_REVIEW")
            with self.assertRaisesRegex(LocalUIError, "LOCAL_DATA_REQUIRES_MANUAL_REVIEW"):
                replacement.delete_all()
            self.assertEqual(unknown.read_text(encoding="utf-8"), "keep this unrecognized file")
        finally:
            replacement.close()

    def test_cancel_stops_at_safe_analysis_boundary(self):
        entered = threading.Event()
        release = threading.Event()
        original = __import__("researchwitness.local_ui", fromlist=["run_paper_audit"]).run_paper_audit

        def blocked_audit(source_path, output_dir, identifier, version, *, progress_callback=None,
                          cancellation_check=None):
            if progress_callback:
                progress_callback("Extracting text and source structure")
            entered.set()
            release.wait(timeout=5)
            if cancellation_check and cancellation_check():
                from researchwitness.paper_audit import PaperAuditCancelled
                raise PaperAuditCancelled()
            return original(source_path, output_dir, identifier, version,
                            progress_callback=progress_callback, cancellation_check=cancellation_check)

        with patch("researchwitness.local_ui.run_paper_audit", side_effect=blocked_audit):
            job, _ = self.store.submit("sample.md", ".md", TABLE_PAPER,
                                       "synthetic:cancel", "fixture-v1")
            self.assertTrue(entered.wait(timeout=3))
            cancelled = self.store.cancel(job.job_id)
            self.assertEqual(cancelled.status, "CANCELLING")
            release.set()
            job.future.result(timeout=10)
            self.assertEqual(job.status, "CANCELLED")
            self.assertFalse((self.store._job_dir(job.job_id) / "report-data").exists())

    def test_real_paper_audit_emits_named_stages_and_checks_cancellation(self):
        source = Path(self.temporary.name) / "progress.md"
        source.write_bytes(TABLE_PAPER)
        output = Path(self.temporary.name) / "progress-report"
        stages = []
        report = run_paper_audit(source, output, "synthetic:progress", "fixture-v1",
                                 progress_callback=stages.append)
        self.assertEqual(report["decision"], "CANDIDATES_FOUND")
        self.assertIn("Extracting text and source structure", stages)
        self.assertIn("Checking Markdown table percentages", stages)
        self.assertEqual(stages[-1], "Writing source copy and reproducible report")

        cancel_output = Path(self.temporary.name) / "cancelled-report"
        cancel_now = False

        def progress(stage):
            nonlocal cancel_now
            if stage == "Scanning explicit count statements":
                cancel_now = True

        with self.assertRaises(PaperAuditCancelled):
            run_paper_audit(source, cancel_output, "synthetic:progress", "fixture-v1",
                            progress_callback=progress, cancellation_check=lambda: cancel_now)
        self.assertFalse(cancel_output.exists())


if __name__ == "__main__":
    unittest.main()
