"""Regression checks for source-tool filesystem and rate-state admission."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    # Dataclasses in public_discovery consult the defining module during import.
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class OfflineBoundaryTests(unittest.TestCase):
    def test_hard_link_is_rejected_and_regular_file_still_reads(self):
        reader = load_tool('offline_files')
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            source = root / 'source.txt'
            source.write_bytes(b'synthetic public source')
            self.assertEqual(reader.read_regular(source, 100), b'synthetic public source')
            linked = root / 'linked.txt'
            try:
                os.link(source, linked)
            except OSError as exc:
                self.skipTest(f'hard links unavailable: {exc}')
            with self.assertRaises(ValueError):
                reader.read_regular(linked, 100)

    def test_unverifiable_rate_state_fails_before_filesystem_or_network(self):
        discovery = load_tool('public_discovery')
        with patch.object(discovery.os, 'getuid', None, create=True), patch.object(discovery.Path, 'mkdir') as mkdir:
            with self.assertRaisesRegex(discovery.SourceAccessError, 'ownership cannot be verified'):
                discovery._private_rate_state_directory()
            mkdir.assert_not_called()


if __name__ == '__main__':
    unittest.main()
