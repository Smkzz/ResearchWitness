from __future__ import annotations

import pytest

from tools.assign_correction_split import allocate, canonical_identifier


def test_doi_forms_canonicalize_to_same_stable_pair():
    first = allocate("https://doi.org/10.1234/Example.A", "doi:10.5678/Correction")
    second = allocate("doi:10.1234/example.a", "https://dx.doi.org/10.5678/correction")
    assert first == second
    assert first["protocol"] == "researchwitness-correction-split-v1"
    assert first["original_identifier"] == "doi:10.1234/example.a"


def test_namespaced_non_doi_identifiers_are_supported():
    assert canonical_identifier(" PMID: 12345 ") == "pmid:12345"
    result = allocate("PMCID:PMC123", "EuropePMC:67890")
    assert result["original_identifier"] == "pmcid:pmc123"
    assert result["correction_identifier"] == "europepmc:67890"


@pytest.mark.parametrize("value", ["", "   ", "PMC123", "10.1234/has whitespace"])
def test_ambiguous_identifiers_fail_closed(value):
    with pytest.raises(ValueError):
        canonical_identifier(value)


def test_split_is_fixed_and_reserved_fraction_is_prespecified():
    result = allocate("10.1000/original", "10.1000/correction")
    expected_bucket = int(result["sha256"][:8], 16) % 5
    assert result["bucket"] == expected_bucket
    assert result["assignment"] == (
        "RESERVED_FOR_FUTURE_EVALUATION" if expected_bucket == 0 else "DEVELOPMENT"
    )
