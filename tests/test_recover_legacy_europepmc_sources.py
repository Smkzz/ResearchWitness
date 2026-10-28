"""Synthetic-only tests for historical Europe PMC original-byte recovery."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import recover_legacy_europepmc_sources as recovery
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "examples/historical-source-recovery/wave1-source-index.json"


def base_index():
    return vb.parse_document(INDEX_PATH.read_bytes())


def selected(*pmcids):
    result = base_index()
    result["records"] = [
        row for row in result["records"] if row["pmcid"] in pmcids
    ]
    return result


def pinned(index):
    data = vb.canonical_bytes(index)
    return data, sha256(data).hexdigest()


def check(index, root, **options):
    data, digest = pinned(index)
    return recovery.recover(
        index, root, expected_index_sha256=digest,
        exact_index_bytes=data, **options
    )


def fake_body_index(body, pmcid="PMC4339301"):
    index = selected(pmcid)
    assert len(index["records"]) == 1
    index["records"][0]["expected_sha256"] = sha256(body).hexdigest()
    index["records"][0]["expected_bytes"] = len(body)
    return index


class FakeResponse:
    def __init__(self, url, body, *, content_encoding="identity",
                 final_url=None, status=200):
        self.requested = url
        self.body = body
        self.status = status
        self.final_url = final_url or url
        self.headers = {
            "Content-Encoding": content_encoding,
            "Content-Type": "application/xml",
        }

    def geturl(self):
        return self.final_url

    def read(self, count):
        return self.body[:count]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class StubOpener:
    def __init__(self, body, *, final_url=None, content_encoding="identity",
                 status=200):
        self.body = body
        self.final_url = final_url
        self.content_encoding = content_encoding
        self.status = status
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request.full_url, timeout))
        return FakeResponse(
            request.full_url, self.body, final_url=self.final_url,
            content_encoding=self.content_encoding, status=self.status,
        )


def test_committed_index_reproduces_archived_source_manifest_checksum():
    raw = INDEX_PATH.read_bytes()
    index = vb.parse_document(raw)
    records = recovery.validate_index(
        index, expected_index_sha256=sha256(raw).hexdigest(),
        exact_index_bytes=raw,
    )
    assert len(records) == 13
    assert sum(row["source_kind"] == "article" for row in records) == 9
    assert sum(row["source_kind"] == "correction" for row in records) == 4
    assert index["source_manifest"]["sha256"] == recovery.ORIGINAL_MANIFEST_HASH
    assert index["source_manifest"]["retrieved_date"] == "2026-10-05"
    assert all(row["source_url"] == (
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/{row['pmcid']}/fullTextXML"
    ) for row in records)


def test_offline_default_accounts_for_every_missing_source_without_network_or_writes(tmp_path):
    sentinel = StubOpener(b"<article/>")
    result = check(base_index(), tmp_path, opener=sentinel)
    assert result["status"] == "HISTORICAL_SOURCE_RESTORATION_INCOMPLETE"
    assert result["selected_records"] == 13
    assert result["counts_by_status"] == {"SOURCE_MISSING_OFFLINE": 13}
    assert result["network_requests_made"] == 0
    assert result["network_opt_in_given"] is False
    assert result["exact_original_content_hash_matches"] == 0
    assert result["raw_source_text_emitted"] is False
    assert result["scientific_detection_improvement_established"] is False
    assert not list(tmp_path.iterdir())
    assert sentinel.calls == []


def test_byte_identical_local_source_proves_continuity_not_provenance(tmp_path):
    data = b"<article><body><p>test</p></body></article>"
    index = fake_body_index(data)
    source = tmp_path / "PMC4339301.xml"
    source.write_bytes(data)
    spy = StubOpener(b"must never be used")
    result = check(index, tmp_path, network_authorized=True, opener=spy)
    assert result["status"] == "ALL_SELECTED_HISTORICAL_BYTES_PRESENT"
    assert result["records"][0]["status"] == "EXACT_HISTORICAL_BYTES_PRESENT"
    assert result["network_requests_made"] == 0
    assert result["historical_provider_transport_authenticated"] is False
    assert result["article_licences_independently_verified"] is False
    assert spy.calls == []


def test_wrong_existing_bytes_are_never_overwritten_or_network_fetched(tmp_path):
    good = b"<article><body><p>exact</p></body></article>"
    index = fake_body_index(good)
    original = tmp_path / "PMC4339301.xml"
    original.write_bytes(b"changed")
    spy = StubOpener(good)
    result = check(index, tmp_path, network_authorized=True, opener=spy)
    assert result["records"][0]["status"] == (
        "EXISTING_SOURCE_VERSION_MISMATCH_NO_OVERWRITE"
    )
    assert original.read_bytes() == b"changed"
    assert spy.calls == []


def test_explicit_network_opt_in_recovers_only_byte_identical_allowed_origin(tmp_path):
    data = b"<article><body><p>exact</p></body></article>"
    index = fake_body_index(data)
    spy = StubOpener(data)
    report = check(index, tmp_path, network_authorized=True, opener=spy)
    assert report["status"] == "ALL_SELECTED_HISTORICAL_BYTES_PRESENT"
    assert report["network_requests_made"] == 1
    assert report["records"][0]["status"] == (
        "RECOVERED_EXACT_HISTORICAL_BYTES_NEW_TRANSPORT"
    )
    assert spy.calls == [(index["records"][0]["source_url"], 25)]
    assert (tmp_path / "PMC4339301.xml").read_bytes() == data
    receipt = vb.parse_document((tmp_path / "PMC4339301.transfer.json").read_bytes())
    assert receipt["source_version_matches_2026_10_05_pin"] is True
    assert receipt["historical_2026_10_05_transport_proven"] is False
    assert receipt["article_specific_licence_independently_verified"] is False
    assert receipt["protected_partition_accessed"] is False
    # Reopening the same private cache is read-only.
    next_report = check(index, tmp_path, opener=StubOpener(b"not used"))
    assert next_report["records"][0]["status"] == "EXACT_HISTORICAL_BYTES_PRESENT"
    assert next_report["network_requests_made"] == 0


def test_current_provider_version_drift_does_not_modify_historical_corpus(tmp_path):
    old = b"<article>old version</article>"
    current = b"<article>new version</article>"
    index = fake_body_index(old)
    report = check(index, tmp_path, network_authorized=True,
                   opener=StubOpener(current))
    assert report["records"][0]["status"] == (
        "PROVIDER_BODY_DIFFERS_FROM_HISTORICAL_PIN_NO_WRITE"
    )
    assert report["exact_original_content_hash_matches"] == 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(("opener", "status"), [
    (StubOpener(b"test", final_url="https://evil.invalid/other"),
     "PROVIDER_URL_OR_STATUS_UNEXPECTED"),
    (StubOpener(b"test", status=302),
     "PROVIDER_URL_OR_STATUS_UNEXPECTED"),
    (StubOpener(b"test", content_encoding="gzip"),
     "PROVIDER_UNSUPPORTED_CONTENT_ENCODING"),
])
def test_redirects_non200_and_encoded_entities_never_create_source(tmp_path, opener, status):
    index = fake_body_index(b"test")
    report = check(index, tmp_path, network_authorized=True, opener=opener)
    assert report["records"][0]["status"] == status
    assert not list(tmp_path.iterdir())


def test_real_urllib_redirect_handler_never_follows_redirect():
    from urllib.request import Request
    handler = recovery._NoRedirect()
    request = Request("https://www.ebi.ac.uk/europepmc/webservices/rest/"
                      "PMC4339301/fullTextXML")
    assert handler.redirect_request(
        request, None, 302, "Found", {}, "https://evil.invalid/"
    ) is None


def test_one_attempt_cap_counts_other_selected_sources_not_attempted(tmp_path):
    data = b"<article>example</article>"
    index = selected("PMC4339301", "PMC5134271")
    index["records"][0].update(
        expected_sha256=sha256(data).hexdigest(), expected_bytes=len(data),
    )
    spy = StubOpener(data)
    report = check(index, tmp_path, network_authorized=True,
                   max_network_requests=1, opener=spy)
    assert report["selected_records"] == 2
    assert report["network_requests_made"] == 1
    assert report["counts_by_status"]["NOT_ATTEMPTED_REQUEST_CAP"] == 1
    assert report["counts_by_status"]["RECOVERED_EXACT_HISTORICAL_BYTES_NEW_TRANSPORT"] == 1
    assert len(spy.calls) == 1


def test_ambiguous_historical_correction_licence_refuses_new_request(tmp_path):
    index = base_index()
    spy = StubOpener(b"malicious input")
    report = check(index, tmp_path, only_pmcid="PMC6991292",
                   network_authorized=True, opener=spy)
    assert report["records"][0]["status"] == "RIGHTS_DECLARATION_AMBIGUOUS_NO_REQUEST"
    assert report["network_requests_made"] == 0
    assert spy.calls == []


@pytest.mark.parametrize(("field", "value", "code"), [
    ("source_url", "https://example.com/xml", "RECOVERY_SOURCE_URL_OR_FILENAME"),
    ("filename", "../other.xml", "RECOVERY_SOURCE_URL_OR_FILENAME"),
    ("source_kind", "protected", "RECOVERY_SOURCE_KIND"),
    ("expected_sha256", "0" * 63, "RECOVERY_SOURCE_PIN_INVALID"),
    ("expected_bytes", 0, "RECOVERY_SOURCE_PIN_INVALID"),
])
def test_source_index_attacker_controlled_fields_fail_before_io(
        tmp_path, field, value, code):
    index = fake_body_index(b"<article/>")
    index["records"][0][field] = value
    spy = StubOpener(b"not touched")
    with pytest.raises(vb.BenchmarkError, match=code):
        check(index, tmp_path, network_authorized=True, opener=spy)
    assert spy.calls == []


def test_protected_partition_and_source_manifest_substitution_refused(tmp_path):
    index = fake_body_index(b"<article/>")
    index["partition"] = "sealed_confirmatory"
    with pytest.raises(vb.BenchmarkError, match="RECOVERY_PROTECTED_DATA_FORBIDDEN"):
        check(index, tmp_path)
    index["partition"] = "exposed_development_historical_not_sealed"
    index["source_manifest"]["sha256"] = "0" * 64
    with pytest.raises(vb.BenchmarkError, match="RECOVERY_INDEX_ORIGIN_MISMATCH"):
        check(index, tmp_path)


def test_stale_external_sha_pin_refused_even_for_verifiable_cache(tmp_path):
    data = b"<article/>"
    index = fake_body_index(data)
    raw, _ = pinned(index)
    with pytest.raises(vb.BenchmarkError, match="RECOVERY_INDEX_EXTERNAL_PIN_MISMATCH"):
        recovery.recover(index, tmp_path, exact_index_bytes=raw,
                         expected_index_sha256="f" * 64)


def test_private_source_directory_cannot_be_the_public_checkout():
    index = fake_body_index(b"<article/>")
    raw, digest = pinned(index)
    with pytest.raises(vb.BenchmarkError, match="RECOVERY_SOURCE_INSIDE_CHECKOUT_FORBIDDEN"):
        recovery.recover(index, ROOT / "examples",
                         expected_index_sha256=digest, exact_index_bytes=raw)


def test_symlink_source_cannot_be_reclassified_as_verified(tmp_path):
    index = fake_body_index(b"<article/>")
    source = tmp_path / "PMC4339301.xml"
    outside = tmp_path / "outside.xml"
    outside.write_bytes(b"<article/>")
    try:
        source.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink unavailable")
    result = check(index, tmp_path)
    assert result["records"][0]["status"] == "EXISTING_SOURCE_UNSAFE_OR_UNREADABLE"


def test_actual_index_cli_audits_missing_records_offline_without_write(tmp_path):
    index_sha = sha256(INDEX_PATH.read_bytes()).hexdigest()
    args = [
        sys.executable, "-m", "tools.recover_legacy_europepmc_sources",
        "--index", str(INDEX_PATH),
        "--expected-index-sha256", index_sha,
        "--private-root", str(tmp_path),
    ]
    response = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=35)
    assert response.returncode == 1, response.stderr
    report = json.loads(response.stdout)
    assert report["selected_records"] == 13
    assert report["counts_by_status"] == {"SOURCE_MISSING_OFFLINE": 13}
    assert report["network_requests_made"] == 0
    assert not list(tmp_path.iterdir())
    failed = args[:]
    failed[failed.index("--expected-index-sha256") + 1] = "0" * 64
    invalid = subprocess.run(failed, cwd=ROOT, capture_output=True, timeout=35)
    assert invalid.returncode == 2
    assert json.loads(invalid.stderr)["code"] == "RECOVERY_INDEX_EXTERNAL_PIN_MISMATCH"
