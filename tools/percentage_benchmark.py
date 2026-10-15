"""Offline, source-bound comparison of supplied development percentage reports.

This module reads only explicit manifest paths. It never fetches sources, runs a
historical executable, or promotes arithmetic annotations to scientific truth.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from tools.audit_contracts import validate
from tools.offline_files import read_regular
from tools.jats_percentage_audit import (
    MAX_SOURCE_BYTES, JATSSourceError, _parse_jats, _text, _DENOMINATOR_RE,
    _fragments, _descendants, _cells, _attribute, _GROUP_POPULATION_RE,
    _population_label_words, _population_label_occurs,
)
from tools.public_discovery import percentage_recalculation

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ANNOTATIONS = 20000
MAX_SOURCE_SET_BYTES = 32 * 1024 * 1024
COMPUTED = {"arithmetic_match", "arithmetic_mismatch_candidate"}
INTEGER = r"(?:[0-9]{1,3}(?:,[0-9]{3}){1,2}|[0-9]{1,9})"
PAIR = re.compile(rf"(?<![\w.,+\-−±/])(?P<n>{INTEGER})(?:\s*/\s*(?P<d>{INTEGER}))?\s*\(\s*(?P<p>[0-9]{{1,3}}(?:\.[0-9]{{1,6}})?)\s*%?\s*\)")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pairs_in_span(text: str, start: int, end: int) -> list[re.Match]:
    pairs = list(PAIR.finditer(text[start:end]))
    if pairs:
        return pairs
    # Compact labels such as P12 (...) C4 (...) require the same exhaustive,
    # bounded component grammar as extraction, never a numeric-token suffix.
    pairs = []
    for fragment in _fragments(text):
        if fragment and start <= fragment["character_start"] and fragment["character_end"] <= end:
            pair = PAIR.fullmatch(fragment["numeric_quote"])
            if pair is not None:
                pairs.append(pair)
    return pairs


def load_json(path: Path) -> Any:
    return parse_json(read_regular(path, MAX_JSON_BYTES), path)


def parse_json(data: bytes, path: Path) -> Any:
    try:
        return json.loads(data)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"Invalid benchmark JSON: {path.name}") from exc


def confined(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or "\\" in relative:
        raise ValueError("Manifest paths must be relative and confined to their manifest directory")
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Manifest path escapes its evidence directory")
    return path


def node_map(data: bytes) -> dict[tuple[int, int], Any]:
    root = _parse_jats(data)
    nodes = {}
    stack = [root]
    while stack:
        node = stack.pop()
        nodes[(node.byte_start, node.byte_end)] = node
        stack.extend(reversed(node.children))
    return nodes


def table_cell_context_map(data: bytes) -> dict[tuple[int, int], dict[str, Any]]:
    """Map exact JATS cell nodes to stable table/row/source-cell identities."""
    root = _parse_jats(data)
    output: dict[tuple[int, int], dict[str, Any]] = {}
    table_number = 0
    for wrapper in _descendants(root, "table-wrap"):
        raw_id = _attribute(wrapper, "id")
        for table in _descendants(wrapper, "table"):
            table_number += 1
            table_id = (raw_id or f"table-{table_number}")[:100]
            for row_index, row in enumerate(_descendants(table, "tr"), start=1):
                for cell_index, cell in enumerate(_cells(row)):
                    output[(cell.byte_start, cell.byte_end)] = {
                        "table_id": table_id,
                        "row_index": row_index,
                        "cell_index": cell_index,
                    }
    return output


def check_anchor(anchor: dict[str, Any], nodes: dict[tuple[int, int], Any]) -> str | None:
    start, end = anchor.get("byte_start"), anchor.get("byte_end")
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        return "invalid source byte range"
    node = nodes.get((start, end))
    if node is None:
        return "anchor does not identify an exact source element"
    quote = anchor.get("quote", anchor.get("cell_quote"))
    text = _text(node)
    truncated = anchor.get("quote_truncated", anchor.get("cell_quote_truncated", False))
    if not isinstance(quote, str) or (not text.startswith(quote) if truncated else quote != text):
        return "anchor quote differs from normalized source text"
    cs = anchor.get("character_start", anchor.get("normalized_character_start"))
    ce = anchor.get("character_end", anchor.get("normalized_character_end"))
    if cs is not None or ce is not None:
        if type(cs) is not int or type(ce) is not int or not 0 <= cs < ce <= len(text):
            return "normalized character range is invalid"
        if "relationship_quote" in anchor and anchor["relationship_quote"] != text[cs:ce]:
            return "component quote differs from its normalized source span"
    return None


def _inside_table_wrap(node: Any) -> bool:
    current = node
    while current is not None:
        if current.tag.rsplit("}", 1)[-1].lower() == "table-wrap":
            return True
        current = current.parent
    return False


def _conditional_population_link_errors(
    relation: dict[str, Any], nodes: dict[tuple[int, int], Any]
) -> list[str]:
    calculation = relation.get("conditional_calculation")
    if not isinstance(calculation, dict):
        return ["conditional calculation is not an object"]
    evidence = calculation.get("evidence")
    has_population_link = (
        "population_group" in calculation
        or calculation.get("assumption") == "matched_article_group_sample_size_may_apply_to_table"
        or (isinstance(evidence, dict)
            and ("group_population" in evidence or "table_population_context" in evidence))
    )
    # Missing-data calculations use their own row-scope evidence and do not
    # claim an article-level group-size link.
    if not has_population_link:
        return []
    if not isinstance(evidence, dict):
        return ["conditional population evidence is missing"]
    group_anchor = evidence.get("group_population")
    table_anchor = evidence.get("table_population_context")
    if not isinstance(group_anchor, dict) or not isinstance(table_anchor, dict):
        return ["conditional population anchors are missing"]
    errors: list[str] = []
    if group_anchor.get("role") != "article_group_population":
        errors.append("group population anchor has the wrong evidence role")
    if table_anchor.get("role") != "table_population_group_context":
        errors.append("table population anchor has the wrong evidence role")
    group_node = nodes.get((group_anchor.get("byte_start"), group_anchor.get("byte_end")))
    table_node = nodes.get((table_anchor.get("byte_start"), table_anchor.get("byte_end")))
    if group_node is None or group_node.tag.rsplit("}", 1)[-1].lower() != "p" or _inside_table_wrap(group_node):
        errors.append("group population evidence is not an article paragraph outside a table")
    if table_node is None or not _inside_table_wrap(table_node):
        errors.append("table population evidence is not inside a table wrapper")
    if group_anchor.get("byte_start") == table_anchor.get("byte_start") and group_anchor.get("byte_end") == table_anchor.get("byte_end"):
        errors.append("article and table population anchors must identify distinct elements")

    population_group = calculation.get("population_group")
    label = _population_label_words(population_group) if isinstance(population_group, str) else ()
    denominator = calculation.get("denominator")
    if not label or type(denominator) is not int or denominator <= 0:
        errors.append("conditional population label or denominator is invalid")
    if group_node is not None and label and type(denominator) is int:
        found = any(
            _population_label_words(match.group("label")) == label
            and int(match.group("value").replace(",", "")) == denominator
            for match in _GROUP_POPULATION_RE.finditer(_text(group_node))
        )
        if not found:
            errors.append("article population paragraph does not establish the linked group and denominator")
    if table_node is not None and label and not _population_label_occurs(label, _text(table_node)):
        errors.append("table context does not identify the linked population group")

    if type(denominator) is int and denominator > 0:
        try:
            expected = percentage_recalculation(
                relation.get("numerator"), denominator, relation.get("reported_percent"),
                relation.get("display_precision"),
            )
        except (TypeError, ValueError):
            errors.append("conditional arithmetic operands are invalid")
        else:
            for key in ("arithmetic_matches", "rounded_percent", "exact_ratio_percent"):
                if calculation.get(key) != expected[key]:
                    errors.append("conditional arithmetic disagrees with its declared operands")
                    break
    return errors


def evidence_errors(value: Any, nodes: dict[tuple[int, int], Any], source_hash: str) -> list[str]:
    errors: list[str] = []
    stack = [value]
    visited = 0
    while stack:
        item = stack.pop()
        visited += 1
        if visited > 100000:
            raise ValueError("Detector evidence exceeds the structural limit")
        if isinstance(item, dict):
            if "source_sha256" in item and item["source_sha256"] != source_hash:
                raise ValueError("Detector evidence refers to a different source version")
            if "byte_start" in item or "byte_end" in item:
                error = check_anchor(item, nodes)
                if error:
                    errors.append(error)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    if isinstance(value, dict) and "conditional_calculation" in value:
        errors.extend(_conditional_population_link_errors(value, nodes))
    return errors


def _annotation_key(relation: dict[str, Any]):
    a = relation["anchor"]
    return a["byte_start"], a["byte_end"], relation["numerator"], relation["reported_percent"]


def _result_key(relation: dict[str, Any]):
    e = relation["evidence"]
    return e["byte_start"], e["byte_end"], relation["numerator"], relation["reported_percent"]


def validate_annotations(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str]:
    annotation_bytes = read_regular(path, MAX_JSON_BYTES)
    annotation = parse_json(annotation_bytes, path)
    schema_name = (
        "percentage-annotations.v2.schema.json"
        if isinstance(annotation, dict) and annotation.get("schema_version") == 2
        else "percentage-annotations.v1.schema.json"
    )
    validate(annotation, schema_name)
    is_v2 = annotation["schema_version"] == 2
    docs, ids = {}, set()
    total = 0
    source_bytes = 0
    for doc in annotation["documents"]:
        document_id = doc["document_id"]
        if document_id in docs or not document_id or not doc["work_family_id"]:
            raise ValueError("Duplicate/empty document or work-family identifier")
        source_path = confined(path.parent, doc["source"]["path"])
        source = read_regular(source_path, MAX_SOURCE_BYTES)
        if len(source) > MAX_SOURCE_BYTES or digest(source) != doc["source"]["sha256"]:
            raise ValueError(f"Source version/hash mismatch: {document_id}")
        source_bytes += len(source)
        if source_bytes > MAX_SOURCE_SET_BYTES:
            raise ValueError("Benchmark source set exceeds the 32 MiB aggregate limit")
        try:
            nodes = node_map(source)
            cell_contexts = table_cell_context_map(source) if is_v2 else {}
        except JATSSourceError as exc:
            if doc["relationships"]:
                raise ValueError(f"Annotated source cannot be parsed safely: {document_id}: {exc}") from exc
            nodes = {}
            cell_contexts = {}
        related_sources: dict[str, dict[str, Any]] = {}
        if is_v2:
            for related in doc["related_sources"]:
                source_id = related["source_id"]
                if source_id in related_sources:
                    raise ValueError(f"Duplicate related-source identifier: {source_id}")
                related_path = confined(path.parent, related["source"]["path"])
                related_data = read_regular(related_path, MAX_SOURCE_BYTES)
                if digest(related_data) != related["source"]["sha256"]:
                    raise ValueError(f"Related source version/hash mismatch: {source_id}")
                source_bytes += len(related_data)
                if source_bytes > MAX_SOURCE_SET_BYTES:
                    raise ValueError("Benchmark source set exceeds the 32 MiB aggregate limit")
                try:
                    related_nodes = node_map(related_data)
                except JATSSourceError as exc:
                    raise ValueError(f"Related evidence source cannot be parsed safely: {source_id}: {exc}") from exc
                related_sources[source_id] = {"record": related, "nodes": related_nodes}
        source_identities = set()
        for relation in doc["relationships"]:
            total += 1
            if total > MAX_ANNOTATIONS:
                raise ValueError("Benchmark exceeds the 20,000-annotation limit")
            identity = relation["relationship_id"]
            if identity in ids:
                raise ValueError(f"Duplicate relationship identifier: {identity}")
            ids.add(identity)
            source_identity = (*_annotation_key(relation), relation["anchor"].get("character_start"), relation["anchor"].get("character_end"))
            if source_identity in source_identities:
                raise ValueError("Duplicate annotated source relationship")
            source_identities.add(source_identity)
            error = check_anchor(relation["anchor"], nodes)
            if error:
                raise ValueError(f"Invalid annotation anchor {identity}: {error}")
            anchor = relation["anchor"]
            text = _text(nodes[(anchor["byte_start"], anchor["byte_end"])])
            if is_v2:
                percent_anchor = relation["percentage_anchor"]
                if (relation["anchor"]["byte_start"] != percent_anchor["byte_start"]
                        or relation["anchor"]["byte_end"] != percent_anchor["byte_end"]
                        or relation["anchor"]["quote"] != percent_anchor["quote"]):
                    raise ValueError(f"Compatibility anchor does not identify the percentage source cell: {identity}")
                main_anchor = relation["anchor"]
                main_text = _text(nodes[(main_anchor["byte_start"], main_anchor["byte_end"])])
                main_start, main_end = main_anchor["character_start"], main_anchor["character_end"]
                if (main_anchor["span_quote"] != main_text[main_start:main_end]
                        or not (main_start <= percent_anchor["character_start"]
                                < percent_anchor["character_end"] <= main_end)):
                    raise ValueError(f"Compatibility anchor does not cover the relationship span: {identity}")
                span_values = {}
                for role in ("numerator_anchor", "percentage_anchor"):
                    a = relation[role]
                    error = check_anchor(a, nodes)
                    if error:
                        raise ValueError(f"Invalid {role} for {identity}: {error}")
                    node_text = _text(nodes[(a["byte_start"], a["byte_end"])])
                    start, end = a["character_start"], a["character_end"]
                    span = node_text[start:end]
                    if a["span_quote"] != span:
                        raise ValueError(f"{role} span quote differs from source: {identity}")
                    span_values[role] = span
                numerator_anchor = relation["numerator_anchor"]
                if (numerator_anchor["byte_start"] == main_anchor["byte_start"]
                        and numerator_anchor["byte_end"] == main_anchor["byte_end"]
                        and not (main_start <= numerator_anchor["character_start"]
                                 < numerator_anchor["character_end"] <= main_end)):
                    raise ValueError(f"Relationship span does not cover its numerator token: {identity}")
                try:
                    numerator_value = int(span_values["numerator_anchor"].replace(",", ""))
                except ValueError as exc:
                    raise ValueError(f"Numerator anchor is not an integer token: {identity}") from exc
                if (not re.fullmatch(INTEGER, span_values["numerator_anchor"])
                        or numerator_value != relation["numerator"]):
                    raise ValueError(f"Numerator anchor differs from declared count: {identity}")
                percent_span = span_values["percentage_anchor"].rstrip("%").strip()
                if percent_span != relation["reported_percent"]:
                    raise ValueError(f"Percentage anchor differs from declared percentage: {identity}")
                contexts = []
                for role, index_key in (("numerator_anchor", "numerator_cell_index"),
                                        ("percentage_anchor", "percentage_cell_index")):
                    a = relation[role]
                    context = cell_contexts.get((a["byte_start"], a["byte_end"]))
                    if context is None:
                        raise ValueError(f"{role} does not identify a table cell: {identity}")
                    if context["cell_index"] != relation[index_key]:
                        raise ValueError(f"{role} cell index differs from source: {identity}")
                    contexts.append(context)
                if any(c["table_id"] != relation["table_id"] for c in contexts):
                    raise ValueError(f"Relationship table identifier differs from source: {identity}")
                if any(c["row_index"] != relation["row_index"] for c in contexts):
                    raise ValueError(f"Relationship row identity differs from source: {identity}")
                if relation["component_index"] >= relation["component_count"]:
                    raise ValueError(f"Component index is outside its declared group: {identity}")
                if relation["component_count"] > 1 and not relation["component_group_id"]:
                    raise ValueError(f"Multiple cell components require a group identity: {identity}")
                for a in relation["scope_evidence"]:
                    error = check_anchor(a, nodes)
                    if error:
                        raise ValueError(f"Invalid population-scope evidence {identity}: {error}")
                if relation["scope_linkage_status"] == "explicit_same_population" and not relation["scope_evidence"]:
                    raise ValueError(f"Explicit population linkage lacks source evidence: {identity}")
                for alternative in relation["alternative_interpretations"]:
                    for a in alternative["evidence"]:
                        error = check_anchor(a, nodes)
                        if error:
                            raise ValueError(f"Invalid alternative-interpretation evidence {identity}: {error}")
                for item in relation["correction_evidence"]:
                    related = related_sources.get(item["source_id"])
                    if related is None or related["record"]["relationship"] != "correction":
                        raise ValueError(f"Correction evidence does not name a registered correction source: {identity}")
                    a = item["anchor"]
                    error = check_anchor(a, related["nodes"])
                    if error:
                        raise ValueError(f"Invalid correction evidence {identity}: {error}")
                    correction_text = _text(related["nodes"][(a["byte_start"], a["byte_end"])])
                    if a["span_quote"] != correction_text[a["character_start"]:a["character_end"]]:
                        raise ValueError(f"Correction evidence span differs from source: {identity}")
                if relation["review_outcome"] == "correction_corroborated" and not relation["correction_evidence"]:
                    raise ValueError(f"Correction-corroborated status lacks source evidence: {identity}")

                denominator = relation["denominator"]
                basis = relation["denominator_basis"]
                explicit_bases = {"cell_ratio", "row_denominator_column", "column_header",
                                  "row_group", "caption_or_footnote", "table_total_row", "reviewer_mapped"}
                if basis in explicit_bases and denominator is None:
                    raise ValueError(f"Explicit denominator basis lacks a denominator: {identity}")
                if basis in {"derived_unresolved", "not_reported"} and denominator is not None:
                    raise ValueError(f"Unresolved denominator must not be credited as explicit: {identity}")
                if basis == "derived_unresolved" and relation["scope_status"] != "derived_unresolved":
                    raise ValueError(f"Derived denominator basis and scope status contradict: {identity}")
                if basis == "not_reported" and relation["scope_status"] != "unknown":
                    raise ValueError(f"Unreported denominator requires unknown scope status: {identity}")
                permitted_evidence_kinds = {
                    "cell_ratio": {"cell_ratio"},
                    "row_denominator_column": {"row_denominator_column"},
                    "column_header": {"column_header"},
                    "row_group": {"row_group"},
                    "caption_or_footnote": {"caption", "footnote"},
                    "table_total_row": {"table_total_row"},
                    "reviewer_mapped": {"reviewer_mapped"},
                }
                if basis in permitted_evidence_kinds and any(
                    item["kind"] not in permitted_evidence_kinds[basis]
                    for item in relation["denominator_evidence"]
                ):
                    raise ValueError(f"Denominator evidence kind contradicts its declared basis: {identity}")
                evidence_values = set()
                for item in relation["denominator_evidence"]:
                    a = item["anchor"]
                    error = check_anchor(a, nodes)
                    if error:
                        raise ValueError(f"Invalid denominator evidence {identity}: {error}")
                    evidence_text = _text(nodes[(a["byte_start"], a["byte_end"])])
                    value = item["value"]
                    anchored_values = {int(m.group("value").replace(",", ""))
                                       for m in _DENOMINATOR_RE.finditer(evidence_text)}
                    anchored_values.update(int(m.group("d").replace(",", ""))
                                           for m in PAIR.finditer(evidence_text) if m.group("d"))
                    if re.fullmatch(INTEGER, evidence_text):
                        anchored_values.add(int(evidence_text.replace(",", "")))
                    total_match = re.fullmatch(
                        rf"\s*(?:(?:Grand|Overall)\s+)?Total\s*[:=\-]?\s*({INTEGER})"
                        r"\s*\(\s*100(?:\.0+)?\s*%\s*\)\s*", evidence_text, re.IGNORECASE)
                    if total_match:
                        anchored_values.add(int(total_match.group(1).replace(",", "")))
                    if value not in anchored_values:
                        raise ValueError(f"Denominator evidence value is absent from source: {identity}")
                    evidence_values.add(value)
                if basis in explicit_bases and (not relation["denominator_evidence"]
                                                 or denominator not in evidence_values):
                    raise ValueError(f"Explicit annotation denominator differs from evidence: {identity}")
                if basis in {"derived_unresolved", "not_reported"} and relation["denominator_evidence"]:
                    raise ValueError(f"Unresolved denominator cannot carry explicit denominator evidence: {identity}")
                if relation["scope_linkage_status"] == "unresolved":
                    if relation["arithmetic_status"] != "not_computed":
                        raise ValueError(f"Unresolved population scope cannot carry computed arithmetic: {identity}")
                elif denominator is None:
                    if relation["arithmetic_status"] != "not_computed":
                        raise ValueError(f"Missing denominator cannot carry computed arithmetic: {identity}")
                else:
                    arithmetic = percentage_recalculation(relation["numerator"], denominator,
                        relation["reported_percent"], relation["precision"])
                    expected = "arithmetic_match" if arithmetic["arithmetic_matches"] else "arithmetic_mismatch_candidate"
                    if relation["arithmetic_status"] != expected:
                        raise ValueError(f"Annotation arithmetic disagrees with its declared operands: {identity}")
            else:
                pairs = [m for m in pairs_in_span(text, anchor.get("character_start", 0), anchor.get("character_end", len(text)))
                         if int(m.group("n").replace(",", "")) == relation["numerator"]
                         and m.group("p") == relation["reported_percent"]]
                if len(pairs) != 1:
                    raise ValueError(f"Annotation numeric tokens are ambiguous or differ from the source: {identity}")
                for denominator_anchor in relation["denominator_evidence"]:
                    error = check_anchor(denominator_anchor, nodes)
                    if error:
                        raise ValueError(f"Invalid denominator evidence {identity}: {error}")
                if relation["scope_status"].startswith("explicit") and not relation["denominator_evidence"]:
                    raise ValueError(f"Explicit denominator lacks source evidence: {identity}")
                denominator = relation["denominator"]
                embedded = pairs[0].group("d")
                if embedded is not None and int(embedded.replace(",", "")) != denominator:
                    raise ValueError(f"Annotation denominator disagrees with embedded n/N: {identity}")
                if relation["scope_status"].startswith("explicit"):
                    evidence_values = set()
                    for a in relation["denominator_evidence"]:
                        evidence_text = _text(nodes[(a["byte_start"], a["byte_end"])])
                        evidence_values.update(int(m.group("value").replace(",", "")) for m in _DENOMINATOR_RE.finditer(evidence_text))
                        evidence_values.update(int(m.group("d").replace(",", "")) for m in PAIR.finditer(evidence_text) if m.group("d"))
                        if re.fullmatch(INTEGER, evidence_text):
                            evidence_values.add(int(evidence_text.replace(",", "")))
                    if denominator is None or denominator not in evidence_values:
                        raise ValueError(f"Explicit annotation denominator differs from source evidence: {identity}")
            if denominator is not None:
                arithmetic = percentage_recalculation(relation["numerator"], denominator,
                    relation["reported_percent"], relation["precision"])
                expected = "arithmetic_match" if arithmetic["arithmetic_matches"] else "arithmetic_mismatch_candidate"
                if expected != relation["arithmetic_status"]:
                    raise ValueError(f"Annotation arithmetic disagrees with its declared operands: {identity}")
        docs[document_id] = {"document": doc, "nodes": nodes}
    return annotation, docs, digest(annotation_bytes)


def taxonomy(reason: str | None, *, missing: bool = False, wrong: bool = False) -> str:
    if wrong:
        return "incorrect_denominator_attribution"
    if missing:
        return "relationship_not_identified"
    if reason and ("spans" in reason or "layout" in reason):
        return "unsupported_table_structure"
    if reason and "adjustment" in reason:
        return "weighted_or_adjusted_percentage_handling"
    if reason and "rounding" in reason:
        return "rounding_interpretation"
    if reason == "percentage_context_not_explicit":
        return "unsupported_scientific_relationship_type"
    return "ambiguous_denominator_scope" if reason else "supported_relationship"


def compare_runs(annotation_path: Path, run_paths: list[Path]) -> dict[str, Any]:
    annotation, docs, annotation_hash = validate_annotations(annotation_path)
    if not 1 <= len(run_paths) <= 10:
        raise ValueError("Provide between one and ten detector runs")
    if sum(len(doc["relationships"]) for doc in annotation["documents"]) * len(run_paths) > 50000:
        raise ValueError("Comparison exceeds the 50,000-outcome limit")
    output_runs, labels = [], set()
    for run_path in run_paths:
        run = load_json(run_path)
        validate(run, "percentage-run.v1.schema.json")
        if run["label"] in labels:
            raise ValueError("Duplicate run label")
        labels.add(run["label"])
        records = {r["document_id"]: r for r in run["documents"]}
        if len(records) != len(run["documents"]) or set(records) != set(docs):
            raise ValueError("Run documents must match the annotation source set exactly")
        metrics: Counter[str] = Counter({key: 0 for key in (
            "parsed_documents", "extraction_failures", "tables_inspected", "relationships_detected",
            "annotated_relationships_surfaced", "arithmetic_matches", "mismatch_candidates", "abstentions",
            "incorrect_denominator_assignments", "parsed_denominator_disagreements", "unresolved_denominator_disagreements",
            "source_anchor_failures", "missed_reference_discrepancies", "matched_reference_discrepancies",
            "candidate_false_positives_against_annotations", "unreviewed_mismatch_candidates",
            "conditional_mismatch_candidates", "unresolved_mismatch_candidates")})
        reasons, causes = Counter(), Counter()
        outcomes, document_results, unannotated = [], [], []
        for document_id in sorted(docs):
            doc, nodes = docs[document_id]["document"], docs[document_id]["nodes"]
            record = records[document_id]
            if record["source_sha256"] != doc["source"]["sha256"]:
                raise ValueError(f"Run source version mismatch: {document_id}")
            if record["status"] == "extraction_failed":
                if record["report_path"] is not None or record["report_sha256"] is not None or not record["reason"]:
                    raise ValueError("An extraction failure must have a reason and no fabricated report")
                metrics["extraction_failures"] += 1
                document_results.append({"document_id": document_id, "source_sha256": record["source_sha256"],
                    "status": "extraction_failed", "reason": record["reason"], "relationships_detected": 0})
                results = []
            else:
                if not record["report_path"] or not record["report_sha256"] or record["reason"] is not None:
                    raise ValueError("A successful extraction needs an integrity-committed report")
                report_path = confined(run_path.parent, record["report_path"])
                report_bytes = read_regular(report_path, MAX_JSON_BYTES)
                if len(report_bytes) > MAX_JSON_BYTES or digest(report_bytes) != record["report_sha256"]:
                    raise ValueError(f"Detector report hash mismatch: {document_id}")
                report = parse_json(report_bytes, report_path)
                if report.get("schema_version") == "research-audit.v1":
                    validate(report, "research-audit.v1.schema.json")
                    if (report["document"]["document_id"] != document_id
                            or report["document"]["input_format"] != "jats"
                            or report["processing"]["status"] != "completed"
                            or report["processing"]["reason"] is not None
                            or report["processing"]["relationships_detected"] != len(report["findings"])):
                        raise ValueError("Audit processing identity/status/count contradicts analyzed manifest record")
                    if report["detector_files"] != run["detector_files"]:
                        raise ValueError("Audit detector identity contradicts run manifest")
                    source_hash = report["document"]["source_sha256"]
                    tables = report["processing"]["tables_inspected"]
                    results = [item["relationship"] for item in report["findings"]]
                else:
                    source_hash, tables, results = report.get("source_sha256"), report.get("tables_inspected"), report.get("results")
                    if report.get("percentage_cells_reviewed") != len(results or []):
                        raise ValueError("Detector report relationship count is inconsistent")
                if source_hash != record["source_sha256"]:
                    raise ValueError(f"Detector report source version mismatch: {document_id}")
                if type(tables) is not int or not 0 <= tables <= 512 or not isinstance(results, list) or len(results) > 1000:
                    raise ValueError("Invalid or unbounded detector report")
                metrics["parsed_documents"] += 1
                metrics["tables_inspected"] += tables
                document_results.append({"document_id": document_id, "source_sha256": source_hash,
                    "status": "analyzed", "tables_inspected": tables, "relationships_detected": len(results)})
            indexed: dict[tuple, list[tuple[int, dict[str, Any], list[str]]]] = defaultdict(list)
            seen_outputs = set()
            for index, relation in enumerate(results):
                if not isinstance(relation, dict) or type(relation.get("numerator")) is not int or not isinstance(relation.get("reported_percent"), str):
                    raise ValueError("Invalid detector relationship")
                # Validate every nested evidence span, including conditional
                # population links that are intentionally not denominator
                # assignments.
                errors = evidence_errors(relation, nodes, record["source_sha256"])
                if relation.get("status") not in {"arithmetic_match", "arithmetic_mismatch_candidate", "scope_ambiguous", "rounding_ambiguous"}:
                    raise ValueError("Unknown detector relationship status")
                denominator = relation.get("denominator")
                if denominator is not None and type(denominator) is not int:
                    raise ValueError("Detector denominator must be an integer or null")
                if relation.get("status") in COMPUTED:
                    arithmetic = percentage_recalculation(relation["numerator"], denominator,
                        relation["reported_percent"], relation.get("display_precision"))
                    expected_status = "arithmetic_match" if arithmetic["arithmetic_matches"] else "arithmetic_mismatch_candidate"
                    if (relation["status"] != expected_status
                            or relation.get("contract_expected_percent") != arithmetic["rounded_percent"]
                            or relation.get("exact_ratio_percent") != arithmetic["exact_ratio_percent"]):
                        raise ValueError("Detector arithmetic is inconsistent with its declared operands")
                evidence = relation.get("evidence", {})
                source_node = nodes.get((evidence.get("byte_start"), evidence.get("byte_end")))
                if source_node is not None:
                    text = _text(source_node)
                    tokens = [m for m in pairs_in_span(text, evidence.get("normalized_character_start", 0), evidence.get("normalized_character_end", len(text))) if int(m.group("n").replace(",", "")) == relation["numerator"] and m.group("p") == relation["reported_percent"]]
                    if not tokens and "count_evidence" in evidence:
                        count_quote = evidence["count_evidence"].get("quote", "").replace(",", "").strip()
                        tokens = [True] if (count_quote.isdigit() and int(count_quote) == relation["numerator"]
                            and text.strip().rstrip("%").strip() == relation["reported_percent"]) else []
                    if len(tokens) != 1:
                        errors.append("detector numeric tokens do not identify one source relationship")
                metrics["source_anchor_failures"] += len(errors)
                try:
                    key = _result_key(relation)
                except (KeyError, TypeError) as exc:
                    raise ValueError("Detector relationship is missing source-anchor fields") from exc
                evidence = relation["evidence"]
                full_key = (*key, evidence.get("normalized_character_start"), evidence.get("normalized_character_end"))
                if full_key in seen_outputs:
                    raise ValueError("Duplicate detector relationship")
                seen_outputs.add(full_key)
                indexed[key].append((index, relation, errors))
                metrics["relationships_detected"] += 1
                status = relation.get("status")
                if status == "arithmetic_match":
                    metrics["arithmetic_matches"] += 1
                elif status == "arithmetic_mismatch_candidate":
                    metrics["mismatch_candidates"] += 1
                else:
                    metrics["abstentions"] += 1
                    reasons[str(relation.get("reason"))] += 1
                if (not errors
                        and relation.get("conditional_calculation", {}).get("arithmetic_matches") is False):
                    metrics["conditional_mismatch_candidates"] += 1
            consumed = set()
            for reference in doc["relationships"]:
                choices = indexed.get(_annotation_key(reference), [])
                if len(choices) > 1:
                    a = reference["anchor"]
                    choices = [choice for choice in choices if
                        choice[1]["evidence"].get("normalized_character_start") == a.get("character_start")
                        and choice[1]["evidence"].get("normalized_character_end") == a.get("character_end")]
                selected = choices[0] if len(choices) == 1 and choices[0][0] not in consumed else None
                relation = selected[1] if selected else None
                if selected:
                    consumed.add(selected[0])
                trusted_span = selected is not None and not selected[2]
                if trusted_span:
                    metrics["annotated_relationships_surfaced"] += 1
                observed_denominator = relation.get("denominator") if relation else None
                different_denominator = observed_denominator is not None and observed_denominator != reference["denominator"]
                unresolved_scope = reference["scope_status"] in {"derived_unresolved", "unknown"}
                computed = trusted_span and relation.get("status") in COMPUTED
                if different_denominator:
                    metrics["parsed_denominator_disagreements"] += 1
                    if unresolved_scope:
                        metrics["unresolved_denominator_disagreements"] += 1
                    elif computed:
                        metrics["incorrect_denominator_assignments"] += 1
                reference_discrepancy = reference["arithmetic_status"] == "arithmetic_mismatch_candidate"
                mismatch = trusted_span and relation.get("status") == "arithmetic_mismatch_candidate"
                credited_mismatch = bool(mismatch and not different_denominator and not unresolved_scope
                                         and observed_denominator is not None)
                if reference_discrepancy and credited_mismatch:
                    metrics["matched_reference_discrepancies"] += 1
                    if reference["review_outcome"] in {"unresolved_scope", "unresolved_rounding"}:
                        metrics["unresolved_mismatch_candidates"] += 1
                elif reference_discrepancy:
                    metrics["missed_reference_discrepancies"] += 1
                elif mismatch:
                    if unresolved_scope:
                        metrics["unresolved_mismatch_candidates"] += 1
                    else:
                        metrics["candidate_false_positives_against_annotations"] += 1
                reason = relation.get("reason") if relation else "not_emitted"
                cause = ("source_extraction_failure" if record["status"] == "extraction_failed" else
                    taxonomy(reason, missing=not trusted_span, wrong=bool(different_denominator and not unresolved_scope)))
                causes[cause] += 1
                outcomes.append({"relationship_id": reference["relationship_id"], "document_id": document_id,
                    "work_family_id": doc["work_family_id"], "source_sha256": record["source_sha256"],
                    "reference_scope": reference["scope_status"], "reference_arithmetic": reference["arithmetic_status"],
                    "reference_review_outcome": reference["review_outcome"],
                    "status": relation.get("status") if relation else "not_emitted", "reason": reason,
                    "source_anchor_valid": trusted_span, "expected_denominator": reference["denominator"],
                    "reference_discrepancy_detected": bool(reference_discrepancy and credited_mismatch),
                    "observed_denominator": observed_denominator, "taxonomy": cause,
                    "conditional_calculation": relation.get("conditional_calculation") if relation else None})
            for index, relation in enumerate(results):
                if index not in consumed:
                    if relation.get("status") == "arithmetic_mismatch_candidate":
                        metrics["unreviewed_mismatch_candidates"] += 1
                    unannotated.append({"document_id": document_id, "status": relation.get("status"),
                        "reason": relation.get("reason"), "numerator": relation.get("numerator"),
                        "reported_percent": relation.get("reported_percent"), "evidence": relation.get("evidence")})
        output_runs.append({"label": run["label"], "detector_revision": run["detector_revision"],
            "detector_files": run["detector_files"], "metrics": dict(sorted(metrics.items())),
            "abstentions_by_reason": dict(sorted(reasons.items())), "error_taxonomy": dict(sorted(causes.items())),
            "documents": document_results, "relationships": outcomes, "unannotated_outputs": unannotated})
    report = {"schema_version": "research-benchmark.v1", "exposure": "development",
        "annotation_sha256": annotation_hash, "document_count": len(docs),
        "work_family_count": len({doc["document"]["work_family_id"] for doc in docs.values()}),
        "annotation_count": sum(len(doc["document"]["relationships"]) for doc in docs.values()),
        "runs": output_runs,
        "limitations": ["Developer-exposed benchmark; no untouched holdout or custodian acceptance evidence.",
            "Arithmetic reference labels and denominator mappings are supplied annotations, not independent scientific adjudication.",
            "Unresolved rounding and derived denominator scopes remain unresolved even when arithmetic matches.",
            "Work-family identifiers are supplied review metadata; unnamed shared datasets can remain undetected.",
            "No independent precision or recall estimate or end-to-end scientific error detection claim is supported."]}
    validate(report, "research-benchmark.v1.schema.json")
    return report


def regression_failures(report: dict[str, Any]) -> list[str]:
    failures = []
    for before, after in zip(report["runs"], report["runs"][1:]):
        a, b = before["metrics"], after["metrics"]
        if b["annotated_relationships_surfaced"] < a["annotated_relationships_surfaced"]:
            failures.append(f"{after['label']} loses annotated extraction coverage")
        before_hits = {r["relationship_id"] for r in before["relationships"] if r["reference_discrepancy_detected"]}
        after_hits = {r["relationship_id"] for r in after["relationships"] if r["reference_discrepancy_detected"]}
        if before_hits - after_hits:
            failures.append(f"{after['label']} loses {len(before_hits - after_hits)} source-bound discrepancy candidates; review any deliberate scope abstention")
        for key in ("incorrect_denominator_assignments", "source_anchor_failures", "candidate_false_positives_against_annotations"):
            if b[key] > a[key]:
                failures.append(f"{after['label']} increases {key}")
    return failures


def comparison_markdown(report: dict[str, Any]) -> str:
    from tools.research_audit import safe_text
    lines = ["# Development percentage comparison", "",
        f"Annotation SHA-256: `{report['annotation_sha256']}`.",
        f"Documents: {report['document_count']}; supplied work families: {report['work_family_count']}; annotated relationships: {report['annotation_count']}.", "",
        "| Metric | " + " | ".join(safe_text(run["label"]) for run in report["runs"]) + " |",
        "|---|" + "---:|" * len(report["runs"])]
    for key in report["runs"][0]["metrics"]:
        lines.append("| " + safe_text(key) + " | " + " | ".join(str(run["metrics"][key]) for run in report["runs"]) + " |")
    for run in report["runs"]:
        lines += ["", f"## {safe_text(run['label'])}", "", f"Detector revision: {safe_text(run['detector_revision'])}.", "",
                  "Abstentions by reason: " + safe_text(json.dumps(run["abstentions_by_reason"], sort_keys=True)), "",
                  "| Relationship | Status | Expected / observed denominator | Reason / taxonomy |", "|---|---|---|---|"]
        for row in run["relationships"]:
            if row["status"] != "arithmetic_match" or row["observed_denominator"] != row["expected_denominator"]:
                lines.append(f"| {safe_text(row['relationship_id'])} | {safe_text(row['status'])} | {row['expected_denominator']} / {row['observed_denominator']} | {safe_text(row['reason'])}; {safe_text(row['taxonomy'])} |")
    lines += ["", *["- " + safe_text(item) for item in report["limitations"]], ""]
    return "\n".join(lines)
