"""Paired DEVELOPMENT comparison over externally pinned declared benchmark receipts.

No protected labels, live providers, real-money calls, certificate authentication,
work-family independence or scientific inference is provided by this scorer.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any

from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-development-paired-comparison.v1"


def _fraction(numerator: int, denominator: int) -> dict[str, int] | None:
    return {"numerator": numerator, "denominator": denominator} if denominator else None


def _state(work_ids: list[str], works: dict[str, dict[str, Any]],
           receipts: dict[str, dict[str, Any]], label: str) -> bool | None:
    records = [receipts.get(identifier) for identifier in work_ids]
    if label == "positive":
        detected = any(
            record is not None and record["status"] == "completed"
            and record["alarm_emitted"] is True
            and record["certificate_status"] == "accepted"
            and record["source_correspondence"] == "supported"
            and record["target_id"] == works[identifier]["target_id"]
            for identifier, record in zip(work_ids, records)
        )
        if detected:
            return True
    else:
        # Alarm emission precedes certificate acceptance, target matching and
        # terminal state; a rejected witness is still a false-alarm event.
        if any(record is not None and record["alarm_emitted"] is True for record in records):
            return True
    if all(record is not None and record["status"] == "completed" for record in records):
        return False
    return None


def _paired_summary(pairs: list[tuple[bool | None, bool | None]],
                    *, desirable: str) -> dict[str, Any]:
    table = {"both": 0, "baseline_only": 0, "candidate_only": 0,
             "neither": 0, "unknown": 0}
    base_lower = cand_lower = base_unknown = cand_unknown = 0
    for baseline, candidate in pairs:
        if baseline is True:
            base_lower += 1
        if candidate is True:
            cand_lower += 1
        if baseline is None:
            base_unknown += 1
        if candidate is None:
            cand_unknown += 1
        if baseline is None or candidate is None:
            table["unknown"] += 1
        elif baseline and candidate:
            table["both"] += 1
        elif baseline:
            table["baseline_only"] += 1
        elif candidate:
            table["candidate_only"] += 1
        else:
            table["neither"] += 1
    n = len(pairs)
    base_upper = base_lower + base_unknown
    cand_upper = cand_lower + cand_unknown
    # Positive detection: candidate minus baseline. Negative false-alarm rate:
    # baseline minus candidate. Bounds include EVERY unknown family.
    low, high = ((cand_lower - base_upper, cand_upper - base_lower)
                 if desirable == "increase" else
                 (base_lower - cand_upper, base_upper - cand_lower))
    return {
        "independent_family_count_declared": n,
        "paired_known": n - table["unknown"],
        "paired_unknown": table["unknown"],
        "paired_table": table,
        "baseline_lower_bound": _fraction(base_lower, n),
        "baseline_upper_bound": _fraction(base_upper, n),
        "candidate_lower_bound": _fraction(cand_lower, n),
        "candidate_upper_bound": _fraction(cand_upper, n),
        "favorable_change_lower_bound": _fraction(low, n),
        "favorable_change_upper_bound": _fraction(high, n),
        "interval_type": "logical_missing_outcome_bounds_not_confidence_interval",
    }


def compare(registry: dict[str, Any], baseline_protocol: dict[str, Any],
            baseline_run: dict[str, Any], candidate_protocol: dict[str, Any],
            candidate_run: dict[str, Any], *, expected_registry_sha256: str,
            expected_baseline_protocol_sha256: str,
            expected_candidate_protocol_sha256: str) -> dict[str, Any]:
    """Compare declarations on the exact same registered works and cost envelope."""
    baseline = vb.score(
        registry, baseline_protocol, baseline_run,
        expected_registry_sha256=expected_registry_sha256,
        expected_protocol_sha256=expected_baseline_protocol_sha256,
    )
    candidate = vb.score(
        registry, candidate_protocol, candidate_run,
        expected_registry_sha256=expected_registry_sha256,
        expected_protocol_sha256=expected_candidate_protocol_sha256,
    )
    shared = ("max_elapsed_ms", "max_calls", "max_cost_micro_eur")
    vb.require(all(baseline_protocol[k] == candidate_protocol[k] for k in shared),
               "RESOURCE_BUDGET_MISMATCH")
    vb.require(baseline_protocol["schedule"] == candidate_protocol["schedule"],
               "SCHEDULE_ORDER_MISMATCH")
    works = vb._registry(registry)
    families: dict[str, list[str]] = defaultdict(list)
    for work_id, work in works.items():
        families[work["family_id"]].append(work_id)
    baseline_receipts = {row["work_id"]: row for row in baseline_run["results"]}
    candidate_receipts = {row["work_id"]: row for row in candidate_run["results"]}
    categories: dict[str, list[tuple[bool | None, bool | None]]] = {
        "positive": [], "negative": [],
    }
    unresolved = excluded = 0
    for family_id in sorted(families):
        members = families[family_id]
        anchor = works[members[0]]
        if not anchor["eligible"]:
            excluded += 1
            continue
        if anchor["label"] == "unresolved":
            unresolved += 1
            continue
        label = anchor["label"]
        categories[label].append((
            _state(members, works, baseline_receipts, label),
            _state(members, works, candidate_receipts, label),
        ))
    positives = _paired_summary(categories["positive"], desirable="increase")
    negatives = _paired_summary(categories["negative"], desirable="decrease")
    complete = (baseline["status"] == candidate["status"] == "complete"
                and positives["paired_unknown"] == negatives["paired_unknown"] == 0)
    return {
        "schema_version": VERSION,
        "classification": "PAIRED_DEVELOPMENT_DECLARATIONS_NOT_SCIENTIFIC_VALIDATION",
        "status": "complete" if complete else "incomplete",
        "scientific_performance_established": False,
        "protected_evaluation_performed": False,
        "source_and_certificate_validation": "SUPPLIED_DECLARATIONS_NOT_REPLAYED",
        "family_independence": "DECLARED_FAMILIES_NOT_AUTHENTICATED",
        "commitments": {
            "registry": vb.commitment(registry),
            "baseline_protocol": vb.commitment(baseline_protocol),
            "candidate_protocol": vb.commitment(candidate_protocol),
            "baseline_run": vb.commitment(baseline_run),
            "candidate_run": vb.commitment(candidate_run),
        },
        "resource_limits_per_work": {
            key: baseline_protocol[key] for key in shared
        },
        "registered_work_count": len(works),
        "excluded_family_count": excluded,
        "unresolved_family_count": unresolved,
        "positive_detection": positives,
        "negative_false_alarm": negatives,
        "baseline_execution": {
            "work_counts": baseline["work_counts"], "resources_reported": baseline["resources_reported"]
        },
        "candidate_execution": {
            "work_counts": candidate["work_counts"], "resources_reported": candidate["resources_reported"]
        },
        "limitations": [
            "Both methods' results and labels are supplied declarations, not independently verified evidence.",
            "Equal declared work budgets and a shared schedule do not authenticate resource usage.",
            "Source/certificate truth and work-family independence remain unverified.",
            "A failed or missing family is unknown, not silently a confirmed negative or successful detection.",
            "Logical missing-outcome bounds are not statistical confidence intervals.",
            "No superiority p-value, sealed evaluation, baseline runtime execution or new discovery is claimed.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("registry", "baseline-protocol", "baseline-run",
                 "candidate-protocol", "candidate-run"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("registry", "baseline-protocol", "candidate-protocol"):
        parser.add_argument("--expected-" + name + "-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        docs = {
            name: vb.parse_document(read_regular(
                getattr(args, name.replace("-", "_")), vb.MAX_BYTES))
            for name in ("registry", "baseline-protocol", "baseline-run",
                         "candidate-protocol", "candidate-run")
        }
        report = compare(
            docs["registry"], docs["baseline-protocol"], docs["baseline-run"],
            docs["candidate-protocol"], docs["candidate-run"],
            expected_registry_sha256=args.expected_registry_sha256,
            expected_baseline_protocol_sha256=args.expected_baseline_protocol_sha256,
            expected_candidate_protocol_sha256=args.expected_candidate_protocol_sha256,
        )
        sys.stdout.buffer.write(vb.canonical_bytes(report))
        return 0
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        diagnostic = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": diagnostic}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
