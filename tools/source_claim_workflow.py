"""Compatibility entry point for installed RW-MATH-02 source claim workflow."""
from researchwitness.source_claim_workflow import (
    MAX_CANDIDATE_BYTES,
    MAX_HINT_BYTES,
    MAX_POINT_BYTES,
    _read,
    _read_hints,
    compile_from_paths,
    main,
    refute_from_paths,
    verify_from_paths,
)

__all__ = ["MAX_CANDIDATE_BYTES", "MAX_HINT_BYTES", "MAX_POINT_BYTES",
           "_read", "_read_hints", "compile_from_paths", "verify_from_paths",
           "refute_from_paths", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
