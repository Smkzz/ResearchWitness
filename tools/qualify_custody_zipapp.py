"""Rebuild and exercise the custody zipapp from two clean synthetic copies.

This tool reads only the checked-in worker source and synthetic fixtures. It
does not access a custody store, research source, network, or external service.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
VERSION = "0.5.0.dev0"
ARCHIVE = f"rw-custody-{VERSION}.pyz"
IGNORED = shutil.ignore_patterns("__pycache__", "dist", "*.pyc")


def checked_run(args: list[str], *, cwd: Path, env: dict[str, str],
                expected: int = 0) -> dict:
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                            text=True, timeout=20, check=False)
    if result.returncode != expected:
        raise RuntimeError(f"qualified command returned {result.returncode}: {args[-1]}")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("qualified command did not return JSON") from exc
    return payload


def make_clean_copy(destination: Path) -> None:
    destination.mkdir(parents=True)
    shutil.copyfile(PROJECT / "LICENSE", destination / "LICENSE")
    shutil.copytree(PROJECT / "custody_worker", destination / "custody_worker",
                    ignore=IGNORED)


def build_copy(destination: Path) -> tuple[Path, str]:
    make_clean_copy(destination)
    result = subprocess.run(
        [sys.executable, str(destination / "custody_worker" / "build_release.py")],
        cwd=destination, capture_output=True, text=True, timeout=20, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("offline zipapp build failed")
    archive = destination / "custody_worker" / "dist" / ARCHIVE
    sidecar = Path(str(archive) + ".sha256")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if sidecar.read_text(encoding="ascii").split()[0] != digest:
        raise RuntimeError("zipapp checksum sidecar did not match")
    return archive, digest


def inspect_archive(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("zipapp CRC verification failed")
        members = set(archive.namelist())
        if "__main__.py" not in members or "RELEASE_MANIFEST.json" not in members:
            raise RuntimeError("zipapp entrypoint or release manifest missing")
        if any(name.startswith(("tests/", "examples/", "papers/", "dist/"))
               or "__pycache__" in name for name in members):
            raise RuntimeError("zipapp contains excluded development material")
        manifest = json.loads(archive.read("RELEASE_MANIFEST.json"))
        for name, digest in manifest["files"].items():
            if name not in members or hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise RuntimeError("zipapp manifest does not match archive contents")
        if set(manifest["files"]) | {"__main__.py", "RELEASE_MANIFEST.json"} != members:
            raise RuntimeError("zipapp contains an unmanifested member")


def exercise_synthetic_cli(archive: Path, workspace: Path) -> None:
    runtime_home = workspace / "runtime"
    runtime_home.mkdir()
    dev_parent = runtime_home / "rw-custody-synthetic-only"
    store = dev_parent / "zipapp-smoke"
    store.mkdir(parents=True)
    (store / ".synthetic-only").write_bytes(
        b"RESEARCHWITNESS_SYNTHETIC_ONLY_V1\n",
    )
    incoming = store / "incoming"
    incoming.mkdir()
    fixture_dir = PROJECT / "custody_worker" / "examples"
    for name in (
        "synthetic-batch.json", "synthetic-review.json",
        "synthetic-original.txt", "synthetic-correction.txt",
    ):
        shutil.copyfile(fixture_dir / name, incoming / name)
    shutil.copyfile(incoming / "synthetic-batch.json",
                    incoming / "synthetic-batch-1.json")

    env = os.environ.copy()
    env["TMPDIR"] = str(runtime_home)

    def cli(*args: str, expected: int = 0) -> dict:
        return checked_run(
            [sys.executable, "-I", "-S", str(archive), "--dev-root", str(store), *args],
            cwd=workspace, env=env, expected=expected,
        )

    if cli("doctor").get("host_egress") != "MUST_BE_VERIFIED_EXTERNALLY":
        raise RuntimeError("doctor overstated host egress controls")
    if cli("init").get("status") != "INITIALIZED":
        raise RuntimeError("zipapp store initialization failed")
    if cli("import", "--batch-id", "synthetic-batch-1").get("status") != "IMPORTED":
        raise RuntimeError("synthetic source import failed")
    if cli("record-review", "--review-id", "synthetic-review").get("status") != "RECORDED":
        raise RuntimeError("synthetic source-bound review failed")
    counts = cli("verify")
    if counts.get("eligible_positive_issues") != 1 or counts.get("eligible_negative_relations") != 0:
        raise RuntimeError("zipapp synthetic review counts differed")
    if cli("seal").get("status") != "SEALED":
        raise RuntimeError("synthetic inventory seal failed")
    summary = cli("summary")
    if summary.get("eligible_positive_issues") != 1 or summary.get("eligible_negative_relations") != 0:
        raise RuntimeError("synthetic summary differed")
    exported = cli("export-summary", expected=2)
    if exported.get("code") != "PUBLIC_EXPORT_THRESHOLDS_NOT_MET":
        raise RuntimeError("below-threshold synthetic aggregate was not withheld")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rw-zipapp-qualification-") as temporary:
        root = Path(temporary)
        first, first_digest = build_copy(root / "clean-copy-a")
        second, second_digest = build_copy(root / "clean-copy-b")
        if first_digest != second_digest or first.read_bytes() != second.read_bytes():
            raise RuntimeError("independent clean builds were not byte-identical")
        inspect_archive(first)
        exercise_synthetic_cli(first, root)
        print(f"Version: {VERSION}")
        print(f"SHA-256: {first_digest}")
        print("Two clean builds: byte-identical")
        print("Allowlist/manifest inspection: PASS")
        print("Isolated synthetic CLI workflow: PASS")
        print("Below-threshold public export: refused")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
