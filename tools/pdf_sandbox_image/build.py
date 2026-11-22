"""Resolve and assemble the PDF runtime; import its tar without builder-added PATH."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

BUILDER = 'debian@sha256:7378260c0a098d27ac206225db5e7d92b8c7c84ea7afccc86eeb513756bbd392'
SNAPSHOT = '20261120T000000Z'
ROOTFS_SHA256 = '01e8b685061d4cec687b4f451c4e3a2e8299fbcf3e9b8ddd83cd8e6c5f1e9074'
SIGNING_FINGERPRINTS = frozenset({
    '04B54C3CDCA79751B16BC6B5225629DF75B188BD',
    '41587F7DB8C774BCCF131416762F67A0B2C39DE4',
    'B8B80B5B623EAB6AD8775C45B7C5D7D6350947F8',
})


def validate_lock(lock: dict) -> None:
    if (lock.get('builder') != BUILDER or lock.get('snapshot') != SNAPSHOT
            or lock.get('suite') != 'trixie' or lock.get('architecture') != 'amd64'
            or lock.get('source') != f'http://snapshot.debian.org/archive/debian/{SNAPSHOT}/'):
        raise ValueError('Lock does not match recipe')
    if not re.fullmatch(r'[0-9a-f]{64}', lock.get('inrelease_sha256', '')):
        raise ValueError('Missing InRelease hash')
    if not lock.get('signing_fingerprints') or any(not re.fullmatch(r'[0-9A-F]{40}', signer)
                                                 for signer in lock['signing_fingerprints']):
        raise ValueError('Missing signature fingerprints')
    if (set(lock['signing_fingerprints']) != SIGNING_FINGERPRINTS
            or len(lock['signing_fingerprints']) != len(SIGNING_FINGERPRINTS)):
        raise ValueError('Signature fingerprints do not match the pinned signer set')
    if not lock.get('packages'):
        raise ValueError('Empty package closure')
    names = set()
    for package in lock['packages']:
        if (package['name'] in names or package['arch'] not in ('amd64', 'all')
                or not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*', package['name'])
                or not re.fullmatch(r'[0-9a-f]{64}', package['sha256'])
                or not package['filename'].startswith('pool/main/')
                or '..' in package['filename'].split('/')
                or any(not package[key] or any(c.isspace() for c in package[key])
                       for key in ('name', 'version', 'arch', 'filename', 'sha256'))):
            raise ValueError('Invalid package lock entry')
        names.add(package['name'])


def run_script(script: str, work: Path, log: Path) -> str:
    command = ['docker', 'run', '--rm', '--interactive', '--pull=never',
               '--platform', 'linux/amd64', '--mount', f'type=bind,source={work},target=/work',
               BUILDER, 'sh', '-s']
    result = subprocess.run(command, input=Path(__file__).with_name(script).read_bytes(),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    output = result.stdout.decode('utf-8', errors='replace').replace('\r\n', '\n')
    log.write_text('$ ' + subprocess.list2cmdline(command) + f' < {script}\n' + output
                   + f'\nEXIT CODE: {result.returncode}\n', encoding='utf-8', newline='\n')
    print(output)
    if result.returncode:
        raise SystemExit(result.returncode)
    return output


def verify_inrelease(directory: Path, lock: dict) -> None:
    validate_lock(lock)
    if hashlib.sha256((directory / 'InRelease').read_bytes()).hexdigest() != lock['inrelease_sha256']:
        raise ValueError('InRelease hash does not match the lock')
    command = ['docker', 'run', '--rm', '--network', 'none', '--pull=never',
               '--mount', f'type=bind,source={directory},target=/evidence,readonly',
               BUILDER, 'sqv', '--keyring', '/usr/share/keyrings/debian-archive-keyring.gpg',
               '--cleartext', '--output', '/tmp/authenticated-release', '--signatures',
               str(len(SIGNING_FINGERPRINTS)), '/evidence/InRelease']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    verified = result.stdout.decode('ascii').splitlines()
    if set(verified) != set(lock['signing_fingerprints']):
        raise ValueError('Verified InRelease signers do not match the locked fingerprint set')


def resolve(work: Path, evidence: Path) -> None:
    output = run_script('prepare.sh', work, evidence / 'resolve.log')
    packages = []
    for spec in (work / 'versions.txt').read_text().splitlines():
        name, version = spec.split('=', 1)
        paragraphs = (work / 'metadata' / f'{name}.txt').read_text().strip().split('\n\n')
        matches = []
        for paragraph in paragraphs:
            fields = dict(line.split(': ', 1) for line in paragraph.splitlines()
                          if ': ' in line and not line.startswith(' '))
            if fields.get('Version') == version:
                matches.append(fields)
        if len(matches) != 1:
            raise ValueError(f'Ambiguous package metadata: {spec}')
        fields = matches[0]
        packages.append({key: fields[source] for key, source in
                         [('name', 'Package'), ('version', 'Version'), ('arch', 'Architecture'),
                          ('filename', 'Filename'), ('sha256', 'SHA256')]})
    lock = {'schema_version': 1, 'builder': BUILDER, 'builder_tag': 'debian:trixie-slim',
            'suite': 'trixie', 'snapshot': SNAPSHOT, 'architecture': 'amd64',
            'source': f'http://snapshot.debian.org/archive/debian/{SNAPSHOT}/',
            'inrelease_sha256': hashlib.sha256((work / 'InRelease').read_bytes()).hexdigest(),
            'signing_fingerprints': sorted(set(re.findall(r'Got GOODSIG ([0-9A-F]{40})', output))),
            'packages': sorted(packages, key=lambda p: p['name'])}
    validate_lock(lock)
    verify_inrelease(work, lock)
    (evidence / 'packages.lock.json').write_text(json.dumps(lock, indent=2) + '\n',
                                                encoding='utf-8', newline='\n')
    shutil.copyfile(work / 'InRelease', evidence / 'InRelease')


def build(work: Path, evidence: Path) -> None:
    lock = json.loads((evidence / 'packages.lock.json').read_text())
    validate_lock(lock)
    verify_inrelease(evidence, lock)
    (work / 'inrelease.sha256').write_text(lock['inrelease_sha256'] + '  InRelease\n',
                                          encoding='ascii', newline='\n')
    (work / 'lock.tsv').write_text(''.join(' '.join(p[k] for k in
        ['name', 'version', 'arch', 'filename', 'sha256']) + '\n' for p in lock['packages']),
        encoding='utf-8', newline='\n')
    run_script('build_rootfs.sh', work, evidence / f'{work.name}.log')
    inventory = []
    with tarfile.open(work / 'rootfs.tar') as archive:
        for member in archive:
            stream = archive.extractfile(member) if member.isfile() else None
            inventory.append({'path': member.name, 'mode': oct(member.mode), 'size': member.size,
                              'sha256': hashlib.sha256(stream.read()).hexdigest() if stream else None,
                              'symlink_target': member.linkname if member.issym() else None})
    (evidence / f'{work.name}-inventory.json').write_text(
        json.dumps(sorted(inventory, key=lambda item: item['path']), indent=2) + '\n',
        encoding='utf-8', newline='\n')


def image(work: Path, evidence: Path) -> None:
    with (work / 'rootfs.tar').open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != ROOTFS_SHA256:
        raise ValueError('Rootfs tar SHA256 does not match the pinned recipe digest')
    server = subprocess.run(['docker', 'version', '--format', '{{json .Server}}'],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if server.returncode:
        raise SystemExit(server.returncode)
    platform = json.loads(server.stdout)
    if platform.get('Os') != 'linux' or platform.get('Arch') not in ('amd64', 'x86_64'):
        raise ValueError('Image import requires a linux amd64/x86_64 Docker daemon')
    command = ['docker', 'import', str(work / 'rootfs.tar')]
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    output = result.stdout.decode('utf-8', errors='replace').replace('\r\n', '\n')
    (evidence / f'{work.name}-import.log').write_text(
        '$ ' + subprocess.list2cmdline(command) + '\n' + output
        + f'\nEXIT CODE: {result.returncode}\n', encoding='utf-8', newline='\n')
    print(output)
    if result.returncode:
        raise SystemExit(result.returncode)
    image_id = output.strip()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('Import did not return a SHA256 image ID')
    inspected = subprocess.run(['docker', 'image', 'inspect', image_id], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False)
    if inspected.returncode:
        raise SystemExit(inspected.returncode)
    metadata = json.loads(inspected.stdout)
    if (len(metadata) != 1 or metadata[0].get('Architecture') != 'amd64'
            or metadata[0].get('Os') != 'linux'):
        raise ValueError('Imported image must have Architecture amd64 and Os linux')
    (work / 'image-id.txt').write_text(image_id + '\n', encoding='ascii', newline='\n')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['resolve', 'build', 'image'])
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    if args.operation != 'image':
        args.work_dir.mkdir(parents=True, exist_ok=False)
    args.evidence.mkdir(parents=True, exist_ok=True)
    {'resolve': resolve, 'build': build, 'image': image}[args.operation](
        args.work_dir.resolve(), args.evidence.resolve())


if __name__ == '__main__':
    main()
