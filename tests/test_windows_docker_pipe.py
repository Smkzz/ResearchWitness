"""Windows Docker pipe identity checks without images or network access."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from tools import pdf_percentage_audit as audit


class WindowsDockerPipeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.docker = self.root / "Docker"
        self.docker.mkdir()
        self.image = self.docker / "backend.exe"
        self.image.touch()
        self.security = object.__new__(audit._WindowsDockerPipeSecurity)
        self.security.kernel = Mock()
        self.security.advapi = Mock()
        self.security.user_sid = Mock(return_value="S-1-5-21-123")
        self.security.sid_string = Mock(return_value="S-1-5-21-123")
        self.security.kernel.CreateFileW.return_value = 10
        self.security.kernel.OpenProcess.return_value = 20
        self.security.kernel.CloseHandle.return_value = 1

        def pid(_pipe, output):
            output._obj.value = 42
            return 1

        def token(_process, _access, output):
            output._obj.value = 30
            return 1

        def information(_token, _kind, buffer, _size, size):
            size._obj.value = ctypes.sizeof(ctypes.c_void_p)
            if buffer is None:
                return 0
            ctypes.c_void_p.from_buffer(buffer).value = 1
            return 1

        def image(_process, _flags, output, _size):
            output.value = str(self.image)
            return 1

        self.security.kernel.GetNamedPipeServerProcessId.side_effect = pid
        self.security.kernel.QueryFullProcessImageNameW.side_effect = image
        self.security.advapi.OpenProcessToken.side_effect = token
        self.security.advapi.GetTokenInformation.side_effect = information
        self.enterContext(patch.object(audit, "ctypes", ctypes, create=True))
        self.enterContext(patch.object(audit, "wintypes", wintypes, create=True))
        self.enterContext(patch.object(ctypes, "get_last_error", return_value=122, create=True))
        self.enterContext(patch.object(ctypes, "WinError", return_value=OSError("pipe unavailable"), create=True))
        self.enterContext(patch.object(audit, "_WindowsDockerPipeSecurity", return_value=self.security))
        self.enterContext(patch.dict(os.environ, {"ProgramFiles": str(self.root)}))

    def test_custom_pipe_name_is_used(self):
        audit._verify_windows_docker_pipe(r"\\.\pipe\custom-identity-test")
        self.assertEqual(self.security.kernel.CreateFileW.call_args.args[0], r"\\.\pipe\custom-identity-test")

    def test_current_user_and_system_servers_accepted(self):
        for sid in ("S-1-5-21-123", "S-1-5-18"):
            with self.subTest(sid=sid):
                self.security.sid_string.return_value = sid
                self.security.kernel.CloseHandle.reset_mock()
                audit._verify_windows_docker_pipe()
                handles = [args[0].value if isinstance(args[0], ctypes.c_void_p) else args[0]
                           for args, _kwargs in self.security.kernel.CloseHandle.call_args_list]
                self.assertEqual(handles, [30, 20, 10])

    def test_wrong_user_rejected(self):
        self.security.sid_string.return_value = "S-1-5-21-456"
        with self.assertRaisesRegex(audit.PDFSourceError, "server is unavailable or unverified"):
            audit._verify_windows_docker_pipe()

    def test_missing_program_files_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(audit.PDFSourceError, "server is unavailable or unverified"):
                audit._verify_windows_docker_pipe()

    def test_cleanup_does_not_mask_api_error(self):
        original = OSError("image query failed")
        self.security.kernel.QueryFullProcessImageNameW.side_effect = original
        self.security.kernel.CloseHandle.side_effect = lambda handle: int(isinstance(handle, ctypes.c_void_p))
        with self.assertRaises(audit.PDFSourceError) as caught:
            audit._verify_windows_docker_pipe()
        self.assertIs(caught.exception.__cause__, original)

    def test_outside_or_missing_image_rejected(self):
        for image in (self.root / "Docker-other" / "backend.exe", self.docker / "missing.exe"):
            with self.subTest(image=image):
                if image.parent != self.docker:
                    image.parent.mkdir(exist_ok=True)
                    image.touch()
                self.image = image
                with self.assertRaisesRegex(audit.PDFSourceError, "server is unavailable or unverified"):
                    audit._verify_windows_docker_pipe()

    def test_api_failures_and_absent_pipe_fail_closed(self):
        for api in (
            self.security.kernel.CreateFileW,
            self.security.kernel.GetNamedPipeServerProcessId,
            self.security.kernel.OpenProcess,
            self.security.advapi.OpenProcessToken,
            self.security.advapi.GetTokenInformation,
            self.security.kernel.QueryFullProcessImageNameW,
            self.security.kernel.CloseHandle,
        ):
            with self.subTest(api=api):
                with patch.object(api, "side_effect", None), patch.object(
                    api, "return_value", wintypes.HANDLE(-1).value if api is self.security.kernel.CreateFileW else 0,
                ):
                    with self.assertRaisesRegex(audit.PDFSourceError, "server is unavailable or unverified"):
                        audit._verify_windows_docker_pipe()

    def test_failure_prevents_any_docker_invocation(self):
        self.security.kernel.OpenProcess.return_value = 0
        with (
            patch.object(audit.sys, "platform", "win32"),
            patch.dict(os.environ, {audit.SANDBOX_IMAGE_ENV: "sha256:" + "a" * 64}),
            patch.object(audit.shutil, "which", return_value="docker.exe"),
            patch.object(audit.subprocess, "run") as run,
            patch.object(audit.subprocess, "Popen") as popen,
        ):
            with self.assertRaisesRegex(audit.PDFSourceError, "server is unavailable or unverified"):
                audit._extract_layout_text(b"%PDF-1.7\n")
        run.assert_not_called()
        popen.assert_not_called()


@unittest.skipUnless(sys.platform == "win32", "native Windows Docker pipe")
class NativeWindowsDockerPipeTests(unittest.TestCase):
    def test_python_pipe_server_rejected(self):
        security = audit._WindowsDockerPipeSecurity()
        create = security.kernel.CreateNamedPipeW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                           wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        create.restype = wintypes.HANDLE
        name = rf"\\.\pipe\rw03-identity-{uuid4().hex}"
        pipe = create(name, 3 | 0x00080000, 0, 1, 4096, 4096, 1000, None)
        security.require(pipe not in (None, wintypes.HANDLE(-1).value))
        try:
            result = subprocess.run(
                [sys.executable, "-c", """
from pathlib import Path
import sys
from unittest.mock import patch
from tools import pdf_percentage_audit as audit

security = audit._WindowsDockerPipeSecurity()
identity = security.server_identity
observed = []
def identify(name):
    value = identity(name)
    observed.append(value)
    return value
security.server_identity = identify
with patch.object(audit, '_WindowsDockerPipeSecurity', return_value=security):
    try:
        audit._verify_windows_docker_pipe(sys.argv[1])
    except audit.PDFSourceError as exc:
        assert len(observed) == 1, 'server identity was not read'
        sid, image = observed[0]
        assert sid == security.user_sid(), 'unexpected server owner'
        assert Path(image).samefile(sys.executable), 'server is not this Python process'
        print('Native Python pipe server SID:', sid)
        print('Native Python pipe server image:', image)
        print('Expected rejection:', exc)
    else:
        raise AssertionError('Python pipe server was accepted')
""", name],
                capture_output=True, text=True, timeout=15, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout, end="")
        finally:
            security.require(security.kernel.CloseHandle(pipe))

    @unittest.skipUnless(os.environ.get("RW_NATIVE_DOCKER_DESKTOP") == "1", "set RW_NATIVE_DOCKER_DESKTOP=1 for Docker Desktop acceptance")
    def test_real_daemon_identity(self):
        try:
            audit._verify_windows_docker_pipe()
        except audit.PDFSourceError as exc:
            if isinstance(exc.__cause__, OSError) and getattr(exc.__cause__, "winerror", None) in (2, 3):
                self.skipTest("Docker Desktop pipe is absent")
            raise

    @unittest.skipIf(os.environ.get("RW_NATIVE_DOCKER_DESKTOP") == "1", "Docker Desktop acceptance is opted in")
    def test_available_server_returns_or_fails_closed(self):
        try:
            audit._verify_windows_docker_pipe()
        except audit.PDFSourceError as exc:
            if isinstance(exc.__cause__, OSError) and getattr(exc.__cause__, "winerror", None) in (2, 3):
                self.skipTest("Docker pipe is absent")
