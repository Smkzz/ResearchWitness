"""Capture local-only final image evidence; never fetch packages or images."""
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
WORK = Path.home()
A = WORK / 'rw03-pdf-repro-a'
B = WORK / 'rw03-pdf-repro-b'


def run(*command, env=None):
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode('utf-8', errors='replace').replace('\r\n', '\n')
    with (OUT / 'final-image.log').open('a', encoding='utf-8', newline='\n') as stream:
        stream.write('$ ' + subprocess.list2cmdline(command) + '\n' + output
                     + f'\nEXIT CODE: {result.returncode}\n')
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    with (OUT / 'final-image.log').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(f'UTC: {datetime.now(timezone.utc).isoformat()}\nOS: {platform.platform()}\n')
    run('git', 'rev-parse', 'HEAD')
    run(sys.executable, '-VV')
    run('docker', 'version')
    image_a = (A / 'image-id.txt').read_text().strip()
    image_b = (B / 'image-id.txt').read_text().strip()
    inspections = json.loads(run('docker', 'image', 'inspect', image_a, image_b))
    for image in inspections:
        config = image['Config']
        if config.get('Env') or config.get('Entrypoint') or config.get('Volumes'):
            raise ValueError('Imported image has forbidden configuration')
    (OUT / 'image-inspect.json').write_text(json.dumps(inspections, indent=2) + '\n',
                                           encoding='utf-8', newline='\n')
    run('docker', 'image', 'inspect',
        'debian@sha256:7378260c0a098d27ac206225db5e7d92b8c7c84ea7afccc86eeb513756bbd392')
    history = run('docker', 'history', '--no-trunc', image_a)
    (OUT / 'image-history.txt').write_bytes(history.replace(b'\r\n', b'\n'))
    archive = WORK / 'rw03-pdf-final-image.tar'
    run('docker', 'save', '--output', str(archive), image_a)
    summary = {'image_id': image_a, 'second_image_id': image_b, 'image_ids_equal': image_a == image_b,
               'created': [image['Created'] for image in inspections],
               'rootfs_tar_sha256': [digest(work / 'rootfs.tar') for work in (A, B)],
               'inventories_equal': (OUT / 'rw03-pdf-repro-a-inventory.json').read_bytes()
               == (OUT / 'rw03-pdf-repro-b-inventory.json').read_bytes(),
               'layers': [image['RootFS']['Layers'] for image in inspections],
               'save_archive_sha256': digest(archive)}
    (OUT / 'image-summary.json').write_text(json.dumps(summary, indent=2) + '\n',
                                           encoding='utf-8', newline='\n')
    env = dict(os.environ, RESEARCHWITNESS_PDF_SANDBOX_IMAGE=image_a)
    run(sys.executable, '-m', 'tools.pdf_sandbox_smoke', '--output',
        str(OUT / 'pdf-final-smoke.json'), env=env)
    smoke = OUT / 'pdf-final-smoke.json'
    smoke.write_text(smoke.read_text(), encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))
    print((OUT / 'pdf-final-smoke.json').read_text())


if __name__ == '__main__':
    main()
