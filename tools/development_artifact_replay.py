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
from pathlib import Path
import stat
import sys
import time
from typing import Any

from researchwitness import exact_optimization as exact
from researchwitness import source_claims as source
from researchwitness import strict
from tools import verification_benchmark as vb
from tools import offline_files
from tools.offline_files import read_regular

VERSION = "rw-development-artifact-replay.v1"
MAX_ACCEPTED = 128
MAX_TOTAL_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
FROZEN_ARMS = ("box-midpoint", "box-objective-corner")
FROZEN_TARGET_ID = "marked-claim"


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


def _replay_work(work_id: str, work: dict[str, Any], record: dict[str, Any],
                 evidence_root: Path, budget: list[int]) -> dict[str, Any]:
    """Replay one accepted receipt or raise; `budget` holds cumulative bytes."""
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
        budget[0] += len(raw)
        vb.require(budget[0] <= MAX_TOTAL_ARTIFACT_BYTES,
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
    return {
        "work_id": work_id,
        "candidate_sha256": record["candidate_sha256"],
        "point_sha256": record["certificate_sha256"],
        "model_sha256": model_sha,
        "source_sha256": work["source_sha256"],
        "source_block_sha256": candidate["source_block_sha256"],
        "formal_refutation_margin": str(objective - claimed),
        "mathematical_replay": "exact_formal_refutation_replayed",
        "publisher_or_paper_error_verified": False,
    }


def _bound_inputs(registry: dict[str, Any], protocol: dict[str, Any],
                  run: dict[str, Any], *, expected_registry_sha256: str,
                  expected_protocol_sha256: str, expected_run_sha256: str
                  ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    exact._sha(expected_run_sha256)
    original = vb.score(
        registry, protocol, run,
        expected_registry_sha256=expected_registry_sha256,
        expected_protocol_sha256=expected_protocol_sha256,
    )
    vb.require(vb.commitment(run) == expected_run_sha256, "RUN_EXTERNAL_PIN_MISMATCH")
    works = vb._registry(registry)
    # No alias of two identities into one Windows case-insensitive folder.
    vb.require(len({w.casefold() for w in works}) == len(works),
               "WORK_PATH_CASE_COLLISION")
    return original, works, {r["work_id"]: r for r in run["results"]}


def frozen_implementation_pins() -> dict[str, str]:
    """Commit to the fixed algorithm, its local implementation and Python runtime."""
    files = {name: _digest(_load(Path(path), exact.MAX_MODEL_BYTES))
             for name, path in (("replay", __file__), ("compiler", source.__file__),
                                ("checker", exact.__file__), ("scorer", vb.__file__),
                                ("files", offline_files.__file__), ("paths", strict.__file__))}
    runtime = {"python": sys.version, "platform": sys.platform,
               "implementation": sys.implementation.name}
    return {arm: vb.commitment({"profile": "rw-marked-box-probe.v1",
                                "arm": arm, "files": files, "runtime": runtime})
            for arm in FROZEN_ARMS}


def _probe(raw: bytes, source_sha256: str, arm: str) -> tuple[dict, list[str], bool]:
    """Run the full single-point search, without labels, on one affine box."""
    candidate, model = source.compile_candidate(
        raw, block_index=0, expected_source_sha256=source_sha256)
    vb.require(candidate["explicit_block_count"] == 1, "MULTIPLE_SOURCE_BLOCKS")
    compiled = exact.compile_model(model)
    vb.require(not (compiled.inequalities or compiled.equalities or compiled.products),
               "FROZEN_ARM_REQUIRES_AFFINE_BOX")
    if arm == "box-midpoint":
        point = [str((lo + hi) / 2) for lo, hi in compiled.bounds]
    else:
        vb.require(arm == "box-objective-corner", "UNKNOWN_FROZEN_ARM")
        coefficients = dict(compiled.objective)
        point = [str(hi if coefficients.get(i, 0) > 0 else lo)
                 for i, (lo, hi) in enumerate(compiled.bounds)]
    return candidate, point, exact.verify_point(compiled, point) > exact.rational(
        candidate["claimed_upper"])


def _replay_frozen(work: dict[str, Any], record: dict[str, Any], evidence_root: Path,
                   budget: list[int], arm: str, max_elapsed_ms: int) -> dict[str, Any]:
    """Verify a completion against regenerated semantics, never a retained report."""
    start = time.monotonic_ns()
    vb.require(record["status"] == "completed", "FROZEN_ARM_RECEIPT_NOT_COMPLETED")
    folder = evidence_root / work["work_id"]
    _directory(folder)
    raw = _load(folder / "source.txt", min(source.MAX_SOURCE_BYTES,
                                          MAX_TOTAL_ARTIFACT_BYTES - budget[0] + 1))
    budget[0] += len(raw)
    vb.require(budget[0] <= MAX_TOTAL_ARTIFACT_BYTES, "CUMULATIVE_ARTIFACT_BUDGET")
    candidate, point, alarm = _probe(raw, work["source_sha256"], arm)
    vb.require(candidate["source_block_sha256"] == work["interpretation_sha256"],
               "INTERPRETATION_SOURCE_BLOCK_MISMATCH")
    vb.require(work["label"] != "positive" or work["target_id"] == FROZEN_TARGET_ID,
               "FROZEN_ARM_TARGET_ID_MISMATCH")
    vb.require(alarm == record["alarm_emitted"], "FROZEN_ARM_ALARM_MISMATCH")
    result = {"work_id": work["work_id"], "source_sha256": work["source_sha256"],
              "source_block_sha256": candidate["source_block_sha256"],
              "model_sha256": candidate["model_sha256"], "arm": arm,
              "paper_error_established": False}
    if alarm:
        candidate_sha = _digest(exact.canonical_bytes(candidate))
        point_sha = _digest(exact.canonical_bytes(point))
        vb.require(record["certificate_status"] == "accepted", "FROZEN_ARM_ALARM_NOT_ACCEPTED")
        vb.require(record["candidate_sha256"] == candidate_sha and
                   record["certificate_sha256"] == point_sha, "FROZEN_ARM_ALARM_DIGEST_MISMATCH")
        result.update(candidate_sha256=candidate_sha, point_sha256=point_sha,
                      mathematical_replay="exact_formal_refutation_replayed")
    vb.require(time.monotonic_ns() - start <= max_elapsed_ms * 1_000_000,
               "FROZEN_ARM_REPLAY_TIME_LIMIT")
    return result


def verify_receipts(registry: dict[str, Any], protocol: dict[str, Any],
                    run: dict[str, Any], evidence_root: Path, *,
                    expected_registry_sha256: str, expected_protocol_sha256: str,
                    expected_run_sha256: str, frozen_arm: bool = False) -> dict[str, Any]:
    """Per-work replay status for aggregation; nothing is dropped or upgraded.

    Unlike `replay`, a receipt whose evidence is missing, substituted or does
    not refute is reported UNVERIFIED with a stable code instead of aborting.
    Pins, the evidence root, case collisions and budgets still fail closed.
    By default only accepted refutations are replayed. The opt-in frozen arm
    re-executes completed alarm and non-alarm outcomes with no legacy fallback.
    """
    original, works, records = _bound_inputs(
        registry, protocol, run,
        expected_registry_sha256=expected_registry_sha256,
        expected_protocol_sha256=expected_protocol_sha256,
        expected_run_sha256=expected_run_sha256,
    )
    expected = [w for w in protocol["schedule"]
                if w in records and records[w]["certificate_status"] == "accepted"]
    vb.require(len(expected) <= MAX_ACCEPTED, "ACCEPTED_REPLAY_BUDGET")
    _directory(evidence_root)
    arm = None
    non_alarms: list[str] = []
    if frozen_arm:
        try:
            for work_id in works:
                strict.relative_path(work_id)
        except strict.Invalid as exc:
            raise vb.BenchmarkError("FROZEN_ARM_WORK_PATH_NOT_PORTABLE") from exc
        matching = {pin: name for name, pin in frozen_implementation_pins().items()}
        arm = matching.get(protocol["implementation_sha256"])
        vb.require(arm is not None, "FROZEN_ARM_IMPLEMENTATION_MISMATCH")
        vb.require(protocol["max_calls"] == 0, "FROZEN_ARM_PROVIDER_CALLS_NOT_SUPPORTED")
        non_alarms = [w for w in protocol["schedule"]
                      if w in records and works[w]["eligible"]
                      and records[w]["status"] == "completed" and not records[w]["alarm_emitted"]]
        vb.require(len(non_alarms) + len(expected) <= MAX_ACCEPTED, "FROZEN_ARM_REPLAY_BUDGET")
    budget = [0]
    verified: dict[str, dict[str, Any]] = {}
    unverified: dict[str, str] = {}
    verified_non_alarms: dict[str, dict[str, Any]] = {}
    unverified_non_alarms: dict[str, str] = {}
    for work_id in [*expected, *non_alarms]:
        non_alarm = arm is not None and not records[work_id]["alarm_emitted"]
        successes = verified_non_alarms if non_alarm else verified
        failures = unverified_non_alarms if non_alarm else unverified
        try:
            if arm is None:
                successes[work_id] = _replay_work(
                    work_id, works[work_id], records[work_id], evidence_root, budget)
            else:
                successes[work_id] = _replay_frozen(
                    works[work_id], records[work_id], evidence_root, budget,
                    arm, protocol["max_elapsed_ms"])
        except (vb.BenchmarkError, source.UnsupportedClaim, exact.CertificateError) as exc:
            if str(exc) == "CUMULATIVE_ARTIFACT_BUDGET":
                raise
            failures[work_id] = str(exc)
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            failures[work_id] = "ARTIFACT_UNAVAILABLE_OR_INVALID"
    return {
        "original_development_score": original,
        "accepted_receipts_declared": len(expected),
        "verified": verified,
        "unverified": unverified,
        **({"frozen_arm": arm,
            "verified_non_alarms": verified_non_alarms,
            "unverified_non_alarms": unverified_non_alarms} if frozen_arm else {}),
    }


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
    # Establish all schedule, source, family, receipt and zero-cost invariants
    # without changing the legacy denominator or supplied scientific labels.
    original, works, records = _bound_inputs(
        registry, protocol, run,
        expected_registry_sha256=expected_registry_sha256,
        expected_protocol_sha256=expected_protocol_sha256,
        expected_run_sha256=expected_run_sha256,
    )
    expected = [w for w in protocol["schedule"]
                if w in records and records[w]["certificate_status"] == "accepted"]
    vb.require(len(expected) <= MAX_ACCEPTED, "ACCEPTED_REPLAY_BUDGET")
    _directory(evidence_root)
    budget = [0]
    checked = [_replay_work(work_id, works[work_id], records[work_id],
                            evidence_root, budget) for work_id in expected]
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
