import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.pdf_sandbox_image import build


class PDFSandboxImageTests(unittest.TestCase):
    def lock(self):
        return {
            'builder': build.BUILDER, 'snapshot': build.SNAPSHOT, 'suite': 'trixie',
            'architecture': 'amd64',
            'source': f'http://snapshot.debian.org/archive/debian/{build.SNAPSHOT}/',
            'inrelease_sha256': 'a' * 64, 'signing_fingerprints': ['A' * 40],
            'packages': [{'name': 'poppler-utils', 'version': '1:25.03.0-5+deb13u4',
                          'arch': 'amd64', 'filename': 'pool/main/p/poppler/poppler-utils.deb',
                          'sha256': 'b' * 64}],
        }

    def test_valid_lock(self):
        build.validate_lock(self.lock())

    def test_empty_packages_and_missing_signatures_fail(self):
        for key in ('packages', 'signing_fingerprints'):
            lock = self.lock()
            lock[key] = []
            with self.subTest(key=key), self.assertRaises(ValueError):
                build.validate_lock(lock)

    def test_wrong_pins_and_missing_hash_fail(self):
        for key in ('builder', 'snapshot', 'suite', 'architecture', 'source', 'inrelease_sha256'):
            lock = self.lock()
            lock[key] = 'invalid'
            with self.subTest(key=key), self.assertRaises(ValueError):
                build.validate_lock(lock)

    def test_unsafe_package_metadata_fails(self):
        for key, value in [('name', '-x'), ('version', '1\nother'), ('arch', 'arm64'),
                           ('filename', 'pool/main/../bad.deb'), ('sha256', 'not-a-hash')]:
            lock = self.lock()
            lock['packages'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build.validate_lock(lock)
        lock = self.lock()
        lock['packages'].append(copy.deepcopy(lock['packages'][0]))
        with self.assertRaises(ValueError):
            build.validate_lock(lock)

    def test_import_is_local_without_config_changes(self):
        image_id = 'sha256:' + 'c' * 64
        for arch in ('amd64', 'x86_64'):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                results = [subprocess.CompletedProcess([], 0, json.dumps({'Os': 'linux', 'Arch': arch}).encode()),
                           subprocess.CompletedProcess([], 0, (image_id + '\n').encode()),
                           subprocess.CompletedProcess([], 0, b'[{"Architecture":"amd64","Os":"linux"}]')]
                with patch.object(build.subprocess, 'run', side_effect=results) as run:
                    build.image(work, work)
                self.assertEqual(run.call_args_list[0].args[0],
                                 ['docker', 'version', '--format', '{{json .Server}}'])
                self.assertEqual(run.call_args_list[1].args[0],
                                 ['docker', 'import', str(work / 'rootfs.tar')])
                self.assertEqual(run.call_args_list[2].args[0], ['docker', 'image', 'inspect', image_id])
                self.assertEqual((work / 'image-id.txt').read_text().strip(), image_id)
                self.assertIn('EXIT CODE: 0', (work / f'{work.name}-import.log').read_text())

    def test_incompatible_or_missing_daemon_platform_stops_before_import(self):
        for platform in ({'Os': 'linux', 'Arch': 'arm64'}, {'Os': 'windows', 'Arch': 'amd64'}, {}):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                result = subprocess.CompletedProcess([], 0, json.dumps(platform).encode())
                with patch.object(build.subprocess, 'run', return_value=result) as run, \
                     self.assertRaisesRegex(ValueError, 'linux amd64/x86_64 Docker daemon'):
                    build.image(work, work)
                run.assert_called_once()
                self.assertFalse((work / 'image-id.txt').exists())

    def test_imported_platform_must_be_linux_amd64_before_writing_pin(self):
        for metadata in ([{'Architecture': 'arm64', 'Os': 'linux'}],
                         [{'Architecture': 'amd64', 'Os': 'windows'}], [{}], []):
            with self.subTest(metadata=metadata), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                results = [subprocess.CompletedProcess([], 0, b'{"Os":"linux","Arch":"amd64"}'),
                           subprocess.CompletedProcess([], 0, ('sha256:' + 'c' * 64).encode()),
                           subprocess.CompletedProcess([], 0, json.dumps(metadata).encode())]
                with patch.object(build.subprocess, 'run', side_effect=results), \
                     self.assertRaisesRegex(ValueError, 'Architecture amd64 and Os linux'):
                    build.image(work, work)
                self.assertFalse((work / 'image-id.txt').exists())

    def test_platform_command_errors_fail_closed(self):
        for stage in ('version', 'inspect'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                results = []
                if stage == 'inspect':
                    results.extend([subprocess.CompletedProcess([], 0, b'{"Os":"linux","Arch":"amd64"}'),
                                    subprocess.CompletedProcess([], 0, ('sha256:' + 'c' * 64).encode())])
                results.append(subprocess.CompletedProcess([], 1, b'daemon failed'))
                with patch.object(build.subprocess, 'run', side_effect=results), self.assertRaises(SystemExit):
                    build.image(work, work)
                self.assertFalse((work / 'image-id.txt').exists())

    def test_import_failure_or_invalid_id_never_writes_pin(self):
        for code, output, error in [(1, b'failed', SystemExit), (0, b'', ValueError)]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                result = subprocess.CompletedProcess([], code, output)
                server = subprocess.CompletedProcess([], 0, b'{"Os":"linux","Arch":"amd64"}')
                with patch.object(build.subprocess, 'run', side_effect=[server, result]), self.assertRaises(error):
                    build.image(work, work)
                self.assertFalse((work / 'image-id.txt').exists())

    def test_invalid_lock_stops_before_builder_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            lock = self.lock()
            lock['packages'] = []
            (work / 'packages.lock.json').write_text(json.dumps(lock))
            with patch.object(build, 'run_script') as run, self.assertRaises(ValueError):
                build.build(work, work)
            run.assert_not_called()

    def test_builder_error_is_logged_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            result = subprocess.CompletedProcess([], 100, b'signature failed\r\n')
            with patch.object(build.subprocess, 'run', return_value=result), self.assertRaises(SystemExit):
                build.run_script('prepare.sh', work, work / 'run.log')
            self.assertIn('signature failed\n\nEXIT CODE: 100\n', (work / 'run.log').read_text())


if __name__ == '__main__':
    unittest.main()
