"""Capture local focused regressions; no package installation or network actions."""
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).with_name('qualification-tests.log')


def main():
    with OUTPUT.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(f'UTC: {datetime.now(timezone.utc).isoformat()}\nOS: {platform.platform()}\n')
        invocations = [(['git', 'rev-parse', 'HEAD'], None),
                       ([sys.executable, '-VV'], None),
                       ([sys.executable, '-m', 'ruff', 'check', '.'], None),
                       ([sys.executable, '-m', 'pytest', '-q',
                         'tests/test_pdf_percentage_audit_unittest.py',
                         'tests/test_windows_docker_pipe.py', 'tests/test_pdf_sandbox_image.py',
                         'tests/test_pdf_sandbox_qualify.py', 'tests/test_documentation_unittest.py',
                         'tests/test_agent_plan_unittest.py'], '1'),
                       ([sys.executable, '-m', 'pytest', '-q', 'tests/test_windows_docker_pipe.py'], '')]
        for command, opt_in in invocations:
            env = dict(os.environ)
            if opt_in is not None:
                env.pop('RW_NATIVE_DOCKER_DESKTOP', None)
                if opt_in:
                    env['RW_NATIVE_DOCKER_DESKTOP'] = opt_in
                stream.write(f'RW_NATIVE_DOCKER_DESKTOP={opt_in or "UNSET"}\n')
            stream.write('$ ' + subprocess.list2cmdline(command) + '\n')
            stream.flush()
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, check=False)
            output = (result.stdout + result.stderr).decode('utf-8', errors='replace').replace('\r\n', '\n')
            stream.write(output + f'\nEXIT CODE: {result.returncode}\n')
            stream.flush()
            print(output)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
