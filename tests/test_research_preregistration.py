"""Prospective study draft contracts: synthetic only, no custody activation."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest

from tools import research_preregistration as registration
from tools import verification_benchmark as vb


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/synthetic-study-registration/draft.json"
SCHEMA = ROOT / "schemas/research-registration.v1.schema.json"


def draft():
    return vb.parse_document(FIXTURE.read_bytes())


def validate(value=None, external_pin=None):
    obj = draft() if value is None else value
    return registration.validate(obj, expected_registration_sha256=external_pin)


def test_synthetic_draft_and_schema_agree():
    obj = draft()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(obj)
    receipt = validate(obj)
    assert receipt["status"] == "VALID_DEVELOPMENT_DRAFT_NOT_SEALED"
    assert receipt["canonical_registration_sha256"] == vb.commitment(obj)
    assert receipt["scientific_performance_established"] is False
    assert receipt["protected_evaluation_performed"] is False
    assert receipt["source_labels_authenticated"] is False
    assert receipt["sample_size_power_verified"] is False
    assert receipt["authority"] == "DRAFT_ONLY_NO_CUSTODY_ACTIVATION"
    assert receipt["additional_spend_authorized_eur"] == 0
    assert receipt["alpha_allocation"] == {
        "primary": {"numerator": 1, "denominator": 40},
        "safety": {"numerator": 1, "denominator": 40},
    }


def test_external_pin_is_not_created_by_report():
    value = draft()
    exact = vb.commitment(value)
    assert validate(value, exact)["external_pin_supplied_and_matched"] is True
    value["sampling"]["selection_rule"] += " (modified after preregistration)"
    with pytest.raises(vb.BenchmarkError, match="REGISTRATION_PIN_MISMATCH"):
        validate(value, exact)


@pytest.mark.parametrize(("mutate","expected"), [
    (lambda x: x.update(unexpected="field"), "OBJECT_FIELDS"),
    (lambda x: x.update(schema_version="v999"), "SCHEMA_VERSION"),
    (lambda x: x.update(study_id="../bad"), "INVALID_ID"),
    (lambda x: x["arms"][0].update(implementation_sha256="zz"), "INVALID_SHA256"),
    (lambda x: x["arms"][1].update(implementation_sha256="1" * 64),
     "IDENTICAL_ARM_COMMITMENTS"),
    (lambda x: x["arms"][0].update(proposal_kind="authorized_cached_ai"),
     "INVALID_SHA256"),
    (lambda x: x["arms"][0].update(prompt_sha256="1" * 64), "UNEXPECTED_MODEL_IDENTITY"),
    (lambda x: x["sampling"].update(unit="row"), "FAMILY_LEVEL_REQUIRED"),
    (lambda x: x["sampling"].update(family_grouping="split_same_paper_versions"),
     "INDEPENDENCE_GROUPING_MISSING"),
    (lambda x: x["sampling"].update(minimum_positive_families=True),
     "POSITIVE_SAMPLE_SIZE"),
    (lambda x: x["endpoints"].update(no_hidden_failures=False),
     "MISSING_CASE_POLICY"),
    (lambda x: x["analysis"].update(paired_unit="relationship"), "PAIRED_UNIT"),
    (lambda x: x["analysis"].update(missingness_policy="complete_cases_only"),
     "MISSINGNESS_POLICY"),
    (lambda x: x["analysis"].update(multiplicity_policy="retune_on_holdout"),
     "MULTIPLICITY_POLICY"),
    (lambda x: x["resources"].update(max_cost_micro_eur_per_work=1),
     "COST_AUTHORIZATION_REQUIRED"),
    (lambda x: x["resources"].update(max_cost_micro_eur_per_work=False),
     "COST_AUTHORIZATION_REQUIRED"),
    (lambda x: x["stopping"].update(confirmatory_runs=2),
     "CONFIRMATORY_RETRY_LIMIT"),
    (lambda x: x["stopping"].update(interim_sealed_looks=1),
     "INTERIM_LOOK_NOT_ALLOWED"),
    (lambda x: x["data_governance"].update(custody_status="self_declared_qualified"),
     "CUSTODY_AUTHORITY_REQUIRED"),
    (lambda x: x["data_governance"].update(study_material="protected_labels"),
     "SEALED_DATA_NOT_ALLOWED"),
    (lambda x: x["data_governance"].update(identities_in_developer_ledger=True),
     "PROTECTED_IDENTITIES_NOT_ALLOWED"),
    (lambda x: x["data_governance"].update(
        exposed_examples_policy="promote_previous_wins"), "EXPOSURE_POLICY"),
])
def test_draft_rejects_policy_and_structure_violations(mutate, expected):
    obj = draft()
    mutate(obj)
    with pytest.raises(vb.BenchmarkError, match=expected):
        registration.validate(obj)


def test_study_power_never_claimed_solely_from_legacy_minimum():
    obj = draft()
    obj["designation"] = "confirmatory_intended"
    obj["sampling"]["minimum_positive_families"] = 1
    obj["sampling"]["minimum_negative_families"] = 14
    obj["sampling"]["minimum_negative_relationships"] = 50
    with pytest.raises(vb.BenchmarkError, match="LEGACY_CUSTODY_MINIMUM_NOT_MET"):
        validate(obj)
    obj["sampling"]["minimum_negative_families"] = 15
    receipt = validate(obj)
    assert receipt["status"] == "VALID_DEVELOPMENT_DRAFT_NOT_SEALED"
    assert receipt["sample_size_power_verified"] is False
    assert receipt["protected_evaluation_performed"] is False


@pytest.mark.parametrize(("primary","safety"), [
    ({"numerator": 1, "denominator": 20},
     {"numerator": 1, "denominator": 40}),
    ({"numerator": 2, "denominator": 25},
     {"numerator": 1, "denominator": 100}),
])
def test_familywise_alpha_budget_is_enforced(primary, safety):
    obj = draft()
    obj["analysis"]["primary_alpha"] = primary
    obj["analysis"]["safety_alpha"] = safety
    with pytest.raises(vb.BenchmarkError, match="FAMILYWISE_ALPHA_EXCEEDED"):
        validate(obj)


def test_invalid_alpha_and_boolean_fraction_rejected():
    obj = draft()
    obj["analysis"]["primary_alpha"]["numerator"] = True
    with pytest.raises(vb.BenchmarkError, match="FRACTION_NUMERATOR"):
        validate(obj)
    obj["analysis"]["primary_alpha"]["numerator"] = 1
    obj["analysis"]["primary_alpha"]["denominator"] = 0
    with pytest.raises(vb.BenchmarkError, match="FRACTION_DENOMINATOR"):
        validate(obj)


def test_no_duplicate_keys_or_trailing_nans_in_cli(tmp_path):
    target = tmp_path / "duplicate.json"
    data = FIXTURE.read_bytes()
    target.write_bytes(data.replace(b'"study_id":', b'"study_id":"other","study_id":', 1))
    process = subprocess.run(
        [sys.executable, "-m", "tools.research_preregistration", str(target)],
        cwd=ROOT, capture_output=True, timeout=30,
    )
    assert process.returncode == 2
    assert json.loads(process.stderr)["status"] == "invalid"
    assert not process.stdout


def test_cli_is_offline_canonical_and_checks_external_pin():
    expected = vb.commitment(draft())
    command = [sys.executable, "-m", "tools.research_preregistration", str(FIXTURE)]
    ok = subprocess.run(command + ["--expected-registration-sha256", expected],
                        cwd=ROOT, capture_output=True, timeout=30)
    assert ok.returncode == 0, ok.stderr
    assert b"\r\n" not in ok.stdout
    assert json.loads(ok.stdout)["canonical_registration_sha256"] == expected
    bad = subprocess.run(command + ["--expected-registration-sha256", "f" * 64],
                         cwd=ROOT, capture_output=True, timeout=30)
    assert bad.returncode == 2
    assert json.loads(bad.stderr)["code"] == "REGISTRATION_PIN_MISMATCH"


def test_canonical_validation_is_deterministic():
    value = draft()
    one = registration.validate(value)
    two = registration.validate(deepcopy(value))
    assert vb.canonical_bytes(one) == vb.canonical_bytes(two)
