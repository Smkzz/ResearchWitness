"""Offline adversarial tests for public-source discovery boundaries."""
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.request import ProxyHandler, Request

from tools.public_discovery import (
    InvalidSourceResponse,
    PublicSourceClient,
    SourceAccessError,
    SourceBoundaryError,
    _ApprovedRedirectHandler,
    _default_transport,
    _private_rate_state_directory,
    _reserve_shared_rate_slot,
    canonical_work_key,
    failed_search_record,
    invalid_response_search_record,
    merge_candidates,
    normalize_doi,
    normalize_pmcid,
    percentage_recalculation,
    search_crossref,
    search_europe_pmc,
    summarize_registry,
    registry_with_search,
    validate_source_url,
    validate_registry_document,
)
from tools.discover_public_candidates import main as discovery_cli_main


class FakeTransport:
    def __init__(self, bodies, *, final_url=None, status=200):
        self.bodies = list(bodies)
        self.final_url = final_url
        self.status = status
        self.calls = []

    def __call__(self, url, headers, timeout, max_bytes):
        self.calls.append((url, dict(headers), timeout, max_bytes))
        body = self.bodies.pop(0)
        return self.status, body, self.final_url or url


class PublicDiscoveryTests(unittest.TestCase):
    def client(self, transport, **kwargs):
        return PublicSourceClient(transport=transport, **kwargs)

    def test_exact_approved_https_hosts_are_required(self):
        self.assertEqual(validate_source_url("https://api.crossref.org/works"), "api.crossref.org")
        self.assertEqual(validate_source_url("https://www.ebi.ac.uk/europepmc/"), "www.ebi.ac.uk")
        for url in (
            "http://api.crossref.org/works",
            "https://api.crossref.org.publisher.example/works",
            "https://publisher.example/article",
            "https://user:secret@api.crossref.org/works",
            "https://api.crossref.org:8443/works",
        ):
            with self.subTest(url=url), self.assertRaises(SourceBoundaryError):
                validate_source_url(url)

    def test_allowed_cross_host_redirect_is_still_rejected(self):
        transport = FakeTransport(
            [b"{}"], final_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/"
        )
        with self.assertRaises(SourceBoundaryError):
            self.client(transport).get("https://www.ebi.ac.uk/europepmc/search")

    def test_redirect_handler_rejects_cross_host_targets_before_following(self):
        request = Request("https://www.ebi.ac.uk/europepmc/search")
        handler = _ApprovedRedirectHandler("www.ebi.ac.uk")
        for target in (
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
            "https://publisher.example/article",
        ):
            with self.subTest(target=target), self.assertRaises(SourceBoundaryError):
                handler.redirect_request(request, None, 302, "Found", {}, target)
        self.assertIsNotNone(handler.redirect_request(
            request, None, 302, "Found", {}, "https://www.ebi.ac.uk/europepmc/search2"
        ))

    def test_proxy_bypass_fails_before_opener_can_attempt_direct_access(self):
        with (
            patch("tools.public_discovery.getproxies", return_value={"https": "http://proxy:8080"}),
            patch("tools.public_discovery.proxy_bypass", return_value=True),
            patch("tools.public_discovery.build_opener") as build_opener,
        ):
            with self.assertRaises(SourceAccessError) as caught:
                _default_transport("https://www.ebi.ac.uk/europepmc/search", {}, 5, 1000)
        self.assertIn("excluded from the managed proxy", caught.exception.reason)
        self.assertFalse(build_opener.called)

    def test_generic_all_proxy_is_explicitly_mapped_to_https(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = "https://www.ebi.ac.uk/europepmc/search"
        response.read.return_value = b"{}"
        response.status = 200
        opener = MagicMock()
        opener.open.return_value = response
        with (
            patch("tools.public_discovery.getproxies", return_value={"all": "http://managed-proxy:8080"}),
            patch("tools.public_discovery.proxy_bypass", return_value=False),
            patch("tools.public_discovery.build_opener", return_value=opener) as build_opener,
        ):
            status, body, final_url = _default_transport(
                "https://www.ebi.ac.uk/europepmc/search", {}, 5, 1000
            )
        proxy_handler = next(
            handler for handler in build_opener.call_args.args
            if isinstance(handler, ProxyHandler)
        )
        self.assertEqual(proxy_handler.proxies["https"], "http://managed-proxy:8080")
        self.assertEqual((status, body), (200, b"{}"))
        self.assertEqual(final_url, "https://www.ebi.ac.uk/europepmc/search")

    def test_shared_host_rate_limit_survives_new_client_instances(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "host.lock"
            now = [100.0]
            slept = []

            def sleep(seconds):
                slept.append(seconds)
                now[0] += seconds

            wall_clock = lambda: now[0]
            _reserve_shared_rate_slot(
                "www.ebi.ac.uk", 1.0, sleep,
                state_path=state_path, wall_clock=wall_clock,
            )
            now[0] += 0.25
            _reserve_shared_rate_slot(
                "www.ebi.ac.uk", 1.0, sleep,
                state_path=state_path, wall_clock=wall_clock,
            )
        self.assertEqual(slept, [0.75])

    @unittest.skipUnless(hasattr(os, "getuid"), "POSIX ownership and permission checks")
    def test_rate_state_directory_rejects_shared_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = _private_rate_state_directory(Path(temp_dir))
            os.chmod(directory, 0o755)
            with self.assertRaises(SourceAccessError):
                _private_rate_state_directory(Path(temp_dir))

    @unittest.skipUnless(hasattr(os, "getuid"), "POSIX ownership and permission checks")
    def test_rate_state_file_rejects_group_or_world_access(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "host.lock"
            state_path.write_text("", encoding="ascii")
            os.chmod(state_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
            with self.assertRaises(SourceAccessError):
                _reserve_shared_rate_slot("www.ebi.ac.uk", 1.0, lambda _seconds: None, state_path=state_path)

    def test_non_success_and_oversized_responses_fail_closed(self):
        with self.assertRaises(SourceAccessError):
            self.client(FakeTransport([b"{}"], status=429)).get("https://api.crossref.org/works")
        with self.assertRaises(SourceAccessError):
            self.client(FakeTransport([b"12345"]), max_response_bytes=4).get(
                "https://api.crossref.org/works"
            )

    def test_failed_search_record_never_claims_a_response_or_zero_hits(self):
        record = failed_search_record(
            "europe_pmc",
            "TITLE:correction",
            SourceAccessError("www.ebi.ac.uk", "managed transport or proxy unavailable"),
        )
        self.assertEqual(record["status"], "transport_failed_before_http_response")
        self.assertIsNone(record["response_sha256"])
        self.assertIsNone(record["record_count"])
        self.assertEqual(record["failure_code"], "TRANSPORT_UNAVAILABLE")

    def test_http_denials_and_provider_errors_have_distinct_statuses(self):
        denied = failed_search_record(
            "crossref", "example", SourceAccessError("api.crossref.org", "provider returned an error", 429)
        )
        provider_error = failed_search_record(
            "crossref", "example", SourceAccessError("api.crossref.org", "provider returned an error", 503)
        )
        self.assertEqual(denied["status"], "blocked")
        self.assertEqual(provider_error["status"], "provider_error")
        self.assertIsNone(provider_error["response_sha256"])
        validate_registry_document(registry_with_search([], [denied, provider_error]))

    def test_per_host_delay_is_applied(self):
        now = [10.0]
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            now[0] += seconds

        transport = FakeTransport([b"{}", b"{}"])
        client = self.client(transport, monotonic=lambda: now[0], sleep=sleep)
        client.get("https://api.crossref.org/works")
        client.get("https://api.crossref.org/works?rows=1")
        self.assertEqual(slept, [1.0])
        self.assertEqual(len(transport.calls), 2)

    def test_doi_and_pmcid_aliases_normalize_without_merging_unknown_aliases(self):
        self.assertEqual(normalize_doi(" DOI:10.1234/AbC.1 "), "10.1234/abc.1")
        self.assertEqual(normalize_doi("https://doi.org/10.1234/AbC.1"), "10.1234/abc.1")
        self.assertEqual(normalize_pmcid("pmc012345"), "PMC012345")
        self.assertIsNone(normalize_pmcid("PMID:12345"))
        self.assertEqual(canonical_work_key({"doi": "10.1234/a", "pmcid": "PMC10"}), "doi:10.1234/a")
        self.assertNotEqual(
            canonical_work_key({"doi": "10.1234/a"}),
            canonical_work_key({"doi": "10.1234/b"}),
        )

    def test_ratio_math_matches_v1_3_round_half_up_at_display_precision(self):
        tie = percentage_recalculation(1, 32, "3.13", 2)
        self.assertEqual(tie["rounded_percent"], "3.13")
        self.assertTrue(tie["arithmetic_matches"])
        non_tie = percentage_recalculation(1, 6, "16.7", 1)
        self.assertEqual(non_tie["exact_ratio_percent"], "100/6")
        self.assertEqual(non_tie["rounded_percent"], "16.7")
        self.assertTrue(non_tie["arithmetic_matches"])
        self.assertFalse(percentage_recalculation(1, 6, "16.6", 1)["arithmetic_matches"])

    def test_ratio_math_rejects_ambiguous_or_invalid_operands(self):
        for args in (
            (0, 0, "0", 0),
            (4, 3, "133.3", 1),
            (-1, 3, "-33.3", 1),
            (1, 3, "33.30", 1),
            (1, 3, "33.3", 7),
            (1_000_000_000, 1_000_000_000, "100", 0),
            (True, 1, "100", 0),
            (1, 3, 33.3, 1),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                percentage_recalculation(*args)

    def test_europe_pmc_search_hashes_response_and_never_marks_evidence_accepted(self):
        payload = {
            "hitCount": 1,
            "resultList": {"result": [{
                "title": "Correction: Example counts",
                "doi": "10.1234/Example",
                "pmcid": "PMC987",
                "pmid": "12345",
                "license": "cc by",
                "isOpenAccess": "Y",
            }]},
        }
        body = json.dumps(payload).encode()
        transport = FakeTransport([body])
        candidates, search = search_europe_pmc(self.client(transport), "TITLE:correction", 5)
        self.assertEqual(search["response_sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(search["record_count"], 1)
        candidate = candidates[0]
        self.assertEqual(candidate["candidate_kinds"], ["correction_notice"])
        self.assertEqual(candidate["exposure_status"], "developer_exposed")
        self.assertFalse(candidate["holdout_eligible"])
        self.assertIsNone(candidate["correction_source"]["content_sha256"])
        self.assertEqual(candidate["independent_review_status"], "not_started")

    def test_crossref_and_europe_pmc_records_deduplicate_on_shared_identifiers(self):
        crossref = {
            "message": {"items": [{
                "DOI": "10.1234/example",
                "title": ["Erratum to: Example table"],
                "type": "journal-article",
                "relation": {},
            }]}
        }
        pmc = {
            "resultList": {"result": [{
                "title": "Erratum to: Example table",
                "doi": "https://doi.org/10.1234/EXAMPLE",
                "pmcid": "PMC444",
            }]}
        }
        cr_candidates, cr_search = search_crossref(
            self.client(FakeTransport([json.dumps(crossref).encode()])), "erratum", 2
        )
        pmc_candidates, pmc_search = search_europe_pmc(
            self.client(FakeTransport([json.dumps(pmc).encode()])), "TITLE:erratum", 2
        )
        merged = merge_candidates(cr_candidates, pmc_candidates)
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0]["candidate_kinds"]), {"correction_notice"})
        self.assertEqual(len(merged[0]["source_records"]), 2)
        registry = registry_with_search(merged, [cr_search, pmc_search])
        summary = summarize_registry(registry)
        self.assertEqual(summary["correction_notice_candidates"], 1)
        self.assertEqual(summary["independently_accepted_positives_in_this_registry"], 0)
        self.assertEqual(summary["untouched_holdout_cases_in_this_registry"], 0)

    def test_identifier_overlap_merges_lower_priority_alias_without_dropping_provenance(self):
        crossref = {"message": {"items": [{
            "DOI": "10.1234/example", "title": ["Example"], "pmcid": "PMC444",
        }]}}
        europe = {"resultList": {"result": [{
            "title": "Example", "pmcid": "PMC444",
        }]}}
        cr_candidates, _ = search_crossref(
            self.client(FakeTransport([json.dumps(crossref).encode()])), "example", 2
        )
        ebi_candidates, _ = search_europe_pmc(
            self.client(FakeTransport([json.dumps(europe).encode()])), "example", 2
        )
        merged = merge_candidates(cr_candidates, ebi_candidates)
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]["source_records"]), 2)
        self.assertEqual(
            {record["record_ordinal"] for record in merged[0]["source_records"]}, {1}
        )
        self.assertIn("10.1234/example", [
            record["reported_identifiers"]["doi"]
            for record in merged[0]["source_records"]
        ])

    def test_conflicting_dois_sharing_a_pmcid_remain_separate_and_marked_unresolved(self):
        crossref = {"message": {"items": [{
            "DOI": "10.1234/first", "title": ["Example"], "pmcid": "PMC444",
        }]}}
        europe = {"resultList": {"result": [{
            "title": "Example", "doi": "10.1234/second", "pmcid": "PMC444",
        }]}}
        cr_candidates, _ = search_crossref(
            self.client(FakeTransport([json.dumps(crossref).encode()])), "example", 2
        )
        ebi_candidates, _ = search_europe_pmc(
            self.client(FakeTransport([json.dumps(europe).encode()])), "example", 2
        )
        merged = merge_candidates(cr_candidates, ebi_candidates)
        self.assertEqual(len(merged), 2)
        self.assertTrue(all(item["work_family"]["duplicate_relationships"] for item in merged))

    def test_identifierless_bridge_does_not_join_conflicting_doi_families(self):
        crossref = {"message": {"items": [
            {"DOI": "10.1234/first", "title": ["Example"], "pmcid": "PMC444"},
            {"DOI": "10.1234/second", "title": ["Example"], "pmcid": "PMC444"},
        ]}}
        europe = {"resultList": {"result": [{
            "title": "Example", "pmcid": "PMC444",
        }]}}
        cr_candidates, _ = search_crossref(
            self.client(FakeTransport([json.dumps(crossref).encode()])), "example", 5
        )
        ebi_candidates, _ = search_europe_pmc(
            self.client(FakeTransport([json.dumps(europe).encode()])), "example", 5
        )
        merged = merge_candidates(cr_candidates, ebi_candidates)
        self.assertEqual(len(merged), 3)
        self.assertTrue(all(item["work_family"]["duplicate_relationships"] for item in merged))

    def test_identifierless_bridge_across_pmcid_and_pmid_stays_unresolved(self):
        crossref = {"message": {"items": [
            {"DOI": "10.1234/first", "title": ["Example"], "pmcid": "PMC444"},
            {"DOI": "10.1234/second", "title": ["Example"], "pmid": "222"},
        ]}}
        europe = {"resultList": {"result": [{
            "title": "Example", "pmcid": "PMC444", "pmid": "222",
        }]}}
        cr_candidates, _ = search_crossref(
            self.client(FakeTransport([json.dumps(crossref).encode()])), "example", 5
        )
        ebi_candidates, _ = search_europe_pmc(
            self.client(FakeTransport([json.dumps(europe).encode()])), "example", 5
        )
        merged = merge_candidates(cr_candidates, ebi_candidates)
        self.assertEqual(len(merged), 3)
        self.assertTrue(all(item["work_family"]["duplicate_relationships"] for item in merged))

    def test_identifierless_duplicate_titles_keep_distinct_record_identities(self):
        payload = {"resultList": {"result": [
            {"title": "Same title"}, {"title": "Same title"},
        ]}}
        candidates, _ = search_europe_pmc(
            self.client(FakeTransport([json.dumps(payload).encode()])), "same title", 5
        )
        self.assertEqual(len(candidates), 2)
        self.assertNotEqual(candidates[0]["candidate_id"], candidates[1]["candidate_id"])
        self.assertEqual(len(merge_candidates(candidates)), 2)

    def test_malformed_provider_responses_are_invalid_not_zero_hit_searches(self):
        malformed = (
            ("europe_pmc", {}, search_europe_pmc),
            ("europe_pmc", {"resultList": {"result": [None]}}, search_europe_pmc),
            ("crossref", {"message": {"items": [None]}}, search_crossref),
        )
        for provider, payload, search in malformed:
            with self.subTest(provider=provider, payload=payload):
                body = json.dumps(payload).encode()
                with self.assertRaises(InvalidSourceResponse) as caught:
                    search(self.client(FakeTransport([body])), "example", 5)
                record = invalid_response_search_record(provider, "example", caught.exception)
                registry = registry_with_search([], [record], updated_utc="2026-10-14T00:00:00Z")
                validate_registry_document(registry)
                self.assertEqual(record["status"], "invalid_response")
                self.assertEqual(record["response_sha256"], hashlib.sha256(body).hexdigest())
                self.assertIsNone(record["record_count"])
                summary = summarize_registry(registry)
                self.assertEqual(summary["workflow_status"], "incomplete")
                self.assertFalse(summary["all_recorded_search_responses_valid"])

    def test_deeply_nested_json_is_recorded_as_invalid_response(self):
        body = b"[" * 1100 + b"0" + b"]" * 1100
        with self.assertRaises(InvalidSourceResponse) as caught:
            search_europe_pmc(self.client(FakeTransport([body])), "example", 5)
        record = invalid_response_search_record("europe_pmc", "example", caught.exception)
        self.assertEqual(record["status"], "invalid_response")
        self.assertEqual(record["response_sha256"], hashlib.sha256(body).hexdigest())
        self.assertIsNone(record["record_count"])

    def test_registry_validation_rejects_missing_nested_fields_and_status_mismatch(self):
        payload = {"resultList": {"result": [{
            "title": "Example", "doi": "10.1234/example",
        }]}}
        candidates, search = search_europe_pmc(
            self.client(FakeTransport([json.dumps(payload).encode()])), "example", 2
        )
        registry = registry_with_search(candidates, [search], updated_utc="2026-10-14T00:00:00Z")
        with_missing_top_field = deepcopy(registry)
        del with_missing_top_field["updated_utc"]
        with self.assertRaises(ValueError):
            validate_registry_document(with_missing_top_field)
        with_missing_nested_field = deepcopy(registry)
        del with_missing_nested_field["candidates"][0]["source_records"][0]["response_sha256"]
        with self.assertRaises(ValueError):
            validate_registry_document(with_missing_nested_field)
        inconsistent = deepcopy(registry)
        inconsistent["workflow_status"] = "incomplete"
        with self.assertRaises(ValueError):
            validate_registry_document(inconsistent)
        completed_with_failure = deepcopy(registry)
        completed_with_failure["searches"][0] = failed_search_record(
            "europe_pmc", "example", SourceAccessError("www.ebi.ac.uk", "transport unavailable")
        )
        with self.assertRaises(ValueError):
            validate_registry_document(completed_with_failure)

    def test_reproduced_relationship_requires_captured_hashed_sources(self):
        payload = {"resultList": {"result": [{"title": "Example", "doi": "10.1234/example"}]}}
        candidates, search = search_europe_pmc(
            self.client(FakeTransport([json.dumps(payload).encode()])), "example", 2
        )
        registry = registry_with_search(candidates, [search], updated_utc="2026-10-14T00:00:00Z")
        candidate = registry["candidates"][0]
        candidate["candidate_kinds"] = ["ratio_relationship"]
        candidate["mathematical_relationship"] = {
            "status": "reproduced", "numerator": "3", "denominator": "7",
            "reported_percent": "42.9", "corrected_values": None, "scope": "same cohort",
        }
        candidate["original_source"] = {
            "identifier": "PMCID:PMC123", "version": "published-v1",
            "content_sha256": "a" * 64, "retrieval_status": "captured", "license_status": "allowed",
        }
        validate_registry_document(registry)

        without_source_hash = deepcopy(registry)
        without_source_hash["candidates"][0]["original_source"]["content_sha256"] = None
        with self.assertRaises(ValueError):
            validate_registry_document(without_source_hash)
        without_values = deepcopy(registry)
        without_values["candidates"][0]["mathematical_relationship"]["numerator"] = None
        with self.assertRaises(ValueError):
            validate_registry_document(without_values)

    def test_reproduced_correction_candidate_requires_correction_source(self):
        payload = {"resultList": {"result": [{"title": "Correction: Example", "doi": "10.1234/example"}]}}
        candidates, search = search_europe_pmc(
            self.client(FakeTransport([json.dumps(payload).encode()])), "correction", 2
        )
        registry = registry_with_search(candidates, [search], updated_utc="2026-10-14T00:00:00Z")
        candidate = registry["candidates"][0]
        candidate["mathematical_relationship"] = {
            "status": "reproduced", "numerator": "3", "denominator": "7",
            "reported_percent": "42.9", "corrected_values": {"corrected_percent": "42.8"}, "scope": "same cohort",
        }
        candidate["original_source"] = {
            "identifier": "PMCID:PMC123", "version": "published-v1",
            "content_sha256": "a" * 64, "retrieval_status": "captured", "license_status": "allowed",
        }
        candidate["correction_source"] = {
            "identifier": "PMCID:PMC124", "version": "corrigendum-v1",
            "content_sha256": "b" * 64, "retrieval_status": "captured", "license_status": "allowed",
        }
        validate_registry_document(registry)
        missing_correction = deepcopy(registry)
        missing_correction["candidates"][0]["correction_source"] = None
        with self.assertRaises(ValueError):
            validate_registry_document(missing_correction)
        missing_corrected_value = deepcopy(registry)
        missing_corrected_value["candidates"][0]["mathematical_relationship"]["corrected_values"] = None
        with self.assertRaises(ValueError):
            validate_registry_document(missing_corrected_value)

    def test_cli_persists_invalid_response_hash_without_reporting_zero_hits(self):
        body = b'{"resultList": {"result": [null]}}'
        response = {
            "url": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=example",
            "host": "www.ebi.ac.uk",
            "retrieved_at_utc": "2026-10-14T00:00:00Z",
            "sha256": hashlib.sha256(body).hexdigest(),
            "byte_count": len(body),
            "body": body,
        }
        invalid = InvalidSourceResponse("europe_pmc", response, "result row was not an object")
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "candidate-registry.json"
            stderr = io.StringIO()
            with (
                patch("tools.discover_public_candidates.PublicSourceClient", return_value=object()),
                patch("tools.discover_public_candidates.search_europe_pmc", side_effect=invalid),
                redirect_stderr(stderr),
            ):
                result = discovery_cli_main([
                    "discover", "--provider", "europe-pmc", "--query", "example",
                    "--output", str(output),
                ])
            registry = json.loads(output.read_text(encoding="utf-8"))
        validate_registry_document(registry)
        self.assertEqual(result, 3)
        self.assertEqual(registry["workflow_status"], "incomplete")
        self.assertEqual(registry["searches"][0]["response_sha256"], hashlib.sha256(body).hexdigest())
        self.assertIsNone(registry["searches"][0]["record_count"])
        self.assertEqual(registry["candidates"], [])
        self.assertIn('"status": "invalid_response"', stderr.getvalue())

    def test_registry_rejects_holdout_relabeling_and_unapproved_fields(self):
        payload = {"resultList": {"result": [{
            "title": "Correction: Example counts", "doi": "10.1234/example",
        }]}}
        candidates, search = search_europe_pmc(
            self.client(FakeTransport([json.dumps(payload).encode()])), "TITLE:correction", 2
        )
        registry = {
            "schema_version": 1,
            "updated_utc": "2026-10-14T00:00:00Z",
            "workflow_status": "completed",
            "scope": "developer_exposed_public_source_candidates_only",
            "searches": [search],
            "candidates": candidates,
        }
        validate_registry_document(registry)
        relabeled = deepcopy(registry)
        relabeled["candidates"][0]["holdout_eligible"] = True
        with self.assertRaises(ValueError):
            validate_registry_document(relabeled)
        with_reserved_label = deepcopy(registry)
        with_reserved_label["candidates"][0]["reserved_label"] = "positive"
        with self.assertRaises(ValueError):
            validate_registry_document(with_reserved_label)
        wrong_host = deepcopy(registry)
        wrong_host["searches"][0]["host"] = "publisher.example"
        with self.assertRaises(ValueError):
            validate_registry_document(wrong_host)


if __name__ == "__main__":
    unittest.main()
