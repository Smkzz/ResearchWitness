"""Real Chromium acceptance tests using only synthetic papers and loopback."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
import unittest
import urllib.parse
import zipfile
from pathlib import Path
from unittest.mock import patch

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # Optional locally; the dedicated CI browser job installs it.
    sync_playwright = None
if sync_playwright is None and os.environ.get("RW_BROWSER_REQUIRED") == "1":
    raise RuntimeError("the dedicated browser qualification job requires Playwright")

from researchwitness import local_ui
from researchwitness.local_ui import LocalAuditStore, LocalUIHTTPServer
from researchwitness.paper_audit import PaperAuditCancelled, run_paper_audit


SYNTHETIC_PAPER = (
    "# Results\n\n"
    "| Outcome | Group A (n=30) |\n"
    "| --- | ---: |\n"
    "| At least 75%, n (%) | 23 (73.3) |\n"
).encode("utf-8")
SLOW_PAPER = b"# Synthetic active job\n\nThis run is held at a test-controlled worker barrier.\n"
COMPLETED_PAPER = SYNTHETIC_PAPER.replace(b"Group A", b"Group B")


def is_same_origin(url: str, expected_origin: str) -> bool:
    try:
        actual = urllib.parse.urlsplit(url)
        expected = urllib.parse.urlsplit(expected_origin)
        actual_port = actual.port or (443 if actual.scheme == "https" else 80 if actual.scheme == "http" else None)
        expected_port = expected.port or (443 if expected.scheme == "https" else 80 if expected.scheme == "http" else None)
    except ValueError:
        return False
    return (actual.scheme.casefold(), (actual.hostname or "").casefold(), actual_port) == (
        expected.scheme.casefold(), (expected.hostname or "").casefold(), expected_port,
    )


def wait_for_result_status(page, expected: str, timeout: int = 10_000) -> None:
    page.wait_for_function(
        "expected => !document.querySelector('#results-panel')?.hidden && "
        "document.querySelector('#result-status')?.textContent.trim() === expected",
        arg=expected, timeout=timeout,
    )


@unittest.skipIf(sync_playwright is None, "Playwright is installed only in the browser qualification job")
class LocalUIBrowserAcceptance(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rw-local-ui-browser-")
        self.screenshot_dir = Path(os.environ.get("RW_BROWSER_SCREENSHOT_DIR", self.temporary.name))
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.store = LocalAuditStore(Path(self.temporary.name) / "store")
        self.server = None
        self.thread = None
        self.release_events: list[threading.Event] = []
        try:
            self.server = LocalUIHTTPServer(("127.0.0.1", 0), self.store, secrets.token_urlsafe(32))
        except OSError as exc:
            self.store.close()
            self.temporary.cleanup()
            if os.environ.get("RW_BROWSER_REQUIRED") == "1":
                raise RuntimeError(f"required browser qualification cannot bind loopback: {exc}") from exc
            self.skipTest(f"this execution environment denies loopback bind: {exc}")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        for event in self.release_events:
            event.set()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
        self.store.close()
        self.temporary.cleanup()

    def make_page(self, browser, *, fail_first_status_for: str | None = None):
        page = browser.new_page(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        if fail_first_status_for:
            target = json.dumps(f"/api/jobs/{fail_first_status_for}")
            page.add_init_script(f"""(() => {{
              const target = {target};
              const originalFetch = window.fetch.bind(window);
              window.__rwStatusFailureInjected = false;
              window.fetch = (input, options = {{}}) => {{
                if (!window.__rwStatusFailureInjected && String(input) === target) {{
                  window.__rwStatusFailureInjected = true;
                  return Promise.reject(new TypeError("synthetic one-shot status disconnect"));
                }}
                return originalFetch(input, options);
              }};
            }})();""")
        off_origin = []
        page_errors = []
        page.on("request", lambda request: off_origin.append(request.url)
                if not is_same_origin(request.url, self.origin) else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(self.origin, wait_until="networkidle")
        return page, off_origin, page_errors

    def test_origin_assertion_checks_scheme_and_port(self):
        port = urllib.parse.urlsplit(self.origin).port
        self.assertTrue(is_same_origin(self.origin + "/", self.origin))
        self.assertFalse(is_same_origin(self.origin.replace("http://", "https://", 1), self.origin))
        self.assertFalse(is_same_origin(f"http://127.0.0.1:{port + 1}/", self.origin))

    def test_upload_evidence_export_replay_reload_error_retry_and_delete(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page, off_origin, page_errors = self.make_page(browser)
                self.assertEqual(page.title(), "ResearchWitness · Local paper audit")
                self.assertTrue(page.locator("#paper-file").evaluate("input => input.labels.length === 1"))
                self.assertEqual(page.locator("#progress-stage").get_attribute("aria-live"), "polite")
                self.assertEqual(page.locator("#error-note").get_attribute("role"), "alert")
                self.assertTrue(page.locator("h1").is_visible())
                self.assertGreaterEqual(page.locator("h2").count(), 4)
                page.keyboard.press("Tab")
                self.assertEqual(page.evaluate("document.activeElement.className"), "skip-link")
                page.keyboard.press("Enter")
                self.assertEqual(urllib.parse.urlparse(page.url).fragment, "main")

                page.locator("#paper-file").set_input_files({
                    "name": "synthetic.md", "mimeType": "text/markdown", "buffer": SYNTHETIC_PAPER,
                })
                self.assertIn("synthetic.md", page.locator("#selected-file").inner_text())
                page.locator("#paper-file").focus()
                for expected_id in ("paper-id", "paper-version", "run-button"):
                    page.keyboard.press("Tab")
                    self.assertEqual(page.evaluate("document.activeElement.id"), expected_id)
                self.assertEqual(
                    page.locator("#run-button").evaluate("button => getComputedStyle(button).outlineStyle"),
                    "solid",
                )
                page.evaluate("""() => {
                  const originalFetch = window.fetch.bind(window);
                  window.__rwUploadCalls = 0;
                  window.__rwUploadPending = false;
                  window.__rwReleaseUpload = null;
                  window.__rwReportPending = false;
                  window.__rwReleaseReport = null;
                  window.__rwBlockedInitialReport = false;
                  window.fetch = async (input, options = {}) => {
                    if (String(input) === "/api/jobs" && options.method === "POST") {
                      window.__rwUploadCalls += 1;
                      window.__rwUploadPending = true;
                      await new Promise(resolve => { window.__rwReleaseUpload = resolve; });
                    }
                    if (String(input).startsWith("/api/reports/") && !window.__rwBlockedInitialReport) {
                      window.__rwBlockedInitialReport = true;
                      window.__rwReportPending = true;
                      await new Promise(resolve => { window.__rwReleaseReport = resolve; });
                    }
                    return originalFetch(input, options);
                  };
                }""")
                page.keyboard.press("Enter")
                page.wait_for_function("window.__rwUploadPending === true", timeout=10_000)
                self.assertEqual(page.evaluate("document.activeElement.id"), "progress-title")
                for control in ("#paper-file", "#paper-id", "#paper-version", "#run-button", "#delete-data"):
                    self.assertTrue(page.locator(control).is_disabled(), control)
                self.assertEqual(page.evaluate("window.__rwUploadCalls"), 1)
                drag_state = page.locator("#drop-zone").evaluate("""zone => {
                  const transfer = new DataTransfer();
                  transfer.items.add(new File(['busy drop'], 'busy.md', {type: 'text/markdown'}));
                  const dragover = new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: transfer});
                  const drop = new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: transfer});
                  zone.dispatchEvent(dragover);
                  zone.dispatchEvent(drop);
                  return {dragoverPrevented: dragover.defaultPrevented, dropPrevented: drop.defaultPrevented};
                }""")
                self.assertTrue(drag_state["dragoverPrevented"])
                self.assertTrue(drag_state["dropPrevented"])
                self.assertIn("synthetic.md", page.locator("#selected-file").inner_text())
                self.assertEqual(urllib.parse.urlparse(page.url).fragment, "main")
                page.evaluate("window.__rwReleaseUpload()")

                page.wait_for_function("window.__rwReportPending === true", timeout=30_000)
                self.assertTrue(page.locator("#progress-panel").is_visible())
                self.assertTrue(page.locator("#results-panel").is_hidden())
                self.assertEqual(page.evaluate("document.activeElement.id"), "progress-title")
                self.assertEqual(page.locator("#progress-stage").inner_text(), "Preparing the saved result")
                self.assertTrue(page.get_by_role("button", name="Cancel this run").is_disabled())
                page.evaluate("window.__rwReleaseReport()")
                wait_for_result_status(page, "Review candidates found", timeout=30_000)
                self.assertIn("23 (73.3)", page.locator("#findings").inner_text())
                self.assertIn("n=30", page.locator("#findings").inner_text())
                self.assertIn("line 3 · byte 32", page.locator("#findings").inner_text())
                page.locator("#full-report-details summary").click()
                page.frame_locator("#full-report").locator("body").wait_for(timeout=10_000)

                desktop_screenshot = self.screenshot_dir / "synthetic-results-desktop.png"
                page.screenshot(path=str(desktop_screenshot), full_page=True)
                self.assertGreater(desktop_screenshot.stat().st_size, 10_000)
                page.set_viewport_size({"width": 390, "height": 844})
                self.assertLessEqual(
                    page.evaluate("document.documentElement.scrollWidth"),
                    page.evaluate("window.innerWidth"),
                )
                mobile_screenshot = self.screenshot_dir / "synthetic-results-mobile.png"
                page.screenshot(path=str(mobile_screenshot), full_page=True)
                self.assertGreater(mobile_screenshot.stat().st_size, 10_000)

                page.evaluate("""() => {
                  const originalFetch = window.fetch.bind(window);
                  window.__rwExportRequestPath = null;
                  window.fetch = (input, options = {}) => {
                    const path = String(input);
                    if (path.startsWith('/api/exports/')) window.__rwExportRequestPath = path;
                    return originalFetch(input, options);
                  };
                }""")
                with page.expect_download(timeout=20_000) as download_info:
                    page.get_by_role("button", name="Export source and report").click()
                download = download_info.value
                export_path = page.evaluate("window.__rwExportRequestPath")
                match = re.fullmatch(r"/api/exports/([0-9a-f]{32})\.zip", export_path or "")
                self.assertIsNotNone(match)
                self.assertEqual(download.suggested_filename, "researchwitness-report.zip")
                exported = Path(self.temporary.name) / "export.zip"
                download.save_as(str(exported))
                with zipfile.ZipFile(exported) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(archive.read("source.md"), SYNTHETIC_PAPER)
                    self.assertIn("report.json", archive.namelist())
                    self.assertIn("report.html", archive.namelist())
                    self.assertIn("REPLAY.txt", archive.namelist())
                    report = json.loads(archive.read("report.json"))
                    self.assertEqual(report["source"]["sha256"], hashlib.sha256(SYNTHETIC_PAPER).hexdigest())

                with page.expect_response(
                    lambda response: response.request.method == "POST" and "/retry" in response.url,
                    timeout=20_000,
                ) as replay_response:
                    page.evaluate("""() => {
                      const originalFetch = window.fetch.bind(window);
                      window.__rwReportGatePending = false;
                      window.__rwReleaseReportGate = null;
                      const reportGate = new Promise(resolve => { window.__rwReleaseReportGate = resolve; });
                      window.fetch = async (input, options = {}) => {
                        if (!window.__rwReportGatePending && String(input).startsWith('/api/reports/')) {
                          window.__rwReportGatePending = true;
                          await reportGate;
                        }
                        return originalFetch(input, options);
                      };
                    }""")
                    page.get_by_role("button", name="Replay this exact input").click()
                self.assertEqual(replay_response.value.status, 200)
                page.wait_for_function("window.__rwReportGatePending === true", timeout=30_000)
                self.assertTrue(page.locator("#progress-panel").is_visible())
                self.assertEqual(page.locator("#progress-stage").inner_text(), "Preparing the saved result")
                self.assertTrue(page.locator("#results-panel").is_hidden())
                self.assertEqual(page.evaluate("document.activeElement.id"), "progress-title")
                page.evaluate("window.__rwReleaseReportGate()")
                wait_for_result_status(page, "Review candidates found", timeout=30_000)
                self.assertEqual(page.evaluate("document.activeElement.id"), "result-status")
                page.reload(wait_until="networkidle")
                page.locator("#history-list .history-item button").first.wait_for(timeout=10_000)
                page.locator("#history-list .history-item button").first.click()
                wait_for_result_status(page, "Review candidates found")
                self.assertTrue(page.locator("#progress-panel").is_hidden())

                page.on("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Delete all ResearchWitness run data").click()
                page.get_by_text("No saved runs.", exact=True).wait_for(timeout=10_000)

                # Inject a deterministic local worker failure; the browser still
                # exercises the actual upload, error state, retry route and UI.
                with patch.object(local_ui, "run_paper_audit", side_effect=OSError("synthetic failure")):
                    page.locator("#paper-file").set_input_files({
                        "name": "synthetic-failure.md", "mimeType": "text/markdown",
                        "buffer": b"# synthetic failure fixture\n",
                    })
                    page.get_by_role("button", name="Run supported checks").click()
                    wait_for_result_status(page, "Run failed", timeout=20_000)
                    self.assertFalse(page.get_by_role("button", name="Retry this run").is_hidden())
                    with page.expect_response(
                        lambda response: response.request.method == "POST" and "/retry" in response.url,
                        timeout=20_000,
                    ) as retry_response:
                        page.get_by_role("button", name="Retry this run").click()
                    self.assertEqual(retry_response.value.status, 200)
                    wait_for_result_status(page, "Run failed", timeout=20_000)

                self.assertEqual(off_origin, [])
                self.assertEqual(page_errors, [])
            finally:
                browser.close()

    def test_active_job_keeps_cancel_target_and_locks_history_selection(self):
        started = threading.Event()
        release = threading.Event()
        self.release_events.append(release)

        def controlled_worker(source_path, output_dir, identifier, version, **kwargs):
            if Path(source_path).read_bytes() == SLOW_PAPER:
                started.set()
                while not release.wait(0.025):
                    if kwargs.get("cancellation_check", lambda: False)():
                        raise PaperAuditCancelled()
            return run_paper_audit(source_path, output_dir, identifier, version, **kwargs)

        with patch.object(local_ui, "run_paper_audit", side_effect=controlled_worker):
            active, _ = self.store.submit("active.md", ".md", SLOW_PAPER, "synthetic:active", "v1")
            self.assertTrue(started.wait(timeout=10))
            completed, _ = self.store.submit(
                "completed.md", ".md", COMPLETED_PAPER, "synthetic:completed", "v1",
            )
            completed.future.result(timeout=20)
            completed_other, _ = self.store.submit(
                "completed-other.md", ".md", COMPLETED_PAPER.replace(b"Group B", b"Group C"),
                "synthetic:completed-other", "v1",
            )
            completed_other.future.result(timeout=20)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page, off_origin, page_errors = self.make_page(
                        browser, fail_first_status_for=active.job_id,
                    )
                    page.locator("#progress-panel").wait_for(state="visible", timeout=10_000)
                    page.get_by_role("button", name="Check run status again").wait_for(
                        state="visible", timeout=10_000,
                    )
                    self.assertEqual(page.evaluate("document.activeElement.id"), "status-retry-button")
                    buttons = page.locator("#history-list .history-item button")
                    page.wait_for_function(
                        "document.querySelectorAll('#history-list .history-item button').length >= 2",
                        timeout=10_000,
                    )
                    self.assertGreaterEqual(buttons.count(), 2)
                    self.assertTrue(all(buttons.nth(index).is_disabled() for index in range(buttons.count())))
                    self.assertTrue(page.get_by_role("button", name="Delete all ResearchWitness run data").is_disabled())
                    self.assertTrue(page.locator("#paper-file").is_disabled())

                    cancel_requests = []
                    page.on("request", lambda request: cancel_requests.append(request.url)
                            if request.method == "POST" and "/cancel" in request.url else None)
                    with page.expect_response(
                        lambda response: response.request.method == "POST"
                        and "/cancel" in response.url,
                        timeout=10_000,
                    ) as cancel_response:
                        page.get_by_role("button", name="Cancel this run").click()
                    self.assertEqual(cancel_response.value.status, 200)
                    release.set()
                    active.future.result(timeout=20)
                    with page.expect_response(
                        lambda response: response.request.method != "POST"
                        and response.url.endswith(f"/api/jobs/{active.job_id}"),
                        timeout=10_000,
                    ) as reconnect_response:
                        page.get_by_role("button", name="Check run status again").click()
                    self.assertEqual(reconnect_response.value.status, 200)
                    wait_for_result_status(page, "Run cancelled", timeout=20_000)
                    self.assertEqual(page.evaluate("document.activeElement.id"), "result-status")
                    self.assertFalse(page.locator("#paper-file").is_disabled())
                    self.assertEqual(len(cancel_requests), 1)
                    self.assertIn(active.job_id, cancel_requests[0])
                    self.assertNotIn(completed.job_id, cancel_requests[0])

                    history = page.locator("#history-list .history-item button")
                    completed_button = page.locator("#history-list .history-item button").filter(
                        has_text="completed.md",
                    )
                    completed_button.wait_for(timeout=10_000)
                    other_completed_button = page.locator("#history-list .history-item button").filter(
                        has_text="completed-other.md",
                    )
                    page.evaluate(f"""() => {{
                      const target = "/api/reports/{completed.job_id}";
                      const originalFetch = window.fetch.bind(window);
                      window.__rwReportCalls = [];
                      window.__rwReportPending = false;
                      window.__rwReleaseReport = null;
                      window.fetch = async (input, options = {{}}) => {{
                        const path = String(input);
                        if (path.startsWith('/api/reports/')) window.__rwReportCalls.push(path);
                        if (path === target) {{
                          window.__rwReportPending = true;
                          await new Promise(resolve => {{ window.__rwReleaseReport = resolve; }});
                        }}
                        return originalFetch(input, options);
                      }};
                    }}""")
                    completed_button.click()
                    page.wait_for_function("window.__rwReportPending === true", timeout=10_000)
                    self.assertEqual(page.evaluate("document.activeElement.id"), "progress-title")
                    self.assertTrue(all(
                        page.locator("#history-list .history-item button").nth(index).is_disabled()
                        for index in range(page.locator("#history-list .history-item button").count())
                    ))
                    other_completed_button.evaluate(
                        "button => button.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}))",
                    )
                    self.assertEqual(page.evaluate("window.__rwReportCalls"), [f"/api/reports/{completed.job_id}"])
                    self.assertTrue(page.locator("#results-panel").is_hidden())
                    page.evaluate("window.__rwReleaseReport()")
                    wait_for_result_status(page, "Review candidates found")
                    self.assertTrue(page.locator("#progress-panel").is_hidden())
                    self.assertTrue(page.locator("#results-panel").is_visible())
                    displayed_source = page.locator("#result-summary").inner_text()
                    self.assertIn(hashlib.sha256(COMPLETED_PAPER).hexdigest(), displayed_source)
                    self.assertNotIn(
                        hashlib.sha256(COMPLETED_PAPER.replace(b"Group B", b"Group C")).hexdigest(),
                        displayed_source,
                    )
                    self.assertEqual(page.evaluate("window.__rwReportCalls"), [f"/api/reports/{completed.job_id}"])
                    self.assertEqual(off_origin, [])
                    self.assertEqual(page_errors, [])
                finally:
                    browser.close()


if __name__ == "__main__":
    unittest.main()
