"""Local JSON contracts for development audit tools; outside the trusted core."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
SHA = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
TEXT = {"type": "string", "maxLength": 10000}
COUNT = {"type": "integer", "minimum": 0, "maximum": 999999999}
PERCENT = {"type": "string", "pattern": r"^[0-9]{1,3}(\.[0-9]{1,6})?$"}
ANCHOR = {"type": "object", "additionalProperties": False,
          "required": ["byte_start", "byte_end", "quote"],
          "properties": {"byte_start": COUNT, "byte_end": COUNT, "quote": TEXT,
                         "character_start": COUNT, "character_end": COUNT}}


def obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties) if required is None else required}


def schema_documents() -> dict[str, dict[str, Any]]:
    source = obj({"path": TEXT, "sha256": SHA, "url": TEXT,
                  "provenance_status": TEXT, "license": TEXT})
    relationship = obj({
        "relationship_id": {"type": "string", "minLength": 1, "maxLength": 250},
        "table_id": TEXT, "numerator": COUNT,
        "denominator": {"anyOf": [COUNT, {"type": "null"}]},
        "reported_percent": PERCENT, "precision": {"type": "integer", "minimum": 0, "maximum": 6},
        "scope_status": {"enum": ["explicit_cell", "explicit_header", "explicit_table", "explicit_row_group", "reviewer_mapped", "derived_unresolved", "unknown"]},
        "arithmetic_status": {"enum": ["arithmetic_match", "arithmetic_mismatch_candidate", "not_computed"]},
        "review_outcome": {"enum": ["arithmetic_only", "unresolved_rounding", "unresolved_scope", "correction_corroborated"]},
        "scope_rationale": TEXT, "anchor": ANCHOR,
        "denominator_evidence": {"type": "array", "items": ANCHOR, "maxItems": 16},
    })
    annotations = obj({"schema_version": {"const": 1}, "exposure": {"const": "development"},
        "annotation_provenance": TEXT,
        "documents": {"type": "array", "minItems": 1, "maxItems": 100, "items": obj({
            "document_id": TEXT, "work_family_id": TEXT, "independence_status": TEXT,
            "source": source,
            "relationships": {"type": "array", "maxItems": 5000, "items": relationship},
        })}})
    run = obj({"schema_version": {"const": 1}, "label": TEXT, "detector_revision": TEXT,
        "detector_files": {"type": "object", "minProperties": 1, "maxProperties": 10, "additionalProperties": SHA},
        "documents": {"type": "array", "minItems": 1, "maxItems": 100, "items": obj({
            "document_id": TEXT, "source_sha256": SHA,
            "status": {"enum": ["analyzed", "extraction_failed"]},
            "report_path": {"anyOf": [TEXT, {"type": "null"}]},
            "report_sha256": {"anyOf": [SHA, {"type": "null"}]},
            "reason": {"anyOf": [TEXT, {"type": "null"}]},
        })}})
    evidence = {"type": "object", "required": ["source_sha256"],
                "properties": {"source_sha256": SHA}}
    raw_result = {"type": "object", "required": ["status", "reason", "numerator", "denominator", "reported_percent", "evidence"],
                  "properties": {"status": TEXT, "reason": {"anyOf": [TEXT, {"type": "null"}]},
                    "numerator": COUNT, "denominator": {"anyOf": [COUNT, {"type": "null"}]},
                    "reported_percent": PERCENT, "evidence": evidence}}
    audit = obj({"schema_version": {"const": "research-audit.v1"},
        "document": obj({"document_id": TEXT, "source_sha256": SHA, "source_bytes": COUNT,
            "input_format": {"enum": ["jats", "pdf"]},
            "source_url": TEXT, "provenance_status": TEXT,
            "provenance_authenticated_by_tool": {"const": False},
            "expected_hash_verified": {"type": "boolean"}}),
        "detector_files": {"type": "object", "additionalProperties": SHA},
        "processing": obj({"status": {"enum": ["completed", "extraction_failed"]},
            "reason": {"anyOf": [TEXT, {"type": "null"}]},
            "tables_inspected": COUNT, "relationships_detected": COUNT,
            "extracted_text_sha256": {"anyOf": [SHA, {"type": "null"}]},
            "extraction_profile": TEXT}),
        "summary": obj({"arithmetic_matches": COUNT, "mismatch_candidates": COUNT,
            "abstentions": COUNT, "conditional_mismatches": COUNT}),
        "findings": {"type": "array", "maxItems": 1000, "items": obj({
            "finding_id": TEXT,
            "state": {"enum": ["extracted_evidence", "arithmetic_match", "arithmetic_mismatch_candidate"]},
            "review_state": {"const": "unreviewed"},
            "scientific_error_status": {"const": "not_established"}, "relationship": raw_result})},
        "limitations": {"type": "array", "maxItems": 30, "items": TEXT}})
    comparison = obj({"schema_version": {"const": "research-benchmark.v1"},
        "exposure": {"const": "development"}, "annotation_sha256": SHA,
        "document_count": COUNT, "work_family_count": COUNT, "annotation_count": COUNT,
        "runs": {"type": "array", "minItems": 1, "maxItems": 10,
            "items": obj({"label": TEXT, "detector_revision": TEXT,
                "detector_files": {"type": "object", "additionalProperties": SHA},
                "metrics": {"type": "object", "additionalProperties": COUNT},
                "abstentions_by_reason": {"type": "object", "additionalProperties": COUNT},
                "error_taxonomy": {"type": "object", "additionalProperties": COUNT},
                "documents": {"type": "array", "maxItems": 100, "items": {"type": "object"}},
                "relationships": {"type": "array", "maxItems": 20000, "items": {"type": "object"}},
                "unannotated_outputs": {"type": "array", "maxItems": 10000, "items": {"type": "object"}},
            })}, "limitations": {"type": "array", "items": TEXT, "maxItems": 30}})
    return {"research-audit.v1.schema.json": audit,
            "percentage-annotations.v1.schema.json": annotations,
            "percentage-run.v1.schema.json": run,
            "research-benchmark.v1.schema.json": comparison}


def validate(data: Any, schema_name: str) -> None:
    # Schemas are bundled constants; no user-controlled or remote references resolve.
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise ValueError("Audit tools require the optional development dependency jsonschema") from exc
    schema = schema_documents()[schema_name]
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        raise ValueError(f"{schema_name} at {list(error.path)}: {error.message}")


def main() -> None:
    for name, schema in schema_documents().items():
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}
        (SCHEMA_ROOT / name).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
