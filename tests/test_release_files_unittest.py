from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from tools import make_release


class ReleaseInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="researchwitness-release-test-")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        (self.root / "validation").mkdir()
        (self.root / ".gitignore").write_text(
            "validation/ignored-private.json\n", encoding="utf-8"
        )
        (self.root / "validation" / "tracked.json").write_text(
            "{\"status\": \"public\"}\n", encoding="utf-8"
        )
        subprocess.run(
            ["git", "add", ".gitignore", "validation/tracked.json"],
            cwd=self.root,
            check=True,
        )
        self.root_patch = patch.object(make_release, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_untracked_and_ignored_files_do_not_enter_source_inventory_or_zip(self) -> None:
        (self.root / "validation" / "untracked-private.json").write_text(
            "private", encoding="utf-8"
        )
        (self.root / "validation" / "ignored-private.json").write_text(
            "private", encoding="utf-8"
        )

        selected = {
            path.relative_to(self.root).as_posix()
            for path in make_release.included_files(include_checksums=False)
        }
        self.assertEqual(selected, {".gitignore", "validation/tracked.json"})

        output = self.root / "dist" / "source.zip"
        output.parent.mkdir()
        make_release.write_source_zip(output, "0.test")
        with zipfile.ZipFile(output) as archive:
            names = set(archive.namelist())
        self.assertIn("researchwitness-0.test/validation/tracked.json", names)
        self.assertNotIn("researchwitness-0.test/validation/untracked-private.json", names)
        self.assertNotIn("researchwitness-0.test/validation/ignored-private.json", names)

    def test_selected_symlink_fails_closed(self) -> None:
        target = self.root.parent / "private-release-test-target"
        target.write_text("private", encoding="utf-8")
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        link = self.root / "validation" / "linked.json"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        subprocess.run(["git", "add", "validation/linked.json"], cwd=self.root, check=True)

        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            make_release.included_files()

    def test_unstaged_release_file_changes_fail_closed(self) -> None:
        tracked = self.root / "validation" / "tracked.json"
        tracked.write_text("{\"status\": \"unstaged\"}\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "unstaged changes"):
            make_release.included_files()

    def test_intent_to_add_release_file_fails_closed(self) -> None:
        candidate = self.root / "validation" / "intent-to-add.json"
        candidate.write_text("private", encoding="utf-8")
        subprocess.run(
            ["git", "add", "--intent-to-add", "validation/intent-to-add.json"],
            cwd=self.root,
            check=True,
        )

        with self.assertRaisesRegex(RuntimeError, "unstaged changes"):
            make_release.included_files()


if __name__ == "__main__":
    unittest.main()
