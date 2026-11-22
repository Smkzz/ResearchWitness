"""Recapture benign synthetic checks using only the existing local image."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
IMAGE = 'sha256:a526f5d88b02e0af23ae5105d4f14da0f8c664595462afc65cac73b94744c944'
OLD = '947ac3126ebd4867bfa91912dcd047c6a95ef580'
MAIN = '6a26ab5147c2443b7bff1e8cd5469d1409b43c96'


def main():
    with (OUT / 'capture.log').open('x', encoding='utf-8', newline='\n') as log:
        log.write(f'UTC: {datetime.now(timezone.utc).isoformat()}\nOS: {platform.platform()}\n')

        def run(command, *, required=True):
            result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            output = (result.stdout + result.stderr).decode('utf-8', errors='replace').replace('\r\n', '\n')
            log.write('$ ' + subprocess.list2cmdline(command) + '\n' + output
                      + f'\nEXIT CODE: {result.returncode}\n')
            log.flush()
            if required and result.returncode:
                raise RuntimeError(f'Capture stopped: {command!r}')
            return result

        run(['git', 'rev-parse', 'HEAD'])
        run([sys.executable, '-VV'])
        inspected = run(['docker', 'image', 'inspect', IMAGE])
        image = json.loads(inspected.stdout)[0]
        if image['Id'] != IMAGE or image['Architecture'] != 'amd64' or image['Os'] != 'linux':
            raise ValueError('Existing local image identity/platform mismatch')
        (OUT / 'image-inspect.json').write_bytes(inspected.stdout.replace(b'\r\n', b'\n'))
        probe = run([sys.executable, '-c',
            'import json,sys,pathlib; from tools import pdf_sandbox_qualify,pdf_sandbox_smoke; '
            'root=pathlib.Path.cwd(); print(json.dumps(sorted({pathlib.Path(m.__file__).resolve().relative_to(root).as_posix() '
            'for m in tuple(sys.modules.values()) if getattr(m,"__file__",None) '
            'and pathlib.Path(m.__file__).resolve().is_relative_to(root)})))'])
        paths = set(json.loads(probe.stdout))
        previous = ROOT / 'evidence/rw03-pdf-image-2026-11-22'
        for name in ('isolation-final.json', 'pdf-final-smoke.json', 'image-summary.json'):
            paths.add((previous / name).relative_to(ROOT).as_posix())
        old_report = json.loads((previous / 'isolation-final.json').read_text())
        for path in old_report['source_sha256']:
            paths.add('tools/' + Path(path).name)
        continuity = []
        for path in sorted(paths):
            hashes = {}
            for revision in (OLD, MAIN):
                result = run(['git', 'show', f'{revision}:{path}'], required=False)
                hashes[revision] = hashlib.sha256(result.stdout).hexdigest() if result.returncode == 0 else None
            continuity.append({'path': path, 'sha256': hashes,
                               'identical': hashes[OLD] is not None and hashes[OLD] == hashes[MAIN]})
        (OUT / 'dependency-continuity.json').write_text(json.dumps(continuity, indent=2) + '\n',
                                                        encoding='utf-8', newline='\n')
        os.environ['RESEARCHWITNESS_PDF_SANDBOX_IMAGE'] = IMAGE
        run([sys.executable, '-m', 'tools.pdf_sandbox_qualify', '--output', str(OUT / 'isolation.json')])
        run([sys.executable, '-m', 'tools.pdf_sandbox_smoke', '--output', str(OUT / 'smoke.json')])
        log.write('Capture exit code: 0\n')


if __name__ == '__main__':
    main()
