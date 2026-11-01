"""RW-04I: replay accepted *formal refutations* behind development receipts.

The legacy scorer deliberately trusts supplied status declarations. This
optional stricter adapter requires each declared accepted certificate to have
actual source, candidate, model, and exact refuting point bytes in a trusted,
quiescent local evidence directory. It re-derives the formalization and checks
the point with the installed exact verifier before reporting an audited score.

This does NOT authenticate publisher/source origin, label truth, actual reviewer
independence, publication errors, resource usage, or a sealed experiment.
Nothing runs on the source bytes. No network, model call, or external contact.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import stat
import sys
from typing import Any

from researchwitness import exact_optimization as exact
from researchwitness import source_claims as source
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-development-artifact-replay.v1"
MAX_ACCEPTED = 128
MAX_TOTAL_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024


def _digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _directory(path: Path) -> None:
    """Confine names below a caller-trusted, quiescent evidence directory."""
    mode = path.lstat().st_mode
    vb.require(stat.S_ISDIR(mode) and not path.is_symlink(), "EVIDENCE_DIR_NOT_PLAIN")


def _load(path: Path, maximum: int) -> bytes:
    # The same guarded regular-file reader used elsewhere in the repository.
    raw = read_regular(path, maximum)
    vb.require(type(raw) is bytes and len(raw) <= maximum, "ARTIFACT_SIZE")
    return raw


def replay(registry: dict[str, Any], protocol: dict[str, Any], run: dict[str, Any],
           evidence_root: Path, *, expected_registry_sha256: str,
           expected_protocol_sha256: str, expected_run_sha256: str) -> dict[str, Any]:
    """Return an audited development score or fail without an audited score.

    V1 assumes one explicit RW-MATH-BEGIN block and NO external compiler hints
    per accepted work. A work's interpretation SHA is the byte hash of that
    exact declared block, not an independent scientific interpretation label.
    The receipt's `certificate_sha256` binds a canonical JSON exact point;
    not a solver-reported upper certificate. Only a strict formal refutation
    receives this adapter's `mathematical_replay_verified` status.
    """
    exact._sha(expected_run_sha256)
    # Establish all schedule, source, family, receipt and zero-cost invariants
    # without changing the legacy denominator or supplied scientific labels.
    original = vb.score(
        registry, protocol, run,
        expected_registry_sha256=expected_registry_sha256,
        expected_protocol_sha256=expected_protocol_sha256,
    )
    vb.require(vb.commitment(run) == expected_run_sha256, "RUN_EXTERNAL_PIN_MISMATCH")
    works = vb._registry(registry)
    records = {r["work_id"]: r for r in run["results"]}
    # No alias of two identities into one Windows case-insensitive folder.
    vb.require(len({w.casefold() for w in works}) == len(works),
               "WORK_PATH_CASE_COLLISION")
    expected = [w for w in protocol["schedule"]
                if w in records and records[w]["certificate_status"] == "accepted"]
    vb.require(len(expected) <= MAX_ACCEPTED, "ACCEPTED_REPLAY_BUDGET")
    _directory(evidence_root)
    total_bytes = 0
    checked: list[dict[str, Any]] = []
    for work_id in expected:
        record = records[work_id]
        work = works[work_id]
        vb.require(record["status"] == "completed" and record["alarm_emitted"] is True,
                   "ACCEPTANCE_ON_NONCOMPLETED_OR_NONALARM")
        folder = evidence_root / work_id
        _directory(folder)
        paths = (
            ("source", source.MAX_SOURCE_BYTES, "source.txt"),
            ("candidate", 32 * 1024, "candidate.json"),
            ("model", exact.MAX_MODEL_BYTES, "model.json"),
            ("point", 64 * 1024, "point.json"),
        )
        artifacts = {}
        for name, maximum, filename in paths:
            raw = _load(folder / filename, maximum)
            total_bytes += len(raw)
            vb.require(total_bytes <= MAX_TOTAL_ARTIFACT_BYTES,
                       "CUMULATIVE_ARTIFACT_BUDGET")
            artifacts[name] = raw
        candidate_raw = artifacts["candidate"]
        model_raw = artifacts["model"]
        point_raw = artifacts["point"]
        # The registry and run are separately pinned by the caller. A self-
        # consistent bundle cannot replace the expected source/point/candidate.
        vb.require(_digest(artifacts["source"]) == work["source_sha256"],
                   "SOURCE_ARTIFACT_PIN_MISMATCH")
        vb.require(_digest(candidate_raw) == record["candidate_sha256"],
                   "CANDIDATE_ARTIFACT_PIN_MISMATCH")
        vb.require(_digest(point_raw) == record["certificate_sha256"],
                   "POINT_ARTIFACT_PIN_MISMATCH")
        model_sha = _digest(model_raw)
        candidate, model = source.recheck_candidate(
            artifacts["source"], block_index=0,
            expected_source_sha256=work["source_sha256"],
            candidate_bytes=candidate_raw, model_bytes=model_raw,
            expected_candidate_sha256=record["candidate_sha256"],
            expected_model_sha256=model_sha,
        )
        vb.require(candidate["explicit_block_count"] == 1 and
                   candidate["selected_block_index"] == 0,
                   "MULTIPLE_OR_UNSELECTED_SOURCE_BLOCKS")
        vb.require(candidate["source_block_sha256"] == work["interpretation_sha256"],
                   "INTERPRETATION_SOURCE_BLOCK_MISMATCH")
        point = exact.parse_json(point_raw, 64 * 1024)
        vb.require(type(point) is list and point_raw == exact.canonical_bytes(point),
                   "POINT_NOT_CANONICAL_ARRAY")
        objective = exact.verify_point(exact.compile_model(model), point)
        claimed = exact.rational(candidate["claimed_upper"])
        vb.require(objective > claimed, "POINT_DOES_NOT_REFUTE_FORMAL_CLAIM")
        checked.append({
            "work_id": work_id,
            "candidate_sha256": record["candidate_sha256"],
            "point_sha256": record["certificate_sha256"],
            "model_sha256": model_sha,
            "source_sha256": work["source_sha256"],
            "source_block_sha256": candidate["source_block_sha256"],
            "formal_refutation_margin": str(objective - claimed),
            "mathematical_replay": "exact_formal_refutation_replayed",
            "publisher_or_paper_error_verified": False,
        })
    report: dict[str, Any] = {
        "schema_version": VERSION,
        "status": "accepted_formal_refutations_replayed" if checked else "no_accepted_records_to_replay",
        "input_commitments": {"registry": vb.commitment(registry),
                              "protocol": vb.commitment(protocol), "run": vb.commitment(run)},
        "accepted_receipts_declared": len(expected),
        "accepted_formal_refutations_replayed": len(checked),
        "replayed": checked,
        "original_development_score": original,
        "original_denominators_and_alarm_counts_preserved": True,
        "source_interpretation_independently_adjudicated": False,
        "family_independence_authenticated": False,
        "publication_error_established": False,
        "protected_evaluation_performed": False,
        "scope": "declared_source_block_plus_formal_counterexample_only",
        "limitations": [
            "A valid point refutes the supplied formalization, not a publication or experimental conclusion.",
            "Work labels and source_correspondence remain separately supplied unverified declarations.",
            "No accepted receipts means no mathematical evidence was replayed.",
            "Receipt certificate_sha256 denotes an exact canonical point in this optional profile.",
            "This profile requires exactly one marked source block, no hints, and interpretation SHA equal to that block's bytes.",
            "Artifact byte pins detect substitution, not authentic publisher provenance or prespecification timing.",
            "Missing and non-accepted evidence is not dropped from the legacy denominator or alarm counts.",
        ],
    }
    vb.require(len(vb.canonical_bytes(report)) <= MAX_REPORT_BYTES, "REPORT_BYTE_LIMIT")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("registry", "protocol", "run"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    for name in ("registry", "protocol", "run"):
        parser.add_argument("--expected-" + name + "-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        documents = [vb.parse_document(_load(getattr(args, name), vb.MAX_BYTES))
                     for name in ("registry", "protocol", "run")]
        report = replay(
            *documents, args.evidence_root,
            expected_registry_sha256=args.expected_registry_sha256,
            expected_protocol_sha256=args.expected_protocol_sha256,
            expected_run_sha256=args.expected_run_sha256,
        )
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        # Never echo filenames, source snippets, reviewer content or private IDs.
        code = str(exc) if isinstance(exc, (vb.BenchmarkError, source.UnsupportedClaim,
                                             exact.CertificateError)) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": code}))
        return 2
    sys.stdout.buffer.write(vb.canonical_bytes(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
