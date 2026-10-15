"""Synthetic regression and adversarial tests for the bounded PDF table aid."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from tools.pdf_percentage_audit import (
    MAX_PDF_BYTES,
    PDFSourceError,
    SANDBOX_IMAGE_ENV,
    _extract_layout_text,
    audit_pdf_percentage_tables,
    parse_pdf_layout_text,
)


def layout(body: str) -> str:
    return body.strip("\n") + "\f"


class PDFPercentageAuditTests(unittest.TestCase):
    @staticmethod
    def seccomp_info_result(options='["name=seccomp,profile=builtin"]'):
        return mock.Mock(returncode=0, stdout=options)

    def test_extraction_fails_closed_without_a_pinned_sandbox_image(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("tools.pdf_percentage_audit.shutil.which") as which:
                with self.assertRaisesRegex(PDFSourceError, "SHA-256-pinned"):
                    _extract_layout_text(b"%PDF-1.7\n")
        which.assert_not_called()

    def test_extraction_fails_closed_when_docker_is_unavailable(self):
        with mock.patch.dict(os.environ, {SANDBOX_IMAGE_ENV: "sha256:" + "a" * 64}, clear=True):
            with mock.patch("tools.pdf_percentage_audit.shutil.which", return_value=None):
                with self.assertRaisesRegex(PDFSourceError, "Docker is required"):
                    _extract_layout_text(b"%PDF-1.7\n")

    def test_extraction_rejects_a_sandbox_image_id_mismatch(self):
        configured = "sha256:" + "a" * 64
        with mock.patch.dict(os.environ, {SANDBOX_IMAGE_ENV: configured}, clear=True):
            with mock.patch("tools.pdf_percentage_audit.shutil.which", return_value="/usr/bin/docker"):
                with mock.patch(
                    "tools.pdf_percentage_audit.subprocess.run",
                    side_effect=[
                        self.seccomp_info_result(),
                        mock.Mock(returncode=0, stdout="sha256:" + "b" * 64 + "\n"),
                    ],
                ):
                    with mock.patch("tools.pdf_percentage_audit.subprocess.Popen") as popen:
                        with self.assertRaisesRegex(PDFSourceError, "unavailable or unverified"):
                            _extract_layout_text(b"%PDF-1.7\n")
        popen.assert_not_called()

    def test_extraction_fails_closed_without_the_docker_builtin_seccomp_profile(self):
        configured = "sha256:" + "a" * 64
        with mock.patch.dict(os.environ, {SANDBOX_IMAGE_ENV: configured}, clear=True):
            with mock.patch("tools.pdf_percentage_audit.shutil.which", return_value="/usr/bin/docker"):
                with mock.patch(
                    "tools.pdf_percentage_audit.subprocess.run",
                    return_value=self.seccomp_info_result('["name=seccomp,profile=unconfined"]'),
                ):
                    with mock.patch("tools.pdf_percentage_audit.subprocess.Popen") as popen:
                        with self.assertRaisesRegex(PDFSourceError, "built-in default seccomp"):
                            _extract_layout_text(b"%PDF-1.7\n")
        popen.assert_not_called()

    def test_extraction_rejects_image_baked_environment_entrypoint_or_volumes(self):
        configured = "sha256:" + "a" * 64
        bad_configs = (
            '{"Env":["APP_MODE=test"],"Entrypoint":null,"Volumes":null}',
            '{"Env":null,"Entrypoint":["/bin/sh"],"Volumes":null}',
            '{"Env":null,"Entrypoint":null,"Volumes":{"/data":{}}}',
        )
        for bad_config in bad_configs:
            with self.subTest(bad_config=bad_config):
                with mock.patch.dict(os.environ, {SANDBOX_IMAGE_ENV: configured}, clear=True):
                    with mock.patch("tools.pdf_percentage_audit.shutil.which", return_value="/usr/bin/docker"):
                        with mock.patch(
                            "tools.pdf_percentage_audit.subprocess.run",
                            side_effect=[
                                self.seccomp_info_result(),
                                mock.Mock(returncode=0, stdout=configured + "\n"),
                                mock.Mock(returncode=0, stdout=bad_config),
                            ],
                        ):
                            with mock.patch("tools.pdf_percentage_audit.subprocess.Popen") as popen:
                                with self.assertRaisesRegex(PDFSourceError, "no baked environment"):
                                    _extract_layout_text(b"%PDF-1.7\n")
                popen.assert_not_called()

    def test_extraction_uses_network_disabled_credential_free_container(self):
        configured = "sha256:" + "a" * 64
        extracted = b"Table 1: Example\nCount (%)\nCategory 1 (100.00)\n"
        child = mock.Mock()
        child.stdout = io.BytesIO(extracted)
        child.wait.return_value = 0

        def popen_side_effect(command, **kwargs):
            self.assertEqual(kwargs["stdin"].read(), b"%PDF-1.7 synthetic bytes")
            self.assertEqual(kwargs["env"], {"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"})
            self.assertIn("--network", command)
            self.assertEqual(command[command.index("--network") + 1], "none")
            self.assertIn("--read-only", command)
            self.assertIn("--cap-drop", command)
            self.assertEqual(command[command.index("--cap-drop") + 1], "ALL")
            self.assertIn("--pids-limit", command)
            self.assertIn("--memory", command)
            self.assertIn("HTTP_PROXY=", command)
            self.assertIn("HTTPS_PROXY=", command)
            self.assertIn("ALL_PROXY=", command)
            self.assertIn("no-new-privileges:true", command)
            self.assertNotIn("seccomp=unconfined", command)
            self.assertIn("--cidfile", command)
            Path(command[command.index("--cidfile") + 1]).write_text("a" * 64, encoding="ascii")
            self.assertNotIn("--rm", command)
            self.assertFalse(any(arg in {"-v", "--volume", "--mount"} for arg in command))
            return child

        with mock.patch.dict(os.environ, {SANDBOX_IMAGE_ENV: configured}, clear=True):
            with mock.patch("tools.pdf_percentage_audit.shutil.which", return_value="/usr/bin/docker"):
                with mock.patch(
                    "tools.pdf_percentage_audit.subprocess.run",
                    side_effect=[
                        self.seccomp_info_result(),
                        mock.Mock(returncode=0, stdout=configured + "\n"),
                        mock.Mock(
                            returncode=0,
                            stdout='{"Env":null,"Entrypoint":null,"Volumes":null}',
                        ),
                        mock.Mock(returncode=0, stdout=""),
                    ],
                ):
                    with mock.patch(
                        "tools.pdf_percentage_audit.subprocess.Popen",
                        side_effect=popen_side_effect,
                    ):
                        self.assertEqual(
                            _extract_layout_text(b"%PDF-1.7 synthetic bytes"),
                            extracted.decode("utf-8"),
                        )

    def test_timeout_removes_verified_container_id_after_killing_docker_client(self):
        configured = "sha256:" + "a" * 64
        child = mock.Mock()
        child.stdout = io.BytesIO(b"")
        child.wait.side_effect = [subprocess.TimeoutExpired("docker run", 20), 137]
        child.poll.return_value = 137

        def start_child(command, **kwargs):
            Path(command[command.index("--cidfile") + 1]).write_text("b" * 64, encoding="ascii")
            return child

        with mock.patch.dict(os.environ, {SANDBOX_IMAGE_ENV: configured}, clear=True):
            with mock.patch("tools.pdf_percentage_audit.shutil.which", return_value="/usr/bin/docker"):
                with mock.patch(
                    "tools.pdf_percentage_audit.subprocess.run",
                    side_effect=[
                        self.seccomp_info_result(),
                        mock.Mock(returncode=0, stdout=configured + "\n"),
                        mock.Mock(returncode=0, stdout='{"Env":null,"Entrypoint":null,"Volumes":null}'),
                        mock.Mock(returncode=0, stdout=""),
                    ],
                ) as docker_run:
                    with mock.patch("tools.pdf_percentage_audit.subprocess.Popen", side_effect=start_child) as popen:
                        with self.assertRaisesRegex(PDFSourceError, "20-second extraction limit"):
                            _extract_layout_text(b"%PDF-1.7 synthetic bytes")
        child.kill.assert_called_once()
        cleanup_command = docker_run.call_args_list[-1].args[0]
        self.assertEqual(cleanup_command[-4:], ["container", "rm", "--force", "b" * 64])

    def test_cleanup_failure_fails_closed_after_pdf_extraction(self):
        configured = "sha256:" + "a" * 64
        child = mock.Mock()
        child.stdout = io.BytesIO(b"Table 1: Example\nCount (%)\nCategory 1 (100.00)\n")
        child.wait.return_value = 0

        def start_child(command, **kwargs):
            Path(command[command.index("--cidfile") + 1]).write_text("c" * 64, encoding="ascii")
            return child
        with mock.patch.dict(os.environ, {SANDBOX_IMAGE_ENV: configured}, clear=True):
            with mock.patch("tools.pdf_percentage_audit.shutil.which", return_value="/usr/bin/docker"):
                with mock.patch(
                    "tools.pdf_percentage_audit.subprocess.run",
                    side_effect=[
                        self.seccomp_info_result(),
                        mock.Mock(returncode=0, stdout=configured + "\n"),
                        mock.Mock(returncode=0, stdout='{"Env":null,"Entrypoint":null,"Volumes":null}'),
                        mock.Mock(returncode=1, stderr="permission denied"),
                    ],
                ):
                    with mock.patch("tools.pdf_percentage_audit.subprocess.Popen", side_effect=start_child):
                        with self.assertRaisesRegex(PDFSourceError, "container cleanup"):
                            _extract_layout_text(b"%PDF-1.7 synthetic bytes")

    def test_infers_percent_context_from_repeated_count_denominator_matches(self):
        text = layout(
            """Table 1: Reasons for study completion

Reasons for study completion                 Number of participants (N=20)
Category A                                                        10 (50.00)
Category B                                                         5 (25.00)
Category C                                                         3 (15.00)
Category D                                                         2 (11.00)
Legends: FAS, analysis population"""
        )
        source_hash = hashlib.sha256(b"synthetic PDF source").hexdigest()
        report = parse_pdf_layout_text(text, source_hash)
        self.assertEqual(report["source_sha256"], source_hash)
        self.assertEqual(report["tables_inspected"], 1)
        self.assertEqual(report["percentage_cells_reviewed"], 4)
        self.assertEqual(
            [row["status"] for row in report["results"]],
            ["arithmetic_match", "arithmetic_match", "arithmetic_match",
             "arithmetic_mismatch_candidate"],
        )
        mismatch = report["results"][-1]
        self.assertEqual(mismatch["evidence"]["row_label"], "Category D")
        self.assertEqual(mismatch["numerator"], 2)
        self.assertEqual(mismatch["denominator"], 20)
        self.assertEqual(mismatch["reported_percent"], "11.00")
        self.assertEqual(mismatch["contract_expected_percent"], "10.00")
        self.assertEqual(
            mismatch["evidence"]["percentage_context_basis"],
            "repeated_count_denominator_matches",
        )
        page = text.split("\f")[0]
        evidence = mismatch["evidence"]
        excerpt = page[evidence["page_text_char_start"]:evidence["page_text_char_end"]]
        self.assertEqual(excerpt.strip(), evidence["row_quote"])

    def test_explicit_percentage_header_can_surface_a_single_mismatch(self):
        text = layout(
            """Table 2: Summary
Count (n) and percentage (N=20)
Category A    2 (20.00)"""
        )
        result = parse_pdf_layout_text(text, "a" * 64)["results"][0]
        self.assertEqual(result["status"], "arithmetic_mismatch_candidate")
        self.assertEqual(result["contract_expected_percent"], "10.00")
        self.assertEqual(
            result["evidence"]["percentage_context_basis"],
            "explicit_percent_header_or_symbol",
        )

    def test_abstains_when_unmarked_parenthetical_values_are_not_corroborated(self):
        text = layout(
            """Table 3: One-row summary
Number of participants (N=10)
Category A    1 (9.00)"""
        )
        result = parse_pdf_layout_text(text, "b" * 64)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(
            result["reason"], "percentage_context_not_explicit_or_corroborated"
        )

    def test_skips_mean_and_standard_deviation_table(self):
        text = layout(
            """Table 4: Measurements
Measure       Mean (SD)       N=20
Measure A     10.5 (2.1)"""
        )
        report = parse_pdf_layout_text(text, "c" * 64)
        self.assertEqual(report["tables_inspected"], 0)
        self.assertEqual(report["results"], [])

    def test_abstains_on_conflicting_header_denominators(self):
        text = layout(
            """Table 5: Counts
Number of participants N=20; complete cases n=18
Category A    2 (10.00)"""
        )
        result = parse_pdf_layout_text(text, "d" * 64)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "conflicting_table_header_denominators")
        self.assertIsNone(result["denominator"])

    def test_does_not_truncate_non_integer_header_denominators(self):
        for denominator_text in ("N=20.5", "N=1,000", "N=20/18", "N=20-18"):
            with self.subTest(denominator_text=denominator_text):
                text = layout(
                    f"""Table 5: Counts
Number of participants {denominator_text}
Category A    2 (10.00)
Category B    4 (20.00)"""
                )
                result = parse_pdf_layout_text(text, "d" * 64)["results"][0]
                self.assertEqual(result["status"], "scope_ambiguous")
                self.assertEqual(
                    result["reason"], "no_explicit_table_header_denominator"
                )
                self.assertIsNone(result["denominator"])

    def test_abstains_when_table_footnote_marks_percentages_as_weighted(self):
        text = layout(
            """Table 6: Counts
Number of participants and percentage (N=20)
Category A    2 (10.00)
Category B    4 (20.00)
Percentages were weighted for age."""
        )
        result = parse_pdf_layout_text(text, "e" * 64)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "adjustment_method_scope_not_mapped")
        self.assertIsNone(result["denominator"])
        note = result["evidence"]["adjustment_note"]
        self.assertEqual(note["page"], 1)
        self.assertIn("weighted for age", note["quote"])
        page = text.split("\f")[0]
        source_span = page[note["page_text_char_start"]:note["page_text_char_end"]]
        source_span_normalized = " ".join(source_span.split())
        note_quote_normalized = " ".join(note["quote"].replace(" | ", " ").split())
        self.assertEqual(source_span_normalized, note_quote_normalized)

    def test_abstains_when_header_indicates_row_specific_denominators(self):
        text = layout(
            """Table 7: Counts
Values are n (% n/N), overall population N=20
Category A    2 (10.00)"""
        )
        result = parse_pdf_layout_text(text, "f" * 64)["results"][0]
        self.assertEqual(result["status"], "scope_ambiguous")
        self.assertEqual(result["reason"], "row_specific_denominator_not_mapped")
        self.assertIsNone(result["denominator"])

    def test_abstains_when_source_rounding_convention_is_stated(self):
        text = layout(
            """Table 8: Counts
Number of participants and percentage (N=20)
Category A    2 (9.99)
Category B    4 (20.00)
Percentages were truncated for display."""
        )
        result = parse_pdf_layout_text(text, "1" * 64)["results"][0]
        self.assertEqual(result["status"], "rounding_ambiguous")
        self.assertEqual(result["reason"], "source_rounding_convention_not_modeled")
        self.assertIn(
            "truncated",
            result["evidence"]["rounding_note"]["quote"].lower(),
        )

    def test_pdf_byte_audit_rejects_non_pdf_and_oversized_input(self):
        with self.assertRaises(PDFSourceError):
            audit_pdf_percentage_tables(b"<!doctype html><html></html>")
        with self.assertRaises(PDFSourceError):
            audit_pdf_percentage_tables(b"%PDF-1.7" + b"x" * MAX_PDF_BYTES)

    def test_layout_parser_requires_a_sha256_for_original_pdf(self):
        with self.assertRaises(PDFSourceError):
            parse_pdf_layout_text(layout("Table 1"), "not-a-hash")


if __name__ == "__main__":
    unittest.main()
