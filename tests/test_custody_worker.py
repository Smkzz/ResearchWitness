"""Synthetic-only regression suite for the v5 offline custody contract."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator

from custody_worker.cli import main
from custody_worker.policy import (
    CustodyError, DEV_PARENT, MARKER, IMPORT_VERSION, REVIEW_VERSION,
    canonical_bytes, computed_percent, normalize_doi, preflight, sha256_bytes,
    validate_source_provenance, validate_utc_timestamp,
)
from custody_worker.store import (
    import_batch, make_store, record_review, verify_all, seal_inventory,
    summarize, export_public_summary, SCOPE_STATUS, SOURCE_VERSION_STATUS,
    CORRECTION_STATUS, _review_validation, _source_index,
)

DOCUMENT = "doi:10.5555/synthetic-study"
CORRECTION_ID = "doi:10.5555/synthetic-correction"


def span(text: str, needle: str, *, base: int = 0, occurrence: int = 0) -> dict:
    encoded = text.encode("utf-8")
    token = needle.encode("utf-8")
    start_local = -1
    cursor = 0
    for _ in range(occurrence + 1):
        start_local = encoded.find(token, cursor)
        if start_local < 0:
            raise AssertionError(f"missing synthetic token: {needle}")
        cursor = start_local + len(token)
    start = base + start_local
    return {"start": start, "end": start + len(token), "text": needle}


def relation(source_text: str, group: str, percentage: str, *, line_number: int = 0,
             numerator: str = "2", denominator: str = "N = 7",
             table_locator: str = "Table 1", numerator_occurrence: int = 0) -> dict:
    lines = source_text.splitlines(keepends=True)
    base = sum(len(line.encode("utf-8")) for line in lines[:line_number])
    line = lines[line_number].rstrip("\r\n")
    return {
        "table_locator_span": span(line, table_locator, base=base),
        "object_locator_span": span(line, group, base=base),
        "context_span": span(line, line, base=base),
        "numerator_span": span(line, numerator, base=base, occurrence=numerator_occurrence),
        "denominator_span": span(line, denominator, base=base),
        "percentage_span": span(line, percentage, base=base),
        "scope_span": span(line, f"{group} / main cohort", base=base),
        "scope_status": SCOPE_STATUS,
    }


def integer_rounding_oracle(numerator: int, denominator: int, places: int) -> str:
    """Independent integer-only reference for nonnegative HALF_UP percent rounding."""
    scale = 10 ** places
    quotient, remainder = divmod(numerator * 100 * scale, denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    if places == 0:
        return str(quotient)
    whole, fraction = divmod(quotient, scale)
    return f"{whole}.{fraction:0{places}d}"


class CustodyWorkerV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DEV_PARENT.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.root = DEV_PARENT / ("rw-v5-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        (self.root / ".synthetic-only").write_text(MARKER, encoding="ascii")
        self.assertEqual(preflight(dev_root=self.root), self.root)
        make_store(self.root)

    def tearDown(self):
        shutil.rmtree(self.root)

    def source_setup(self, *, original: str, correction: str | None = None,
                     document_id: str = DOCUMENT, source_version: str = "v1",
                     correction_document_id: str | None = None,
                     extension: str = "txt"):
        original_bytes = original.encode("utf-8")
        original_name = "original." + extension
        original_item = {
            "name": original_name, "role": "original", "size": len(original_bytes),
            "sha256": sha256_bytes(original_bytes), "document_id": document_id,
            "source_id": document_id, "source_version": source_version,
            "provenance": self.synthetic_provenance("original"),
        }
        (self.root / "incoming" / original_name).write_bytes(original_bytes)
        files = [original_item]
        correction_item = None
        if correction is not None:
            correction_bytes = correction.encode("utf-8")
            correction_item = {
                "name": "correction.txt", "role": "correction",
                "size": len(correction_bytes), "sha256": sha256_bytes(correction_bytes),
                "document_id": correction_document_id or document_id,
                "source_id": CORRECTION_ID, "source_version": "corr-1",
                "provenance": self.synthetic_provenance("correction"),
            }
            (self.root / "incoming" / correction_item["name"]).write_bytes(correction_bytes)
            files.append(correction_item)
        manifest = {
            "schema_version": IMPORT_VERSION,
            "batch_id": "synthetic-batch-" + uuid.uuid4().hex[:8],
            "files": files,
        }
        (self.root / "incoming" / (manifest["batch_id"] + ".json")).write_bytes(canonical_bytes(manifest))
        result = import_batch(self.root, manifest["batch_id"])
        self.assertEqual(result["status"], "IMPORTED")
        return original_item, correction_item

    @staticmethod
    def synthetic_provenance(name: str) -> dict:
        return {
            "method": "SYNTHETIC_FIXTURE",
            "source_url": f"synthetic://fixture/{name}",
            "retrieved_at_utc": "2026-10-09T00:00:00Z",
            "license_notice": "Synthetic fixture; no external source was retrieved.",
            "public_use_status": "NOT_APPLICABLE_SYNTHETIC",
        }

    @staticmethod
    def original_text(percent: str = "28.6%", group: str = "Group A") -> str:
        return f"Table 1 / {group} / main cohort / N = 7 / count 2 / {percent}\n"

    @staticmethod
    def correction_text(percent: str = "28.6%", old: str = "28.5%",
                       group: str = "Group A", table_locator: str = "Table 1") -> str:
        return (
            f"Correction {table_locator} / {group} / main cohort / N = 7 / "
            f"count 2 / {percent} instead of {old}\n"
        )

    def review_object(self, original_item: dict, correction_item: dict | None, *,
                      review_id: str = "review-one", role: str = "CORRECT_NEGATIVE_RELATION",
                      original_text: str | None = None, correction_text: str | None = None,
                      eligibility: str = "ELIGIBLE", group: str = "Group A",
                      original_percent: str = "28.6%", corrected_percent: str = "28.6%",
                      old_percent: str = "28.5%", correction_old_percent: str | None = None,
                      correction_numerator: str = "2", correction_denominator: str = "N = 7",
                      numerator: str = "2", denominator: str = "N = 7",
                      table_locator: str = "Table 1",
                      numerator_occurrence: int = 0,
                      corrected_group: str | None = None,
                      changed_fields: list[str] | None = None, scope_status: str = SCOPE_STATUS,
                      line_number: int = 0):
        original_text = original_text if original_text is not None else self.original_text(original_percent, group)
        source_relation = relation(
            original_text, group, original_percent, line_number=line_number,
            numerator=numerator, denominator=denominator, table_locator=table_locator,
            numerator_occurrence=numerator_occurrence,
        )
        source_relation["scope_status"] = scope_status
        correction_binding = None
        if role == "CORRECTION_POSITIVE":
            if correction_item is None or correction_text is None:
                raise AssertionError("positive fixture needs a correction source")
            correction_relation = relation(
                correction_text, corrected_group or group, corrected_percent,
                numerator=correction_numerator, denominator=correction_denominator,
                table_locator=table_locator,
            )
            correction_relation["scope_status"] = SCOPE_STATUS
            correction_old_percent = correction_old_percent or old_percent
            correction_line = correction_text.rstrip("\r\n")
            old_token_occurrence = (
                1 if correction_old_percent == corrected_percent
                and correction_text.count(correction_old_percent) > 1 else 0
            )
            correction_binding = {
                "statement_span": span(correction_text, correction_line),
                "corrected_relation": correction_relation,
                "old_value_spans": {
                    "percentage": span(correction_text, correction_old_percent,
                                        occurrence=old_token_occurrence),
                },
                "changed_fields": changed_fields or ["percentage"],
                "mapping_status": CORRECTION_STATUS,
            }
        return {
            "schema_version": REVIEW_VERSION,
            "review_id": review_id,
            "role": role,
            "eligibility": eligibility,
            "document_id": original_item["document_id"],
            "source_sha256": original_item["sha256"],
            "source_version": original_item["source_version"],
            "correction_sha256": correction_item["sha256"] if correction_item else None,
            "correction_source_version": correction_item["source_version"] if correction_item else None,
            "source_version_status": SOURCE_VERSION_STATUS,
            "relationship": source_relation,
            "correction_binding": correction_binding,
            "objections": [],
        }

    def write_review(self, review: dict):
        path = self.root / "incoming" / (review["review_id"] + ".json")
        path.write_bytes(canonical_bytes(review))

    def record(self, review: dict):
        self.write_review(review)
        return record_review(self.root, review["review_id"])

    def write_v4_record(self, review: dict):
        _, details = _review_validation(review, self.root, _source_index(self.root))
        record = {
            "schema_version": "rw-custody-review-record/4",
            "review": review,
            "checked": {
                "original_arithmetic": details["original_arithmetic"],
                "corrected_arithmetic": details["corrected_arithmetic"],
                "relationship_key": details["legacy_relationship_key"],
            },
            "recorded_by": "SYNTHETIC_DEVELOPMENT",
            "recorded_at_utc": "2026-10-09T00:00:00Z",
        }
        path = self.root / "manifests" / "reviews" / (review["review_id"] + ".json")
        path.write_bytes(canonical_bytes(record))
        return path

    def test_doi_normalization_is_stable_and_rejects_arbitrary_paper_labels(self):
        self.assertEqual(normalize_doi("https://doi.org/10.5555/Synthetic-Study"), DOCUMENT)
        self.assertEqual(normalize_doi("DOI:10.5555/Synthetic-Study"), DOCUMENT)
        with self.assertRaisesRegex(CustodyError, "CANONICAL_DOI_REQUIRED"):
            normalize_doi("synthetic:paper-1")

    def test_decimal_percentage_matches_an_independent_integer_rounding_oracle(self):
        cases = [
            (0, 7, 0, "0"),
            (1, 800, 2, "0.13"),
            (1, 800, 2, "0.12"),
            (1, 6, 1, "16.7"),
            (2, 7, 1, "28.6"),
            (999, 1000, 1, "99.9"),
            (1, 3, 2, "33.33"),
        ]
        for numerator, denominator, places, printed in cases:
            expected = integer_rounding_oracle(numerator, denominator, places)
            result = computed_percent(numerator, denominator, printed, places)
            self.assertEqual(result["recomputed"], expected)
            self.assertEqual(result["matches"], printed == expected)
        with self.assertRaisesRegex(CustodyError, "INVALID_INTEGER"):
            computed_percent(0, 0, "0", 0)
        with self.assertRaisesRegex(CustodyError, "PRINTED_PRECISION_MISMATCH"):
            computed_percent(1, 8, "12.50", 1)

    def test_source_provenance_accepts_only_the_approved_public_hosts(self):
        valid = {
            "method": "APPROVED_PUBLIC_PROVIDER",
            "source_url": "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC123/fullTextXML",
            "retrieved_at_utc": "2026-10-09T12:00:00Z",
            "license_notice": "CC BY 4.0",
            "public_use_status": "CUSTODIAN_CONFIRMED_PUBLIC_USE",
        }
        self.assertEqual(validate_source_provenance(valid, synthetic_only=False), valid)
        invalid = dict(valid, source_url="https://publisher.example/article")
        with self.assertRaisesRegex(CustodyError, "SOURCE_HOST_NOT_APPROVED"):
            validate_source_provenance(invalid, synthetic_only=False)
        handoff = dict(valid, method="HASH_PINNED_HANDOFF")
        self.assertEqual(validate_source_provenance(handoff, synthetic_only=False), handoff)

    def test_synthetic_store_rejects_real_provider_provenance(self):
        source = {
            "method": "APPROVED_PUBLIC_PROVIDER",
            "source_url": "https://api.crossref.org/works/10.5555/example",
            "retrieved_at_utc": "2026-10-09T12:00:00Z",
            "license_notice": "Metadata only",
            "public_use_status": "CUSTODIAN_CONFIRMED_PUBLIC_USE",
        }
        with self.assertRaisesRegex(CustodyError, "REAL_SOURCE_FORBIDDEN_IN_SYNTHETIC_MODE"):
            validate_source_provenance(source, synthetic_only=True)

    def test_direct_storage_apis_require_marked_synthetic_root(self):
        unmarked = DEV_PARENT / ("rw-unmarked-" + uuid.uuid4().hex)
        unmarked.mkdir()
        try:
            with self.assertRaises(CustodyError):
                make_store(unmarked)
        finally:
            unmarked.rmdir()
        with self.assertRaises(CustodyError):
            verify_all(Path(tempfile.gettempdir()) / "not-a-custody-store")

    def test_version_one_manifests_are_not_silently_upgraded(self):
        manifest = {
            "schema_version": "rw-custody-import/1",
            "batch_id": "synthetic-batch-old",
            "files": [],
        }
        path = self.root / "incoming" / "synthetic-batch-old.json"
        path.write_bytes(canonical_bytes(manifest))
        with self.assertRaisesRegex(CustodyError, "UNSUPPORTED_MANIFEST_VERSION"):
            import_batch(self.root, "synthetic-batch-old")

    def test_substituted_percentage_text_fails_exact_source_span_binding(self):
        original = self.original_text("28.5%")
        original_item, _ = self.source_setup(original=original)
        review = self.review_object(
            original_item, None, original_text=original, role="CORRECT_NEGATIVE_RELATION",
            original_percent="28.5%",
        )
        review["relationship"]["percentage_span"]["text"] = "28.6%"
        with self.assertRaisesRegex(CustodyError, "SOURCE_SPAN_MISMATCH"):
            self.record(review)

    def test_table_identifier_digit_cannot_be_borrowed_as_a_positive_numerator(self):
        original = "Table 2 / Group A / main cohort / N = 7 / 28.5%\n"
        correction = "Correction Table 2 / Group A / main cohort / N = 7 / 28.6% instead of 28.5%\n"
        original_item, correction_item = self.source_setup(original=original, correction=correction)
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction,
            original_percent="28.5%", corrected_percent="28.6%",
            old_percent="28.5%", table_locator="Table 2",
        )
        with self.assertRaisesRegex(CustodyError, "TABLE_LOCATOR_OVERLAPS_RELATION_VALUE"):
            self.record(review)

    def test_eligible_numerator_requires_a_literal_count_field_cue(self):
        original = "Table 1 / Group A / main cohort / N = 7 / 2 / 28.6%\n"
        original_item, _ = self.source_setup(original=original)
        review = self.review_object(
            original_item, None, original_text=original, original_percent="28.6%",
        )
        with self.assertRaisesRegex(CustodyError, "NUMERATOR_COUNT_CUE_NOT_EXPLICIT"):
            self.record(review)

    def test_cross_row_operands_are_rejected_even_when_the_fraction_matches(self):
        first = "Table 1 / Group A / main cohort / N = 7 / count 2 / 28.6%\n"
        second = "Table 2 / Group B / main cohort / N = 7 / count 2 / 28.6%\n"
        original = first + second
        original_item, _ = self.source_setup(original=original)
        review = self.review_object(
            original_item, None, original_text=original, original_percent="28.6%",
        )
        offset = len(first.encode("utf-8"))
        review["relationship"]["context_span"] = span(original, original.rstrip("\n"))
        review["relationship"]["numerator_span"] = span(original, "2", base=offset)
        review["relationship"]["table_locator_span"] = span(original, "Table 1")
        review["relationship"]["object_locator_span"] = span(original, "Group A")
        review["relationship"]["scope_span"] = span(original, "Group A / main cohort")
        with self.assertRaisesRegex(CustodyError, "RELATION_CONTEXT_NOT_EXACT_SOURCE_LINE"):
            self.record(review)

    def test_second_same_line_relation_cannot_be_hidden_in_the_context(self):
        original = (
            "Table 1 / Group A / main cohort / N = 7 / count 2 / 28.6% ; "
            "Table 2 / Group B / main cohort / N = 7 / count 2 / 28.6%\n"
        )
        original_item, _ = self.source_setup(original=original)
        review = self.review_object(
            original_item, None, original_text=original, original_percent="28.6%",
        )
        with self.assertRaisesRegex(CustodyError, "SOURCE_RELATION_HAS_UNMAPPED_NUMERIC_VALUE"):
            self.record(review)

    def test_correction_values_cannot_be_borrowed_from_another_line(self):
        original = self.original_text("28.5%")
        correction = (
            "Correction Table 1 / Group A / main cohort / N = 7 / count 2 / 28.6%\n"
            "Unrelated statement: instead of 28.5%\n"
        )
        original_item, correction_item = self.source_setup(original=original, correction=correction)
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction, original_percent="28.5%",
            corrected_percent="28.6%", old_percent="28.5%",
        )
        review["correction_binding"]["statement_span"] = span(correction, correction.rstrip("\n"))
        with self.assertRaisesRegex(CustodyError, "CORRECTION_STATEMENT_NOT_EXACT_SOURCE_LINE"):
            self.record(review)

    def test_unrelated_anchor_strings_cannot_qualify_a_negative(self):
        original = self.original_text("28.6%")
        original_item, _ = self.source_setup(original=original)
        review = self.review_object(original_item, None, original_text=original)
        review["relationship"]["scope_span"] = {"start": 0, "end": 9, "text": "fictional"}
        with self.assertRaisesRegex(CustodyError, "SOURCE_SPAN_MISMATCH"):
            self.record(review)

    def test_source_bound_correct_negative_is_counted_once(self):
        original = self.original_text("28.6%")
        original_item, _ = self.source_setup(original=original)
        review = self.review_object(original_item, None, original_text=original)
        self.assertEqual(self.record(review), {"status": "RECORDED"})
        counts = verify_all(self.root)
        self.assertEqual(counts["eligible_negative_relations"], 1)
        self.assertEqual(counts["eligible_negative_document_ids"], 1)
        self.assertEqual(counts["eligible_negative_tables"], 1)
        record_path = self.root / "manifests" / "reviews" / "review-one.json"
        stored = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["recorded_by"], "SYNTHETIC_DEVELOPMENT")
        validate_utc_timestamp(stored["recorded_at_utc"])
        import jsonschema
        from referencing import Registry, Resource
        schema_dir = Path(__file__).parents[1] / "custody_worker" / "schemas"
        review_schema = json.loads((schema_dir / "review.v5.schema.json").read_text())
        record_schema = json.loads((schema_dir / "review-record.v5.schema.json").read_text())
        registry = Registry().with_resource(
            "review.v5.schema.json", Resource.from_contents(review_schema),
        )
        jsonschema.Draft202012Validator(record_schema, registry=registry).validate(stored)

    def test_verify_detects_missing_or_changed_imported_source_objects(self):
        original = self.original_text("28.6%")
        original_item, _ = self.source_setup(original=original)
        object_path = self.root / "objects" / "sha256" / original_item["sha256"]
        object_path.write_text("changed bytes", encoding="utf-8")
        with self.assertRaisesRegex(CustodyError, "SOURCE_OBJECT_INTEGRITY_FAILURE"):
            verify_all(self.root)

    def test_verify_and_seal_reject_unreferenced_source_objects(self):
        original = self.original_text("28.6%")
        self.source_setup(original=original)
        orphan = b"unreferenced synthetic object"
        orphan_path = self.root / "objects" / "sha256" / sha256_bytes(orphan)
        orphan_path.write_bytes(orphan)
        with self.assertRaisesRegex(CustodyError, "UNREFERENCED_SOURCE_OBJECT"):
            verify_all(self.root)
        with self.assertRaisesRegex(CustodyError, "UNREFERENCED_SOURCE_OBJECT"):
            seal_inventory(self.root)

    def test_import_is_idempotent_for_the_same_hash_pinned_batch(self):
        original = self.original_text("28.6%")
        source = original.encode("utf-8")
        item = {
            "name": "original.txt", "role": "original", "size": len(source),
            "sha256": sha256_bytes(source), "document_id": DOCUMENT,
            "source_id": DOCUMENT, "source_version": "v1",
            "provenance": self.synthetic_provenance("idempotent-import"),
        }
        (self.root / "incoming" / item["name"]).write_bytes(source)
        manifest = {"schema_version": IMPORT_VERSION, "batch_id": "synthetic-batch-replay", "files": [item]}
        path = self.root / "incoming" / "synthetic-batch-replay.json"
        path.write_bytes(canonical_bytes(manifest))
        self.assertEqual(import_batch(self.root, "synthetic-batch-replay")["status"], "IMPORTED")
        self.assertEqual(import_batch(self.root, "synthetic-batch-replay")["status"], "ALREADY_IMPORTED")

    def test_mismatched_negative_label_is_rejected(self):
        original = self.original_text("28.5%")
        original_item, _ = self.source_setup(original=original)
        review = self.review_object(
            original_item, None, original_text=original,
            original_percent="28.5%", role="CORRECT_NEGATIVE_RELATION",
        )
        with self.assertRaisesRegex(CustodyError, "NEGATIVE_LABEL_NOT_ARITHMETICALLY_CORRECT"):
            self.record(review)

    def test_correction_positive_requires_original_discrepancy_and_fixed_relation(self):
        original = self.original_text("28.5%")
        correction = self.correction_text("28.6%", "28.5%")
        original_item, correction_item = self.source_setup(original=original, correction=correction)
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction, original_percent="28.5%",
            corrected_percent="28.6%", old_percent="28.5%",
        )
        self.assertEqual(self.record(review), {"status": "RECORDED"})
        counts = verify_all(self.root)
        self.assertEqual(counts["eligible_positive_issues"], 1)
        self.assertEqual(counts["eligible_positive_relations"], 1)
        self.assertEqual(counts["arithmetic_mismatches"], 1)

    def test_correction_positive_rejects_wrong_old_value_mapping(self):
        original = self.original_text("28.5%")
        correction = self.correction_text("28.6%", "28.5%")
        original_item, correction_item = self.source_setup(original=original, correction=correction)
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction, original_percent="28.5%",
            corrected_percent="28.6%", correction_old_percent="28.6%",
        )
        with self.assertRaisesRegex(CustodyError, "CORRECTION_OLD_VALUE_OVERLAPS_CORRECTED_VALUE"):
            self.record(review)

    def test_correction_that_does_not_recompute_is_not_eligible(self):
        original = self.original_text("28.5%")
        correction = self.correction_text("28.5%", "28.5%")
        original_item, correction_item = self.source_setup(original=original, correction=correction)
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction, original_percent="28.5%",
            corrected_percent="28.5%", old_percent="28.5%",
        )
        with self.assertRaisesRegex(CustodyError, "CORRECTION_DOES_NOT_CHANGE_RELATION"):
            self.record(review)

    def test_correction_must_map_every_operand_and_displayed_value_that_changed(self):
        original = self.original_text("28.5%")
        correction = "Correction Table 1 / Group A / main cohort / N = 8 / count 2 / 25.0% instead of 28.5%\n"
        original_item, correction_item = self.source_setup(original=original, correction=correction)
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction, original_percent="28.5%",
            corrected_percent="25.0%", correction_denominator="N = 8",
            changed_fields=["percentage"],
        )
        with self.assertRaisesRegex(CustodyError, "CORRECTION_CHANGED_FIELDS_NOT_EXACT"):
            self.record(review)

    def test_correction_with_a_conflicting_table_scope_is_rejected(self):
        original = self.original_text("28.5%", group="Group A")
        correction = self.correction_text("28.6%", "28.5%", group="Group B")
        original_item, correction_item = self.source_setup(original=original, correction=correction)
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction, original_percent="28.5%",
            corrected_percent="28.6%", old_percent="28.5%", corrected_group="Group B",
        )
        conflicting = relation(correction, "Group B", "28.6%")
        review["correction_binding"]["corrected_relation"] = conflicting
        with self.assertRaisesRegex(CustodyError, "CORRECTION_RELATION_SCOPE_MISMATCH"):
            self.record(review)

    def test_noneligible_positive_cannot_store_an_unchecked_correction_binding(self):
        original = self.original_text("28.5%")
        correction = self.correction_text("28.6%", "28.5%")
        original_item, correction_item = self.source_setup(original=original, correction=correction)
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction, original_percent="28.5%",
            corrected_percent="28.6%", eligibility="UNRESOLVED",
        )
        with self.assertRaisesRegex(CustodyError, "CORRECTION_BINDING_REQUIRES_ELIGIBILITY"):
            self.record(review)

    def test_correction_version_must_be_bound_to_the_same_article_family(self):
        original = self.original_text("28.5%")
        correction = self.correction_text("28.6%", "28.5%")
        original_item, correction_item = self.source_setup(
            original=original, correction=correction,
            correction_document_id="doi:10.5555/different-paper",
        )
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction, original_percent="28.5%",
            corrected_percent="28.6%", old_percent="28.5%",
        )
        with self.assertRaisesRegex(CustodyError, "SOURCE_VERSION_NOT_IMPORTED"):
            self.record(review)

    def test_same_canonical_relationship_cannot_be_duplicated_with_new_review_id(self):
        original = self.original_text("28.6%")
        original_item, _ = self.source_setup(original=original)
        first = self.review_object(original_item, None, original_text=original, review_id="review-one")
        second = self.review_object(original_item, None, original_text=original, review_id="review-two")
        self.record(first)
        with self.assertRaisesRegex(CustodyError, "DUPLICATE_CANONICAL_RELATIONSHIP"):
            self.record(second)

    def test_relationship_dedup_ignores_reviewer_selected_context_and_locator_spans(self):
        original = "Table 1 / Group A / main cohort / N = 7 / count 2 / 28.6%\n"
        original_item, _ = self.source_setup(original=original)
        first = self.review_object(
            original_item, None, original_text=original, original_percent="28.6%",
            numerator="2", denominator="N = 7",
        )
        second = self.review_object(
            original_item, None, review_id="review-two", original_text=original,
            original_percent="28.6%", numerator="2", denominator="N = 7",
        )
        # All numeric operand spans stay bound to the same source bytes while
        # the reviewer widens/narrows the surrounding labels and context.
        second["relationship"]["context_span"] = span(original, original.rstrip())
        second["relationship"]["object_locator_span"] = span(original, "Group A / main cohort")
        second["relationship"]["scope_span"] = span(original, "main cohort")
        self.record(first)
        with self.assertRaisesRegex(CustodyError, "DUPLICATE_CANONICAL_RELATIONSHIP"):
            self.record(second)

    def test_same_source_bytes_with_a_new_version_label_do_not_inflate_relation_count(self):
        original = self.original_text("28.6%")
        first_item, _ = self.source_setup(original=original, source_version="v1")
        second_item, _ = self.source_setup(original=original, source_version="owner-renamed-v2")
        first = self.review_object(first_item, None, original_text=original, review_id="review-one")
        second = self.review_object(second_item, None, original_text=original, review_id="review-two")
        self.record(first)
        with self.assertRaisesRegex(CustodyError, "DUPLICATE_CANONICAL_RELATIONSHIP"):
            self.record(second)

    def test_harmless_row_text_edit_across_versions_is_unresolved(self):
        first_text = self.original_text("28.6%")
        second_text = first_text.rstrip("\n").replace("28.6%", "28.6% / confirmed") + "\n"
        first_item, _ = self.source_setup(original=first_text, source_version="v1")
        second_item, _ = self.source_setup(original=second_text, source_version="v2")
        first = self.review_object(
            first_item, None, review_id="review-one", original_text=first_text,
        )
        second = self.review_object(
            second_item, None, review_id="review-two", original_text=second_text,
        )

        self.record(first)
        with self.assertRaisesRegex(CustodyError, "SOURCE_ROW_LINEAGE_UNRESOLVED"):
            self.record(second)
        self.assertEqual(verify_all(self.root)["eligible_negative_relations"], 1)

    def test_cross_version_distinct_subgroups_remain_distinct(self):
        first_text = self.original_text("28.6%", "Group A")
        second_text = self.original_text("28.6%", "Group B")
        first_item, _ = self.source_setup(original=first_text, source_version="v1")
        second_item, _ = self.source_setup(original=second_text, source_version="v2")
        first = self.review_object(
            first_item, None, review_id="review-one", original_text=first_text,
            group="Group A",
        )
        second = self.review_object(
            second_item, None, review_id="review-two", original_text=second_text,
            group="Group B",
        )

        self.record(first)
        self.record(second)
        counts = verify_all(self.root)
        self.assertEqual(counts["eligible_negative_relations"], 2)
        self.assertEqual(counts["eligible_negative_document_ids"], 1)

    def test_distinct_source_rows_with_equal_values_count_as_distinct_relations(self):
        original = (
            self.original_text("28.6%", "Group A")
            + self.original_text("28.6%", "Group B")
        )
        original_item, _ = self.source_setup(original=original)
        first = self.review_object(
            original_item, None, original_text=original, group="Group A", original_percent="28.6%",
        )
        second = self.review_object(
            original_item, None, original_text=original, group="Group B", original_percent="28.6%",
            review_id="review-two", line_number=1,
        )
        self.record(first)
        self.record(second)
        counts = verify_all(self.root)
        self.assertEqual(counts["eligible_negative_relations"], 2)
        self.assertEqual(counts["eligible_negative_document_ids"], 1)
        self.assertEqual(counts["eligible_negative_tables"], 1)
        self.assertEqual(counts["eligible_negative_versions"], 1)

    def test_identical_rows_in_distinct_tables_count_as_distinct_relations(self):
        original = (
            "Table 1 / Group A / main cohort / N = 7 / count 2 / 28.6%\n"
            "Table 2 / Group A / main cohort / N = 7 / count 2 / 28.6%\n"
        )
        original_item, _ = self.source_setup(original=original)
        first = self.review_object(
            original_item, None, original_text=original, group="Group A",
            original_percent="28.6%", table_locator="Table 1", line_number=0,
        )
        second = self.review_object(
            original_item, None, review_id="review-two", original_text=original,
            group="Group A", original_percent="28.6%", table_locator="Table 2", line_number=1,
            numerator_occurrence=1,
        )
        self.record(first)
        self.record(second)
        counts = verify_all(self.root)
        self.assertEqual(counts["eligible_negative_relations"], 2)
        self.assertEqual(counts["eligible_negative_tables"], 2)
        self.assertEqual(counts["eligible_negative_document_ids"], 1)

    def test_precision_aliases_of_the_same_source_row_collapse_across_versions(self):
        first_text = "Table 1 / Group A / main cohort / N = 118 / count 7 / 6%\n"
        first_item, _ = self.source_setup(original=first_text, source_version="v1")
        second_text = "Table 1 / Group A / main cohort / N = 118 / count 7 / 5.9%\n"
        second_item, _ = self.source_setup(original=second_text, source_version="owner-renamed-v2")
        first = self.review_object(
            first_item, None, review_id="review-one", original_text=first_text,
            original_percent="6%", numerator="7", denominator="N = 118",
        )
        second = self.review_object(
            second_item, None, review_id="review-two", original_text=second_text,
            original_percent="5.9%", numerator="7", denominator="N = 118",
        )
        self.record(first)
        with self.assertRaisesRegex(CustodyError, "DUPLICATE_CANONICAL_RELATIONSHIP"):
            self.record(second)
        self.assertEqual(verify_all(self.root)["eligible_negative_relations"], 1)

    def test_table_number_zero_padding_is_a_stable_locator_alias(self):
        first_text = "Table 1 / Group A / main cohort / N = 118 / count 7 / 6%\n"
        first_item, _ = self.source_setup(original=first_text, source_version="v1")
        second_text = "Table 01 / Group A / main cohort / N = 118 / count 7 / 5.9%\n"
        second_item, _ = self.source_setup(original=second_text, source_version="v2")
        first = self.review_object(
            first_item, None, review_id="review-one", original_text=first_text,
            original_percent="6%", numerator="7", denominator="N = 118",
        )
        second = self.review_object(
            second_item, None, review_id="review-two", original_text=second_text,
            original_percent="5.9%", numerator="7", denominator="N = 118",
            table_locator="Table 01",
        )
        self.record(first)
        with self.assertRaisesRegex(CustodyError, "DUPLICATE_CANONICAL_RELATIONSHIP"):
            self.record(second)

    def test_changed_table_locator_across_versions_is_unresolved(self):
        first_text = "Table 1 / Group A / main cohort / N = 7 / count 2 / 28.6%\n"
        first_item, _ = self.source_setup(original=first_text, source_version="v1")
        second_text = "Table 2 / Group A / main cohort / N = 7 / count 2 / 28.6%\n"
        second_item, _ = self.source_setup(original=second_text, source_version="v2")
        first = self.review_object(
            first_item, None, review_id="review-one", original_text=first_text,
        )
        second = self.review_object(
            second_item, None, review_id="review-two", original_text=second_text,
            table_locator="Table 2", numerator_occurrence=1,
        )
        self.record(first)
        with self.assertRaisesRegex(CustodyError, "SOURCE_TABLE_LINEAGE_UNRESOLVED"):
            self.record(second)
        self.assertEqual(verify_all(self.root)["eligible_negative_relations"], 1)

    def test_v4_record_is_verified_without_rewriting_and_uses_row_identity_for_new_counts(self):
        original = (
            self.original_text("28.6%", "Group A")
            + self.original_text("28.6%", "Group B")
        )
        original_item, _ = self.source_setup(original=original)
        first = self.review_object(
            original_item, None, original_text=original,
            group="Group A", original_percent="28.6%",
        )
        self.record(first)
        record_path = self.root / "manifests" / "reviews" / "review-one.json"
        stored = json.loads(record_path.read_text(encoding="utf-8"))
        stored["schema_version"] = "rw-custody-review-record/4"
        stored["checked"]["relationship_key"] = sha256_bytes(canonical_bytes({
            "document_id": DOCUMENT,
            "numerator": 2,
            "denominator": 7,
            "percentage": "28.6",
        }))
        v4_bytes = canonical_bytes(stored)
        record_path.write_bytes(v4_bytes)

        second = self.review_object(
            original_item, None, review_id="review-two", original_text=original,
            group="Group B", original_percent="28.6%", line_number=1,
        )
        self.record(second)
        self.assertEqual(verify_all(self.root)["eligible_negative_relations"], 2)
        self.assertEqual(record_path.read_bytes(), v4_bytes)

    def test_legacy_precision_alias_records_remain_intact_and_aggregate_once(self):
        first_text = "Table 1 / Group A / main cohort / N = 118 / count 7 / 6%\n"
        second_text = "Table 1 / Group A / main cohort / N = 118 / count 7 / 5.9%\n"
        first_item, _ = self.source_setup(original=first_text, source_version="v1")
        second_item, _ = self.source_setup(original=second_text, source_version="v2")
        first = self.review_object(
            first_item, None, review_id="review-one", original_text=first_text,
            original_percent="6%", numerator="7", denominator="N = 118",
        )
        second = self.review_object(
            second_item, None, review_id="review-two", original_text=second_text,
            original_percent="5.9%", numerator="7", denominator="N = 118",
        )
        first_path = self.write_v4_record(first)
        second_path = self.write_v4_record(second)
        before = (first_path.read_bytes(), second_path.read_bytes())

        counts = verify_all(self.root)
        self.assertEqual(counts["eligible_negative_relations"], 1)
        self.assertEqual((first_path.read_bytes(), second_path.read_bytes()), before)

    def test_same_numeric_relation_in_changed_source_version_counts_once(self):
        first_text = self.original_text("28.6%")
        first_item, _ = self.source_setup(original=first_text, source_version="v1")
        second_text = "\n" + self.original_text("28.6%")
        second_item, _ = self.source_setup(original=second_text, source_version="v2")
        first = self.review_object(
            first_item, None, review_id="review-one", original_text=first_text,
        )
        second = self.review_object(
            second_item, None, review_id="review-two", original_text=second_text,
            line_number=1,
        )
        self.record(first)
        with self.assertRaisesRegex(CustodyError, "DUPLICATE_CANONICAL_RELATIONSHIP"):
            self.record(second)

    def test_one_source_version_identity_cannot_bind_two_different_hashes(self):
        self.source_setup(original=self.original_text("28.6%"), source_version="v1")
        with self.assertRaisesRegex(CustodyError, "SOURCE_VERSION_CONTENT_CONFLICT"):
            self.source_setup(original=self.original_text("28.5%"), source_version="v1")

    def test_two_distinct_doi_documents_count_as_two(self):
        first_text = self.original_text("28.6%", "Group A")
        first_item, _ = self.source_setup(original=first_text, document_id=DOCUMENT)
        self.record(self.review_object(first_item, None, original_text=first_text))
        second_id = "doi:10.5555/another-synthetic-study"
        second_text = self.original_text("28.6%", "Group A")
        second_item, _ = self.source_setup(
            original=second_text, document_id=second_id, source_version="v1",
        )
        second_review = self.review_object(
            second_item, None, original_text=second_text, review_id="review-two",
        )
        self.record(second_review)
        counts = verify_all(self.root)
        self.assertEqual(counts["eligible_negative_relations"], 2)
        self.assertEqual(counts["eligible_negative_document_ids"], 2)

    def test_eligible_review_cannot_use_a_different_source_version(self):
        original = self.original_text("28.6%")
        original_item, _ = self.source_setup(original=original, source_version="v1")
        review = self.review_object(original_item, None, original_text=original)
        review["source_version"] = "v2"
        with self.assertRaisesRegex(CustodyError, "SOURCE_VERSION_NOT_IMPORTED"):
            self.record(review)

    def test_scope_and_source_version_flags_are_explicit_human_attestations(self):
        original = self.original_text("28.6%")
        original_item, _ = self.source_setup(original=original)
        review = self.review_object(original_item, None, original_text=original)
        review["source_version_status"] = "UNRESOLVED"
        with self.assertRaisesRegex(CustodyError, "ELIGIBILITY_NOT_ESTABLISHED"):
            self.record(review)

    def test_pdf_source_is_not_claimed_as_byte_mapped_text(self):
        original = self.original_text("28.6%")
        original_item, _ = self.source_setup(original=original, extension="pdf")
        review = self.review_object(original_item, None, original_text=original)
        with self.assertRaisesRegex(CustodyError, "SOURCE_FORMAT_NOT_BOUND_FOR_TEXT_REVIEW"):
            self.record(review)

    def test_public_export_suppresses_small_exact_counts_and_private_identifiers(self):
        original = self.original_text("28.6%")
        original_item, _ = self.source_setup(original=original)
        self.record(self.review_object(original_item, None, original_text=original))
        seal_inventory(self.root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--dev-root", str(self.root), "export-summary"])
        self.assertEqual(code, 2)
        serialized = output.getvalue()
        self.assertIn("PUBLIC_EXPORT_THRESHOLDS_NOT_MET", serialized)
        for private in (DOCUMENT, CORRECTION_ID, "28.6%", "review-one", "source_sha256", '"1"'):
            self.assertNotIn(private, serialized)
        self.assertFalse((self.root / "audit" / "public-export.json").exists())

        next_text = self.original_text("28.6%", "Group B")
        next_item, _ = self.source_setup(
            original=next_text, document_id="doi:10.5555/another-synthetic-study",
        )
        self.record(self.review_object(
            next_item, None, original_text=next_text, review_id="review-two", group="Group B",
        ))
        seal_inventory(self.root)
        with self.assertRaisesRegex(CustodyError, "PUBLIC_EXPORT_THRESHOLDS_NOT_MET"):
            export_public_summary(self.root)

    def test_threshold_export_is_one_time_and_keyed_to_its_sealed_snapshot(self):
        from unittest.mock import patch

        seal_inventory(self.root)
        counts = summarize(self.root)
        counts.update({
            "eligible_positive_issues": 1,
            "eligible_negative_relations": 50,
            "eligible_negative_document_ids": 15,
            "current_inventory_sealed": True,
            "current_seal_commitment": "a" * 64,
        })
        with patch("custody_worker.store._summarize", return_value=counts):
            exported = export_public_summary(self.root)
            self.assertTrue(exported["minimum_count_thresholds_met"])
            self.assertEqual(export_public_summary(self.root), exported)

        changed_counts = dict(counts)
        changed_counts["current_seal_commitment"] = "b" * 64
        with patch("custody_worker.store._summarize", return_value=changed_counts):
            with self.assertRaisesRegex(CustodyError, "PUBLIC_EXPORT_ALREADY_ISSUED"):
                export_public_summary(self.root)

    def test_public_export_requires_a_sealed_snapshot(self):
        with self.assertRaisesRegex(CustodyError, "PUBLIC_EXPORT_REQUIRES_SEALED_INVENTORY"):
            export_public_summary(self.root)

    def test_schema_matches_runtime_private_and_public_summary(self):
        import jsonschema

        for schema_name, value in [
            ("summary.v3.schema.json", summarize(self.root)),
        ]:
            schema = json.loads((Path(__file__).parents[1] / "custody_worker" / "schemas" / schema_name).read_text())
            jsonschema.Draft202012Validator(schema).validate(value)
        public = {
            "schema_version": "rw-custody-public-summary/2",
            "eligible_positive_cases": "AT_LEAST_1",
            "eligible_negative_relationships": "AT_LEAST_50",
            "distinct_negative_document_ids": "AT_LEAST_15",
            "minimum_count_thresholds_met": True,
            "inventory_sealed": True,
            "integrity_commitment": "a" * 64,
            "meaning": "Thresholded custodian aggregate; not a Wave 3 result or scientific performance claim",
        }
        from custody_worker.store import _validate_public_summary
        _validate_public_summary(public)
        schema = json.loads((Path(__file__).parents[1] / "custody_worker" / "schemas" / "public-summary.v2.schema.json").read_text())
        jsonschema.Draft202012Validator(schema).validate(public)
        receipt = {
            "schema_version": "rw-custody-public-export/2",
            "inventory_commitment": "a" * 64,
            "public_summary": public,
        }
        schema = json.loads((Path(__file__).parents[1] / "custody_worker" / "schemas" / "public-export.v2.schema.json").read_text())
        jsonschema.Draft202012Validator(schema).validate(receipt)

    def test_review_schema_accepts_source_bound_synthetic_positive(self):
        import jsonschema

        original = self.original_text("28.5%")
        correction = self.correction_text("28.6%", "28.5%")
        original_item, correction_item = self.source_setup(original=original, correction=correction)
        review = self.review_object(
            original_item, correction_item, role="CORRECTION_POSITIVE",
            original_text=original, correction_text=correction, original_percent="28.5%",
            corrected_percent="28.6%", old_percent="28.5%",
        )
        schema = json.loads((Path(__file__).parents[1] / "custody_worker" / "schemas" / "review.v5.schema.json").read_text())
        Draft202012Validator(schema).validate(review)

        unresolved = dict(review)
        unresolved["eligibility"] = "UNRESOLVED"
        validator = Draft202012Validator(schema)
        self.assertTrue(list(validator.iter_errors(unresolved)))
        unresolved["correction_binding"] = None
        self.assertFalse(list(validator.iter_errors(unresolved)))

    def test_release_builder_rejects_symlinked_checksum_sidecar(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink creation is unavailable")
        repository = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory(prefix="rw-build-link-test-") as temporary:
            root = Path(temporary)
            shutil.copyfile(repository / "LICENSE", root / "LICENSE")
            shutil.copytree(repository / "custody_worker", root / "custody_worker",
                            ignore=shutil.ignore_patterns("__pycache__", "dist"))
            output = root / "custody_worker" / "dist"
            output.mkdir()
            target = root / "checksum-target.txt"
            target.write_text("keep this exact file", encoding="utf-8")
            sidecar = output / "rw-custody-0.5.0.dev0.pyz.sha256"
            sidecar.symlink_to(target)
            result = subprocess.run(
                [sys.executable, str(root / "custody_worker" / "build_release.py")],
                cwd=root, capture_output=True, text=True, timeout=20,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep this exact file")
            self.assertFalse((output / "rw-custody-0.5.0.dev0.pyz").exists())

    def test_release_builder_rejects_symlinked_input_parent(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink creation is unavailable")
        repository = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory(prefix="rw-build-parent-link-test-") as temporary:
            root = Path(temporary)
            shutil.copyfile(repository / "LICENSE", root / "LICENSE")
            real_package = root / "real-custody-worker"
            shutil.copytree(repository / "custody_worker", real_package,
                            ignore=shutil.ignore_patterns("__pycache__", "dist"))
            (root / "custody_worker").symlink_to(real_package, target_is_directory=True)
            result = subprocess.run(
                [sys.executable, str(real_package / "build_release.py")],
                cwd=root, capture_output=True, text=True, timeout=20,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Build input path contains a link", result.stderr)

    def test_seal_commitment_is_stable_per_store_and_keyed_between_stores(self):
        first = seal_inventory(self.root)
        second = seal_inventory(self.root)
        self.assertEqual(first, second)
        key_bytes = (self.root / "audit" / "commitment-key.bin").read_bytes()
        self.assertEqual(len(key_bytes), 32)
        self.assertNotIn(key_bytes.hex(), json.dumps(summarize(self.root)))

        other_root = DEV_PARENT / ("rw-v5-test-" + uuid.uuid4().hex)
        other_root.mkdir()
        try:
            (other_root / ".synthetic-only").write_text(MARKER, encoding="ascii")
            make_store(other_root)
            self.assertNotEqual(seal_inventory(other_root)["seal_sha256"], first["seal_sha256"])
        finally:
            shutil.rmtree(other_root)

    def test_old_seal_stops_matching_after_a_new_review(self):
        original = self.original_text("28.6%")
        original_item, _ = self.source_setup(original=original)
        seal_inventory(self.root)
        before = summarize(self.root)
        self.assertTrue(before["current_inventory_sealed"])
        self.record(self.review_object(original_item, None, original_text=original))
        after = summarize(self.root)
        self.assertFalse(after["current_inventory_sealed"])
        self.assertIsNone(after["current_seal_commitment"])

    def test_doctor_does_not_claim_os_network_isolation(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--dev-root", str(self.root), "doctor"])
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["host_egress"], "MUST_BE_VERIFIED_EXTERNALLY")
        self.assertNotEqual(report.get("network"), "DISABLED_BY_DESIGN")

    def test_cli_exports_only_thresholded_aggregate(self):
        seal_inventory(self.root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--dev-root", str(self.root), "export-summary"])
        self.assertEqual(code, 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["code"], "PUBLIC_EXPORT_THRESHOLDS_NOT_MET")

    def test_verify_does_not_create_missing_store_state(self):
        incomplete = DEV_PARENT / ("rw-incomplete-" + uuid.uuid4().hex)
        incomplete.mkdir()
        (incomplete / ".synthetic-only").write_text(MARKER, encoding="ascii")
        try:
            with self.assertRaises(CustodyError):
                verify_all(incomplete)
            self.assertFalse((incomplete / "audit").exists())
            self.assertFalse((incomplete / "manifests").exists())
        finally:
            shutil.rmtree(incomplete)

    def test_checked_in_synthetic_bundle_is_source_consistent_end_to_end(self):
        fixture = Path(__file__).parents[1] / "custody_worker" / "examples"
        import jsonschema
        manifest_schema = json.loads((Path(__file__).parents[1] / "custody_worker" / "schemas" / "import-manifest.v2.schema.json").read_text())
        manifest_fixture = json.loads((fixture / "synthetic-batch.json").read_text())
        jsonschema.Draft202012Validator(manifest_schema).validate(manifest_fixture)
        for name in (
            "synthetic-batch.json", "synthetic-review.json",
            "synthetic-original.txt", "synthetic-correction.txt",
        ):
            shutil.copyfile(fixture / name, self.root / "incoming" / name)
        shutil.copyfile(
            fixture / "synthetic-batch.json",
            self.root / "incoming" / "synthetic-batch-1.json",
        )
        self.assertEqual(import_batch(self.root, "synthetic-batch-1")["status"], "IMPORTED")
        self.assertEqual(record_review(self.root, "synthetic-review"), {"status": "RECORDED"})
        counts = verify_all(self.root)
        self.assertEqual(counts["eligible_positive_issues"], 1)
        self.assertEqual(counts["eligible_negative_relations"], 0)
        seal_inventory(self.root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--dev-root", str(self.root), "export-summary"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["code"], "PUBLIC_EXPORT_THRESHOLDS_NOT_MET")


if __name__ == "__main__":
    unittest.main()
