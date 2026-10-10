"""Build the committed local-first app wheel twice, inspect and smoke-install it.

The builds use an immutable local Git revision and pip's --no-index mode. No
package registry, external dependency, or network access is used.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
SOURCE_DATE_EPOCH = "1791418753"  # UTC commit time of qualified starting content.


def git_bytes(*args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(PROJECT), *args],
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError("local Git source snapshot failed")
    return result.stdout


def extract_clean_revision(archive_data: bytes, destination: Path) -> None:
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:") as archive:
        archive.extractall(destination, filter="data")


def build_wheel(source: Path, wheelhouse: Path) -> Path:
    wheelhouse.mkdir()
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    result = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps",
         "--no-build-isolation", "--wheel-dir", str(wheelhouse), str(source)],
        cwd=source, env=env, capture_output=True, text=True, timeout=90, check=False,
    )
    wheels = list(wheelhouse.glob("*.whl"))
    if result.returncode != 0 or len(wheels) != 1:
        raise RuntimeError("offline app wheel build failed")
    return wheels[0]


def install_smoke(wheel: Path, target: Path, workspace: Path) -> None:
    env = os.environ.copy()
    env["PIP_NO_INDEX"] = "1"
    installed = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-index", "--no-deps",
         "--target", str(target), str(wheel)],
        cwd=workspace, env=env, capture_output=True, text=True, timeout=60, check=False,
    )
    if installed.returncode != 0:
        raise RuntimeError("offline app wheel install failed")
    smoke = "\n".join((
        "import sys",
        "sys.path.insert(0, sys.argv[1])",
        "import researchwitness",
        "from importlib.resources import files",
        "assert files('researchwitness').joinpath('webui/index.html').is_file()",
        "assert files('researchwitness').joinpath('webui/app.js').is_file()",
        "from researchwitness.__main__ import main",
        "try:",
        "    main(['--version'])",
        "except SystemExit as exc:",
        "    if exc.code != 0: raise",
        "else:",
        "    raise AssertionError('version command did not exit')",
    ))
    result = subprocess.run([sys.executable, "-I", "-c", smoke, str(target)],
                            cwd=workspace, capture_output=True, text=True,
                            timeout=20, check=False)
    if result.returncode != 0 or "researchwitness " not in result.stdout:
        raise RuntimeError("clean wheel import/CLI/resource smoke test failed")


def retain_qualified_wheel(wheel: Path) -> Path:
    output_dir = PROJECT / "dist"
    if output_dir.exists() or output_dir.is_symlink():
        info = os.lstat(output_dir)
        if (os.path.islink(output_dir) or not output_dir.is_dir()
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise RuntimeError("unsafe local wheel output directory")
    else:
        output_dir.mkdir()
    output = output_dir / wheel.name
    if output.exists() or output.is_symlink():
        info = os.lstat(output)
        if (os.path.islink(output) or not output.is_file() or info.st_nlink != 1
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise RuntimeError("unsafe existing local wheel output")
    fd, name = tempfile.mkstemp(prefix=".rw-wheel-", suffix=".tmp", dir=output_dir)
    try:
        with os.fdopen(fd, "wb") as stream, wheel.open("rb") as source:
            shutil.copyfileobj(source, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, output)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    if hashlib.sha256(output.read_bytes()).digest() != hashlib.sha256(wheel.read_bytes()).digest():
        raise RuntimeError("retained wheel differs from qualified build")
    return output


def main() -> int:
    status = git_bytes("status", "--porcelain", "--untracked-files=no").decode("utf-8")
    if status:
        raise RuntimeError("tracked worktree must be committed before clean wheel qualification")
    revision = git_bytes("rev-parse", "HEAD").decode("ascii").strip()
    archive_data = git_bytes("archive", "--format=tar", "HEAD")
    with tempfile.TemporaryDirectory(prefix="rw-app-wheel-qualification-") as temporary:
        root = Path(temporary)
        source_a = root / "source-a"
        source_b = root / "source-b"
        extract_clean_revision(archive_data, source_a)
        extract_clean_revision(archive_data, source_b)
        wheel_a = build_wheel(source_a, root / "wheels-a")
        wheel_b = build_wheel(source_b, root / "wheels-b")
        bytes_a = wheel_a.read_bytes()
        bytes_b = wheel_b.read_bytes()
        digest = hashlib.sha256(bytes_a).hexdigest()
        if digest != hashlib.sha256(bytes_b).hexdigest() or bytes_a != bytes_b:
            raise RuntimeError("independent clean app wheels were not byte-identical")
        with zipfile.ZipFile(wheel_a) as package:
            members = set(package.namelist())
            if "researchwitness/webui/index.html" not in members or "researchwitness/webui/app.js" not in members:
                raise RuntimeError("wheel omitted the local interface assets")
            if any(name.startswith(("tests/", "custody_worker/", "validation/")) for name in members):
                raise RuntimeError("wheel contains excluded test, custody, or validation data")
            if package.testzip() is not None:
                raise RuntimeError("wheel CRC verification failed")
        install_smoke(wheel_a, root / "installed", root)
        retained = retain_qualified_wheel(wheel_a)
        print(f"Source revision: {revision}")
        print(f"SOURCE_DATE_EPOCH: {SOURCE_DATE_EPOCH}")
        print(f"Wheel: {wheel_a.name}")
        print(f"SHA-256: {digest}")
        print(f"Qualified artifact: {retained}")
        print("Two clean wheel builds: byte-identical")
        print("Wheel contents: PASS")
        print("Offline clean-target install and CLI/resource smoke test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
