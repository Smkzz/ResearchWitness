from __future__ import annotations

import subprocess
import tempfile
import unittest
import zipfile
import json
from pathlib import Path
import sys
from unittest.mock import patch

from tools import make_release


class ReleasePackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rw-release-packaging-")
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        (self.root / "docs").mkdir()
        (self.root / "docs" / "custody-worker").mkdir()
        (self.root / "tools").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "README.md").write_text(
            "See [docs/PAPER_AUDIT_CAPABILITIES.md](docs/PAPER_AUDIT_CAPABILITIES.md)\n",
            encoding="utf-8",
        )
        (self.root / "docs" / "RELEASING.md").write_text("tracked release note\n", encoding="utf-8")
        (self.root / "docs" / "PAPER_AUDIT_CAPABILITIES.md").write_text(
            "synthetic product scope\n", encoding="utf-8",
        )
        (self.root / "docs" / "ROADMAP.md").write_text("synthetic roadmap\n", encoding="utf-8")
        (self.root / "docs" / "ACCEPTANCE_LEDGER.md").write_text(
            "synthetic qualification sentinel\n", encoding="utf-8",
        )
        (self.root / "docs" / "VALIDATION.md").write_text(
            "synthetic validation sentinel\n", encoding="utf-8",
        )
        (self.root / "docs" / "owner-private.md").write_text(
            "synthetic owner-only sentinel\n", encoding="utf-8",
        )
        (self.root / "docs" / "custody-worker" / "DEPLOYMENT.md").write_text(
            "synthetic owner deployment sentinel\n", encoding="utf-8",
        )
        (self.root / "tools" / "make_release.py").write_text(
            "# synthetic approved release helper\n", encoding="utf-8",
        )
        (self.root / "tools" / "review_frozen_screen.py").write_text(
            "# synthetic paper-specific qualification sentinel\n", encoding="utf-8",
        )
        (self.root / "tools" / "custody_worker_owner_action.ps1").write_text(
            "# synthetic owner action sentinel\n", encoding="utf-8",
        )
        (self.root / "tests" / "test_private_fixture.py").write_text(
            "# synthetic test-corpus sentinel\n", encoding="utf-8",
        )
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "researchwitness"\nversion = "0.4.0.dev0"\n', encoding="utf-8",
        )
        for directory, filename in (("validation", "reserved-fixture.json"),
                                    ("evidence", "reserved-fixture.json")):
            (self.root / directory).mkdir()
            (self.root / directory / filename).write_text(
                "synthetic reserved-evidence sentinel\n", encoding="utf-8",
            )
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Synthetic Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "README.md", "docs", "tools", "pyproject.toml",
                        "validation", "evidence"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "synthetic release fixture"], cwd=self.root, check=True)

    def tearDown(self):
        self.temporary.cleanup()

    def test_release_selection_omits_untracked_files_and_symlinks(self):
        outside = Path(self.temporary.name) / "outside-secret.txt"
        outside.write_text("synthetic private sentinel\n", encoding="utf-8")
        (self.root / "docs" / "untracked-sentinel.md").write_text(
            "synthetic untracked sentinel\n", encoding="utf-8",
        )
        (self.root / "docs" / "untracked-link.md").symlink_to(outside)

        with patch.object(make_release, "ROOT", self.root):
            selected = {path.relative_to(self.root).as_posix() for path in make_release.included_files()}
            checksum_selected = {
                path.relative_to(self.root).as_posix() for path in make_release.checksum_files()
            }
            self.assertIn("docs/RELEASING.md", selected)
            self.assertIn("tools/make_release.py", selected)
            self.assertNotIn("docs/ACCEPTANCE_LEDGER.md", selected)
            self.assertNotIn("docs/VALIDATION.md", selected)
            self.assertNotIn("docs/owner-private.md", selected)
            self.assertNotIn("docs/custody-worker/DEPLOYMENT.md", selected)
            self.assertNotIn("tools/review_frozen_screen.py", selected)
            self.assertNotIn("tools/custody_worker_owner_action.ps1", selected)
            self.assertNotIn("tests/test_private_fixture.py", selected)
            self.assertFalse(any(name.startswith(("validation/", "evidence/")) for name in selected))
            self.assertNotIn("docs/owner-private.md", checksum_selected)
            self.assertNotIn("docs/ACCEPTANCE_LEDGER.md", checksum_selected)
            self.assertNotIn("docs/VALIDATION.md", checksum_selected)
            self.assertNotIn("docs/custody-worker/DEPLOYMENT.md", checksum_selected)
            self.assertNotIn("tools/review_frozen_screen.py", checksum_selected)
            self.assertNotIn("tools/custody_worker_owner_action.ps1", checksum_selected)
            self.assertNotIn("tests/test_private_fixture.py", checksum_selected)
            self.assertFalse(any(name.startswith(("validation/", "evidence/"))
                                 for name in checksum_selected))
            self.assertNotIn("docs/untracked-sentinel.md", selected)
            self.assertNotIn("docs/untracked-link.md", selected)
            self.assertNotIn("docs/untracked-sentinel.md", checksum_selected)
            archive_path = Path(self.temporary.name) / "source.zip"
            make_release.write_source_zip(archive_path, "test")

        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            bundled_readme = archive.read("researchwitness-test/README.md").decode("utf-8")
            self.assertIn("researchwitness-test/docs/RELEASING.md", names)
            self.assertIn("researchwitness-test/tools/make_release.py", names)
            self.assertIn("docs/PAPER_AUDIT_CAPABILITIES.md", bundled_readme)
            self.assertNotIn("docs/VALIDATION.md", bundled_readme)
            self.assertFalse(any(name.endswith("/docs/owner-private.md") for name in names))
            self.assertFalse(any(name.endswith("/docs/ACCEPTANCE_LEDGER.md") for name in names))
            self.assertFalse(any(name.endswith("/docs/VALIDATION.md") for name in names))
            self.assertFalse(any(name.endswith("/docs/custody-worker/DEPLOYMENT.md") for name in names))
            self.assertFalse(any(name.endswith("/tools/review_frozen_screen.py") for name in names))
            self.assertFalse(any(name.endswith("/tools/custody_worker_owner_action.ps1") for name in names))
            self.assertFalse(any("/tests/" in name for name in names))
            self.assertFalse(any("/validation/" in name or "/evidence/" in name for name in names))
            self.assertFalse(any("untracked-sentinel" in name for name in names))
            self.assertFalse(any("untracked-link" in name for name in names))
            self.assertNotIn(outside.read_text(encoding="utf-8"), [
                archive.read(name).decode("utf-8", errors="replace") for name in names
            ])

    def test_release_allowlists_match_reviewed_paths_exactly(self):
        self.assertEqual(make_release.RELEASE_DOCS, {
            "docs/ARCHITECTURE.md", "docs/EXPRESSION_DSL.md", "docs/MVP.md",
            "docs/PAPER_AUDIT_CAPABILITIES.md", "docs/PROTOCOL.md",
            "docs/RELEASING.md", "docs/ROADMAP.md",
        })
        self.assertEqual(make_release.RELEASE_TOOLS, {
            "tools/make_examples.py", "tools/make_release.py",
            "tools/make_timeline_example.py", "tools/qualify_app_wheel.py",
            "tools/write_schema.py",
        })

    def test_tracked_file_replaced_by_symlink_is_rejected(self):
        tracked = self.root / "docs" / "RELEASING.md"
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_text("synthetic outside bytes\n", encoding="utf-8")
        tracked.unlink()
        tracked.symlink_to(outside)

        with patch.object(make_release, "ROOT", self.root):
            with self.assertRaisesRegex(RuntimeError, "unsafe release input path"):
                make_release.included_files()

    def test_release_build_supports_external_output_directory(self):
        output = Path(self.temporary.name) / "external-output"

        def fake_build(destination: Path) -> Path:
            wheel = destination / "researchwitness-0.4.0.dev0-py3-none-any.whl"
            wheel.write_bytes(b"synthetic wheel bytes")
            return wheel

        with (patch.object(make_release, "ROOT", self.root),
              patch.object(make_release, "write_checksums"),
              patch.object(make_release, "build_wheel", side_effect=fake_build),
              patch.object(sys, "argv", ["make_release", "--output-dir", str(output)])):
            self.assertEqual(make_release.main(), 0)

        manifest_path = output / "ResearchWitness-v0.4.0.dev0-release.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertTrue((output / manifest["source"]["file"]).is_file())
        self.assertTrue((output / manifest["wheel"]["file"]).is_file())
        self.assertTrue((output / "ResearchWitness-v0.4.0.dev0-SHA256SUMS.txt").is_file())

    def test_release_rejects_symlinked_output_manifest_without_following_it(self):
        output = Path(self.temporary.name) / "external-output"
        output.mkdir()
        outside = Path(self.temporary.name) / "outside-manifest-target.txt"
        outside.write_text("preserve this synthetic file\n", encoding="utf-8")
        manifest_path = output / "ResearchWitness-v0.4.0.dev0-release.json"
        manifest_path.symlink_to(outside)

        def fake_build(destination: Path) -> Path:
            wheel = destination / "researchwitness-0.4.0.dev0-py3-none-any.whl"
            wheel.write_bytes(b"synthetic wheel bytes")
            return wheel

        with (patch.object(make_release, "ROOT", self.root),
              patch.object(make_release, "write_checksums"),
              patch.object(make_release, "build_wheel", side_effect=fake_build),
              patch.object(sys, "argv", ["make_release", "--output-dir", str(output)])):
            with self.assertRaisesRegex(RuntimeError, "unsafe existing release destination"):
                make_release.main()
        self.assertEqual(outside.read_text(encoding="utf-8"), "preserve this synthetic file\n")
        self.assertTrue(manifest_path.is_symlink())


if __name__ == "__main__":
    unittest.main()
