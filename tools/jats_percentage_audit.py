"""Compatibility shim: legacy JATS module imports one installed implementation."""
from __future__ import annotations
import sys
from researchwitness import _jats_parser as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
sys.modules[__name__] = _implementation
