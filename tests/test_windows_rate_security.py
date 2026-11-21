"""Native Windows rate-state security boundary checks; no network access."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import public_discovery as discovery


class WindowsRateCleanupTests(unittest.TestCase):
    def test_successful_cleanup(self):
        cleanup = Mock(return_value=True)
        with discovery._WindowsRateSecurity.checked_cleanup(cleanup):
            pass
        cleanup.assert_called_once_with()

    def test_cleanup_failure_after_success_fails_closed(self):
        cleanup = Mock(return_value=False)
        with self.assertRaises(OSError):
            with discovery._WindowsRateSecurity.checked_cleanup(cleanup):
                pass
        cleanup.assert_called_once_with()

    def test_cleanup_failure_preserves_original_exception(self):
        for result in (False, OSError("cleanup failed")):
            with self.subTest(result=result):
                cleanup = Mock(side_effect=result) if isinstance(result, OSError) else Mock(return_value=result)
                original = OSError("original failure")
                with self.assertRaises(OSError) as caught:
                    with discovery._WindowsRateSecurity.checked_cleanup(cleanup):
                        raise original
                self.assertIs(caught.exception, original)
                cleanup.assert_called_once_with()

    def test_cleanup_failure_with_unrelated_handled_exception_fails_closed(self):
        try:
            raise OSError("already handled")
        except OSError:
            with self.assertRaises(OSError):
                with discovery._WindowsRateSecurity.checked_cleanup(lambda: False):
                    pass


@unittest.skipUnless(sys.platform == "win32", "native Windows ACL checks")
class WindowsRateSecurityTests(unittest.TestCase):
    def test_empty_read_only_and_inherit_only_dacls_rejected(self):
        security = discovery._WindowsRateSecurity()
        sid = security.user_sid()
        convert = security.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        for acl in ("", f"(A;OICI;FR;;;{sid})", f"(A;OICIIO;FA;;;{sid})"):
            with self.subTest(acl=acl), tempfile.TemporaryDirectory() as root:
                def convert_acl(_sddl, *args):
                    return convert(f"O:{sid}D:P{acl}", *args)

                try:
                    with patch.object(security.advapi, "ConvertStringSecurityDescriptorToSecurityDescriptorW", side_effect=convert_acl):
                        with patch.object(discovery, "_WindowsRateSecurity", return_value=security):
                            with self.assertRaises(discovery.SourceAccessError):
                                discovery._private_rate_state_directory(Path(root))
                finally:
                    for directory in Path(root).iterdir():
                        subprocess.run(
                            ["icacls", str(directory), "/grant", f"*{sid}:(OI)(CI)F"],
                            check=True, capture_output=True,
                        )

    def test_private_creation_existing_acl_and_native_lock(self):
        with tempfile.TemporaryDirectory() as root:
            directory = discovery._private_rate_state_directory(Path(root))
            security = discovery._WindowsRateSecurity()
            security.verify(directory, security.user_sid())
            self.assertEqual(discovery._private_rate_state_directory(Path(root)), directory)
            with patch.object(discovery.tempfile, "gettempdir", return_value=root):
                path = discovery._shared_rate_state_path("www.ebi.ac.uk")
            self.assertEqual(path.parent, directory)
            self.assertIsNone(discovery.fcntl)
            discovery._reserve_shared_rate_slot(
                "www.ebi.ac.uk", 1, lambda _: None, state_path=path, wall_clock=lambda: 100,
            )
            self.assertTrue(path.is_file())

    def test_inherited_default_acl_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = discovery._private_rate_state_directory(Path(root))
            directory.rmdir()
            directory.mkdir()
            with self.assertRaises(discovery.SourceAccessError):
                discovery._private_rate_state_directory(Path(root))

    def test_extra_everyone_ace_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = discovery._private_rate_state_directory(Path(root))
            subprocess.run(["icacls", str(directory), "/grant", "*S-1-1-0:(OI)(CI)R"], check=True, capture_output=True)
            with self.assertRaises(discovery.SourceAccessError):
                discovery._private_rate_state_directory(Path(root))

    def test_junction_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory = discovery._private_rate_state_directory(Path(root))
            directory.rmdir()
            target = Path(root) / "target"
            target.mkdir()
            subprocess.run(["cmd", "/c", "mklink", "/J", str(directory), str(target)], check=True, capture_output=True)
            try:
                with self.assertRaises(discovery.SourceAccessError):
                    discovery._private_rate_state_directory(Path(root))
            finally:
                directory.rmdir()

    def test_native_api_errors_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            for method in ("user_sid", "create", "verify"):
                with self.subTest(method=method), patch.object(discovery._WindowsRateSecurity, method, side_effect=OSError):
                    with self.assertRaises(discovery.SourceAccessError):
                        discovery._private_rate_state_directory(Path(root))
