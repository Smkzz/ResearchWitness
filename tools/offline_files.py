"""Bounded regular-file reads for offline development tools."""
from __future__ import annotations

import os
from pathlib import Path
import stat


def read_regular(path: Path, limit: int) -> bytes:
    """Reject special files without blocking, then bound the opened descriptor.

    This is input validation, not a filesystem sandbox. Manifest confinement and
    PDF process isolation are separate responsibilities.
    """
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    # The precheck also protects platforms without O_NONBLOCK/O_NOFOLLOW.
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"Input must be a regular file: {path.name}")
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f"Input must be a regular file: {path.name}")
        if info.st_size > limit:
            raise ValueError(f"Input exceeds its byte limit: {path.name}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"Input exceeds its byte limit: {path.name}")
        return data
    finally:
        os.close(descriptor)

