import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import pdf_sandbox_qualify as qualify
from tools.pdf_percentage_audit import _extract_layout_text, _sandbox_arguments


class PDFSandboxQualificationTests(unittest.TestCase):
    image = 'sha256:' + 'a' * 64

    def container(self):
        args = _sandbox_arguments(self.image, Path('cid'))
        return {
            'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True, 'CapDrop': ['ALL'],
                           'SecurityOpt': ['no-new-privileges:true'], 'Memory': 536870912,
                           'MemorySwap': 536870912, 'NanoCpus': 1000000000, 'PidsLimit': 8,
                           'Ulimits': [{'Name': key, 'Soft': value, 'Hard': value} for key, value in
                                       [('cpu', 20), ('fsize', 2097152), ('nofile', 64), ('core', 0)]],
                           'Tmpfs': {'/tmp': 'rw,nosuid,nodev,noexec,size=32m,mode=1777'}, 'Binds': None},
            'Config': {'User': '65534:65534', 'Env': [args[i + 1] for i, value in enumerate(args)
                                                    if value == '--env']},
            'Image': self.image, 'Mounts': [], 'NetworkSettings': {'Networks': {'none': {}}},
            'State': {'Status': 'created', 'Running': False},
        }

    def checks(self, container, security=None):
        return qualify.configuration_checks(container, self.image,
            ['name=seccomp,profile=builtin'] if security is None else security,
            _sandbox_arguments(self.image, Path('cid')))

    def test_valid_effective_configuration_and_cpu_quota(self):
        container = self.container()
        self.assertTrue(all(self.checks(container).values()))
        container['HostConfig'].update(NanoCpus=0, CpuPeriod=100000, CpuQuota=100000)
        self.assertTrue(self.checks(container)['one_cpu'])

    def test_missing_or_insecure_configuration_fails_each_check(self):
        changes = [
            ('HostConfig', 'NetworkMode', 'bridge', 'network_none'),
            ('HostConfig', 'ReadonlyRootfs', False, 'readonly_root'),
            ('HostConfig', 'CapDrop', [], 'capabilities_dropped'),
            ('HostConfig', 'SecurityOpt', [], 'no_new_privileges'),
            ('HostConfig', 'Memory', 0, 'memory'),
            ('HostConfig', 'MemorySwap', -1, 'memory_swap'),
            ('HostConfig', 'NanoCpus', 0, 'one_cpu'),
            ('HostConfig', 'PidsLimit', 0, 'pids'),
            ('HostConfig', 'Ulimits', [], 'ulimits'),
            ('HostConfig', 'Tmpfs', {}, 'tmpfs'),
            ('HostConfig', 'Binds', ['/secret:/secret'], 'no_mounts_or_binds'),
            ('Config', 'User', '0', 'user'),
            ('Config', 'Env', ['SECRET=value'], 'environment'),
            ('State', 'Running', True, 'not_started'),
        ]
        for section, key, value, check in changes:
            container = self.container()
            container[section][key] = value
            with self.subTest(check=check):
                self.assertFalse(self.checks(container)[check])
        container = self.container()
        container['NetworkSettings']['Networks']['bridge'] = {}
        self.assertFalse(self.checks(container)['network_none'])
        container['Image'] = 'wrong'
        self.assertFalse(self.checks(container)['image_pin'])
        self.assertFalse(self.checks(self.container(), [])['default_seccomp'])

    def test_tmpfs_requires_size_and_all_security_options(self):
        for option in ('noexec', 'nosuid', 'nodev', 'size=32m'):
            container = copy.deepcopy(self.container())
            container['HostConfig']['Tmpfs']['/tmp'] = ','.join(
                part for part in container['HostConfig']['Tmpfs']['/tmp'].split(',') if part != option)
            with self.subTest(option=option):
                self.assertFalse(self.checks(container)['tmpfs'])

    def test_empty_inspection_cannot_pass(self):
        self.assertFalse(all(self.checks({}).values()))

    def test_resource_fixtures_are_deterministic_bounded_and_valid_xref(self):
        for overflow in (False, True):
            data = qualify.resource_pdf(overflow=overflow)
            with self.subTest(overflow=overflow):
                self.assertEqual(data, qualify.resource_pdf(overflow=overflow))
                self.assertLess(len(data), 8 * 1024 * 1024)
                xref = int(data.split(b'startxref\n')[1].splitlines()[0])
                self.assertEqual(data[xref:xref + 4], b'xref')

    def test_production_helper_and_timeout_cannot_widen_limits(self):
        args = _sandbox_arguments(self.image, Path('cid'))
        self.assertEqual(args[:4], ['--pull=never', '--interactive', '--cidfile', 'cid'])
        self.assertIn('--read-only', args)
        self.assertEqual(args[-7:], [self.image, '/usr/bin/pdftotext', '-layout', '-enc', 'UTF-8', '-', '-'])
        for timeout in (0, -1, 21, float('nan')):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                _extract_layout_text(b'%PDF-1.4', _timeout=timeout)

    def test_report_records_failure_and_never_claims_qualification(self):
        for failure in (None, RuntimeError('blocked')):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'result.json'
                with patch.dict(os.environ, {qualify.SANDBOX_IMAGE_ENV: self.image}), \
                     patch.object(qualify, 'collect', side_effect=failure):
                    self.assertEqual(qualify.main(['--output', str(output)]), 2 if failure else 0)
                report = json.loads(output.read_text())
                self.assertFalse(report['sandbox_qualified'])
                self.assertEqual(report['error'], str(failure) if failure else None)

    def test_failed_assertion_is_saved_before_stopping(self):
        evidence = qualify.Evidence(Path('unused.json'))
        evidence.check('normal', True)
        with self.assertRaisesRegex(RuntimeError, 'empty'):
            evidence.check('empty', False, containers=[])
        self.assertEqual([check['passed'] for check in evidence.checks], [True, False])


if __name__ == '__main__':
    unittest.main()
