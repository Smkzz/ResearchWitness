"""Validate a prospective ResearchWitness study *draft* without opening protected data.

This is a bounded declaration validator, not protocol preregistration custody,
statistical power verification, a sealed holdout or a scientific scoring engine.
An externally pinned canonical digest can later be checked by an authorized
isolated custodian; this CLI never grants that authority.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path
import re
import sys
from typing import Any

from tools import verification_benchmark as vb
from tools.offline_files import read_regular

SCHEMA_VERSION = "rw-research-study-registration.v1"
MAX_INPUT_BYTES = 64 * 1024
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z", re.ASCII)
SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _require(value: bool, code: str) -> None:
    if not value:
        raise vb.BenchmarkError(code)


def _fields(value: Any, names: str) -> dict[str, Any]:
    _require(type(value) is dict and set(value) == set(names.split()), "OBJECT_FIELDS")
    return value


def _id(value: Any) -> str:
    _require(type(value) is str and ID.fullmatch(value) is not None, "INVALID_ID")
    return value


def _sha(value: Any) -> str:
    _require(type(value) is str and SHA256.fullmatch(value) is not None, "INVALID_SHA256")
    return value


def _text(value: Any, minimum: int = 20, maximum: int = 2000) -> str:
    _require(type(value) is str and minimum <= len(value) <= maximum
             and value.strip() == value, "TEXT_DECLARATION_REQUIRED")
    return value


def _int(value: Any, lower: int, upper: int, code: str) -> int:
    _require(type(value) is int and lower <= value <= upper, code)
    return value


def _fraction(value: Any, *, allow_zero: bool = False) -> Fraction:
    _fields(value, "numerator denominator")
    n = _int(value["numerator"], 0 if allow_zero else 1, 1_000_000, "FRACTION_NUMERATOR")
    d = _int(value["denominator"], 1, 1_000_000, "FRACTION_DENOMINATOR")
    _require(n <= d, "FRACTION_RANGE")
    return Fraction(n, d)


def validate(registration: dict[str, Any], *,
             expected_registration_sha256: str | None = None) -> dict[str, Any]:
    """Check commitments, study design and zero-spend/custody boundaries.

    A valid declaration does not prove that its design has enough statistical
    power, source labels are true, data are independently isolated, or hashes
    were pinned *before* any outcome was observed.
    """
    vb.parse_document(vb.canonical_bytes(registration))
    _fields(registration, "schema_version study_id designation research_question arms "
                          "sampling endpoints analysis resources stopping data_governance")
    _require(registration["schema_version"] == SCHEMA_VERSION, "SCHEMA_VERSION")
    _id(registration["study_id"])
    _require(registration["designation"] in {"pilot_only", "confirmatory_intended"},
             "INVALID_STUDY_DESIGNATION")
    _text(registration["research_question"], minimum=40)
    arms = registration["arms"]
    _require(type(arms) is list and len(arms) == 2, "TWO_PINNED_ARMS_REQUIRED")
    for role, arm in zip(("baseline", "candidate"), arms):
        _fields(arm, "role implementation_sha256 proposal_kind model_sha256 prompt_sha256")
        _require(arm["role"] == role, "ARM_ROLE")
        _sha(arm["implementation_sha256"])
        _require(arm["proposal_kind"] in {"deterministic_local", "authorized_cached_ai"},
                 "PROPOSAL_KIND")
        if arm["proposal_kind"] == "deterministic_local":
            _require(arm["model_sha256"] is None and arm["prompt_sha256"] is None,
                     "UNEXPECTED_MODEL_IDENTITY")
        else:
            _sha(arm["model_sha256"])
            _sha(arm["prompt_sha256"])
    _require(arms[0]["implementation_sha256"] != arms[1]["implementation_sha256"],
             "IDENTICAL_ARM_COMMITMENTS")

    frame = _fields(registration["sampling"],
                    "unit family_grouping selection_rule eligibility_rule exclusion_rule "
                    "minimum_positive_families minimum_negative_families "
                    "minimum_negative_relationships sample_size_justification")
    _require(frame["unit"] == "work_family", "FAMILY_LEVEL_REQUIRED")
    _require(frame["family_grouping"] ==
             "group_versions_corrections_supplements_and_shared_datasets",
             "INDEPENDENCE_GROUPING_MISSING")
    _text(frame["selection_rule"], minimum=35)
    _text(frame["eligibility_rule"], minimum=35)
    _text(frame["exclusion_rule"], minimum=35)
    pos = _int(frame["minimum_positive_families"], 1, 1_000_000, "POSITIVE_SAMPLE_SIZE")
    neg = _int(frame["minimum_negative_families"], 1, 1_000_000, "NEGATIVE_SAMPLE_SIZE")
    neg_rel = _int(frame["minimum_negative_relationships"], 1, 1_000_000,
                   "NEGATIVE_RELATIONSHIP_SAMPLE_SIZE")
    _text(frame["sample_size_justification"],
          minimum=60 if registration["designation"] == "confirmatory_intended" else 35)
    if registration["designation"] == "confirmatory_intended":
        # Preserve the v1.3 lower bounds, but they do NOT establish power for
        # this broader comparative research question.
        _require(neg >= 15 and neg_rel >= 50, "LEGACY_CUSTODY_MINIMUM_NOT_MET")

    endpoints = _fields(registration["endpoints"],
                        "primary safety registered_denominator no_hidden_failures")
    _require(endpoints["primary"] == "eligible_positive_family_detection",
             "PRIMARY_ENDPOINT")
    _require(endpoints["safety"] == "eligible_negative_family_false_alarm_emission",
             "SAFETY_ENDPOINT")
    _require(endpoints["registered_denominator"] == "all_selected_work_families",
             "REGISTERED_DENOMINATOR")
    _require(endpoints["no_hidden_failures"] is True, "MISSING_CASE_POLICY")

    analysis = _fields(registration["analysis"],
                       "paired_unit primary_test primary_sidedness primary_estimand "
                       "safety_test safety_bound_method safety_estimand "
                       "success_decision_rule primary_alpha safety_alpha "
                       "minimum_practical_gain maximum_false_alarm_increase "
                       "missingness_policy multiplicity_policy uncertainty_plan")
    _require(analysis["paired_unit"] == "work_family", "PAIRED_UNIT")
    _require(analysis["primary_test"] == "exact_paired_discordance", "PRIMARY_TEST")
    _require(analysis["primary_sidedness"] == "one_sided_candidate_improvement",
             "PRIMARY_SIDEDNESS")
    _require(analysis["primary_estimand"] ==
             "candidate_minus_baseline_positive_family_detection",
             "PRIMARY_ESTIMAND")
    _require(analysis["safety_test"] == "one_sided_negative_family_harm_bound",
             "SAFETY_TEST")
    _require(analysis["safety_bound_method"] ==
             "bonferroni_clopper_pearson_difference", "SAFETY_BOUND_METHOD")
    _require(analysis["safety_estimand"] ==
             "candidate_minus_baseline_negative_family_alarm_rate",
             "SAFETY_ESTIMAND")
    _require(analysis["success_decision_rule"] ==
             "significant_and_practical_detection_gain_and_safe_upper_bound",
             "SUCCESS_DECISION_RULE")
    primary_alpha = _fraction(analysis["primary_alpha"])
    safety_alpha = _fraction(analysis["safety_alpha"])
    _require(primary_alpha + safety_alpha <= Fraction(1, 20),
             "FAMILYWISE_ALPHA_EXCEEDED")
    _fraction(analysis["minimum_practical_gain"])
    safety_margin = _fraction(analysis["maximum_false_alarm_increase"], allow_zero=True)
    _require(safety_margin < 1, "VACUOUS_SAFETY_MARGIN")
    _require(analysis["missingness_policy"] == "report_bounds_or_inconclusive",
             "MISSINGNESS_POLICY")
    _require(analysis["multiplicity_policy"] == "preallocated_alpha_no_posthoc",
             "MULTIPLICITY_POLICY")
    _text(analysis["uncertainty_plan"], minimum=40)

    resources = _fields(registration["resources"],
                        "max_elapsed_ms_per_work max_calls_per_work max_cost_micro_eur_per_work")
    _int(resources["max_elapsed_ms_per_work"], 1, 10_000_000, "RUNTIME_CAP")
    _int(resources["max_calls_per_work"], 0, 100_000, "CALL_CAP")
    _require(resources["max_cost_micro_eur_per_work"] == 0
             and type(resources["max_cost_micro_eur_per_work"]) is int,
             "COST_AUTHORIZATION_REQUIRED")

    stopping = _fields(registration["stopping"],
                       "max_development_revisions confirmatory_runs interim_sealed_looks "
                       "invalid_run_policy")
    _int(stopping["max_development_revisions"], 1, 10, "REVISION_CAP")
    _require(stopping["confirmatory_runs"] == 1
             and type(stopping["confirmatory_runs"]) is int, "CONFIRMATORY_RETRY_LIMIT")
    _require(stopping["interim_sealed_looks"] == 0
             and type(stopping["interim_sealed_looks"]) is int, "INTERIM_LOOK_NOT_ALLOWED")
    _require(stopping["invalid_run_policy"] == "preserve_and_report_no_reuse",
             "INVALID_RUN_POLICY")

    governance = _fields(registration["data_governance"],
                         "custody_status study_material identities_in_developer_ledger "
                         "exposed_examples_policy label_policy source_license_policy")
    _require(governance["custody_status"] == "not_qualified", "CUSTODY_AUTHORITY_REQUIRED")
    _require(governance["study_material"] == "not_collected", "SEALED_DATA_NOT_ALLOWED")
    _require(governance["identities_in_developer_ledger"] is False,
             "PROTECTED_IDENTITIES_NOT_ALLOWED")
    _require(governance["exposed_examples_policy"] ==
             "exclude_historical_and_developer_exposed", "EXPOSURE_POLICY")
    _require(governance["label_policy"] ==
             "source_supported_positive_negative_and_unresolved", "LABEL_POLICY")
    _require(governance["source_license_policy"] ==
             "review_permissions_before_collection", "LICENSE_POLICY")

    digest = vb.commitment(registration)
    if expected_registration_sha256 is not None:
        _sha(expected_registration_sha256)
        _require(digest == expected_registration_sha256, "REGISTRATION_PIN_MISMATCH")

    return {
        "schema_version": "rw-registration-validation-receipt.v1",
        "status": "VALID_DEVELOPMENT_DRAFT_NOT_SEALED",
        "study_id": registration["study_id"],
        "study_designation": registration["designation"],
        "canonical_registration_sha256": digest,
        "external_pin_supplied_and_matched": expected_registration_sha256 is not None,
        "minimum_declared_positive_families": pos,
        "minimum_declared_negative_families": neg,
        "minimum_declared_negative_relationships": neg_rel,
        "alpha_allocation": {
            "primary": {"numerator": primary_alpha.numerator,
                        "denominator": primary_alpha.denominator},
            "safety": {"numerator": safety_alpha.numerator,
                       "denominator": safety_alpha.denominator},
        },
        "authority": "DRAFT_ONLY_NO_CUSTODY_ACTIVATION",
        "scientific_performance_established": False,
        "sample_size_power_verified": False,
        "source_labels_authenticated": False,
        "protected_evaluation_performed": False,
        "additional_spend_authorized_eur": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    parser.add_argument("--expected-registration-sha256")
    args = parser.parse_args(argv)
    try:
        data = read_regular(args.draft, MAX_INPUT_BYTES)
        registration = vb.parse_document(data)
        receipt = validate(registration,
                           expected_registration_sha256=args.expected_registration_sha256)
        sys.stdout.buffer.write(vb.canonical_bytes(receipt))
        return 0
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        diagnostic = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": diagnostic}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
