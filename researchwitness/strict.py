"""Small, bounded JSON and file-reading boundary. No code execution or fetching."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 24
MAX_NODES = 10000
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


class Invalid(ValueError):
    """Input is unsupported, malformed, unavailable or fails integrity checking."""


def require(condition: bool, message: str) -> None:
    # Do not use assert at a security/proof boundary: python -O removes asserts.
    if not condition:
        raise Invalid(message)


def fields(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    require(type(value) is dict, "Expected JSON object")
    optional = optional or set()
    require(not (set(value) - required - optional), "Unknown field(s): " + str(sorted(set(value) - required - optional)))
    require(not (required - set(value)), "Missing field(s): " + str(sorted(required - set(value))))
    return value


def text(value: Any, limit: int = 10000) -> str:
    require(type(value) is str and 0 < len(value) <= limit, "Expected nonempty bounded string")
    require(not any(ord(c) < 32 and c not in '\n\t' for c in value), "Control character in text")
    require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "Unpaired surrogate in text")
    return value


def integer(value: Any, low: int, high: int) -> int:
    require(type(value) is int and low <= value <= high, "Integer outside allowed bounds")
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def byte_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')


def _pairs(items: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def _no_float(_: str) -> Any:
    raise Invalid("JSON floats/nonfinite numbers are forbidden; use exact rational strings")


def _parse_int(value: str) -> int:
    require(len(value) <= 12, "JSON integer too large")
    return int(value)


def loads(data: bytes) -> Any:
    require(len(data) <= MAX_JSON_BYTES, "JSON size limit exceeded")
    try:
        obj = json.loads(data.decode('utf-8'), object_pairs_hook=_pairs,
                         parse_float=_no_float, parse_constant=_no_float, parse_int=_parse_int)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, Invalid):
            raise
        raise Invalid("Invalid JSON encoding or structure") from exc
    todo, count = [(obj, 0)], 0
    while todo:
        item, depth = todo.pop()
        count += 1
        require(depth <= MAX_DEPTH and count <= MAX_NODES, "JSON complexity limit exceeded")
        if isinstance(item, dict):
            for k, v in item.items():
                text(k, 256)
                todo.append((v, depth + 1))
        elif isinstance(item, list):
            todo.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            # Empty values are permitted at decoding, rejected by individual schemas.
            require(len(item) <= 20000, "JSON string too long")
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in item), "Unpaired surrogate")
    return obj


def relative_path(name: Any) -> str:
    text(name, 240)
    require('\\' not in name and ':' not in name, "Nonportable/Windows path rejected")
    require(all(ord(c) >= 32 for c in name), "Control character in path")
    parts = name.split('/')
    require(not name.startswith('/') and all(p not in ('', '.', '..') for p in parts), "Unsafe relative path")
    require(str(PurePosixPath(name)) == name, "Noncanonical path")
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{x}{i}' for x in ('COM', 'LPT') for i in range(1, 10)}
    require(all(not p.endswith((' ', '.')) and p.split('.')[0].upper() not in reserved for p in parts),
            'Nonportable reserved path')
    return name


class Bundle:
    """Read only declared regular files beneath a trusted, quiescent directory.

    This is not an OS sandbox. Concurrent hostile replacement of parent directories,
    mount points or hardlinks is outside the supported threat model.
    """

    def __init__(self, root: Path | str):
        raw = Path(root).absolute()
        require(not raw.is_symlink(), "Bundle root must not be a symlink")
        self.root = raw.resolve()
        require(self.root.is_dir(), "Bundle directory unavailable")

    def read(self, name: str, limit: int = MAX_ARTIFACT_BYTES) -> bytes:
        relative_path(name)
        target = self.root
        for component in name.split('/'):
            target = target / component
            require(not target.is_symlink(), "Symlink rejected: " + name)
        require(target.resolve().is_relative_to(self.root), "Path escapes bundle")
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        try:
            fd = os.open(target, flags)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode), "Not a regular file: " + name)
                require(info.st_nlink == 1, "Hard-linked artifact rejected: " + name)
                require(info.st_size <= limit, "Artifact size limit exceeded")
                data = stream.read(limit + 1)
                require(len(data) <= limit, "Artifact grew beyond size limit")
                require(len(data) == info.st_size, "Artifact changed while reading")
                return data
        except OSError as exc:
            raise Invalid("Cannot read artifact: " + name) from exc
