"""Build a deterministic, offline, isolated Python zipapp from reviewed code only.

No protected custody store, papers, network, model provider, GitHub, or external
dependencies are accessed by this build script.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

VERSION = "0.5.0.dev0"
PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent
SOURCE_FILES = (
    "LICENSE",
    "custody_worker/__init__.py",
    "custody_worker/__main__.py",
    "custody_worker/cli.py",
    "custody_worker/policy.py",
    "custody_worker/store.py",
    "custody_worker/schemas/import-manifest.v2.schema.json",
    "custody_worker/schemas/review.v5.schema.json",
    "custody_worker/schemas/review-record.v4.schema.json",
    "custody_worker/schemas/summary.v3.schema.json",
    "custody_worker/schemas/public-summary.v2.schema.json",
    "custody_worker/schemas/public-export.v2.schema.json",
)
ARCHIVE_NAME = f"rw-custody-{VERSION}.pyz"
MAIN = (b"from custody_worker.cli import main\n"
        b"if __name__ == '__main__':\n"
        b"    raise SystemExit(main())\n")


def main() -> int:
    files: dict[str, bytes] = {}
    for rel in SOURCE_FILES:
        path = ROOT / rel
        current = ROOT
        parts = Path(rel).parts
        for index, part in enumerate(parts):
            current = current / part
            try:
                info = os.lstat(current)
            except OSError as exc:
                raise RuntimeError(f"Build input unavailable: {rel}") from exc
            is_reparse = bool(getattr(info, "st_file_attributes", 0) & 0x400)
            if os.path.islink(current) or is_reparse:
                raise RuntimeError(f"Build input path contains a link: {rel}")
            if index < len(parts) - 1 and not os.path.isdir(current):
                raise RuntimeError(f"Build input parent is not a directory: {rel}")
        if not os.path.isfile(path) or info.st_nlink != 1:
            raise RuntimeError(f"Build input not regular or is linked: {rel}")
        files[rel] = path.read_bytes()
        if len(files[rel]) > 2_000_000:
            raise RuntimeError(f"Build input too large: {rel}")
    record = {
        "archive_format": "rw-custody-release/1",
        "version": VERSION,
        "files": {rel: hashlib.sha256(data).hexdigest() for rel, data in sorted(files.items())},
        "build": "deterministic-zip-stored",
        "source_only": True,
    }
    files["__main__.py"] = MAIN
    files["RELEASE_MANIFEST.json"] = (
        json.dumps(record, ensure_ascii=True, sort_keys=True,
                   separators=(",", ":")) + "\n").encode("utf-8")
    out = PACKAGE_DIR / "dist"
    if out.exists() or out.is_symlink():
        info = os.lstat(out)
        is_reparse = bool(getattr(info, "st_file_attributes", 0) & 0x400)
        if os.path.islink(out) or is_reparse or not os.path.isdir(out):
            raise RuntimeError("Unsafe dist directory")
    out.mkdir(exist_ok=True)
    output = out / ARCHIVE_NAME
    checksum_path = out / (ARCHIVE_NAME + ".sha256")
    for path in (output, checksum_path):
        if path.exists() or path.is_symlink():
            info = os.lstat(path)
            if os.path.islink(path) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
                raise RuntimeError(f"Unsafe existing output link: {path.name}")
            if not os.path.isfile(path) or info.st_nlink != 1:
                raise RuntimeError(f"Unsafe existing output file: {path.name}")
    fd, name = tempfile.mkstemp(prefix=".rw-build-", suffix=".tmp", dir=out)
    os.close(fd)
    try:
        with zipfile.ZipFile(name, mode="w", compression=zipfile.ZIP_STORED,
                             allowZip64=False, strict_timestamps=True) as archive:
            for rel, data in sorted(files.items()):
                entry = zipfile.ZipInfo(rel, (2020, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_STORED
                entry.create_system = 3
                entry.external_attr = 0o100444 << 16
                archive.writestr(entry, data)
        os.replace(name, output)
    finally:
        if os.path.exists(name):
            os.unlink(name)

    data = output.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    fd, checksum_name = tempfile.mkstemp(prefix=".rw-checksum-", suffix=".tmp", dir=out)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as stream:
            stream.write(f"{digest}  {ARCHIVE_NAME}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(checksum_name, checksum_path)
    finally:
        if os.path.exists(checksum_name):
            os.unlink(checksum_name)
    print(f"Archive: {output}")
    print(f"SHA-256: {digest}")
    print("Source-only offline package. NOT production qualified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
