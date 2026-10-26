"""Source mapping tests for the narrow JATS prose sample-flow adapter."""
from __future__ import annotations

from hashlib import sha256

from researchwitness.jats_table_projection import project_jats_tables
from researchwitness.paper_flow_source import (
    FlowArithmeticRelation,
    FlowExclusion,
    FlowPopulation,
    FlowStage,
    FlowTransition,
    map_jats_sample_flows,
)


def _document(paragraph: str):
    source = (
        '<article><front><article-meta><title-group><article-title>Flow test</article-title>'
        '</title-group></article-meta></front><body><sec><title>Results</title><p>'
        + paragraph
        + '</p></sec></body></article>'
    ).encode('utf-8')
    return project_jats_tables(source, include_body_paragraphs=True)


def _explicit_flow(included: int) -> str:
    return (
        'Of the 100 participants in cohort Alpha, we excluded 10 with condition A and '
        '5 with condition B. The exclusion categories were mutually exclusive and exhaustive, '
        'and all remaining participants were included. Finally, '
        f'{included} participants in cohort Alpha were included.'
    )


def test_source_mapped_flow_balances_and_anchors_each_operand_and_relation():
    document = _document(_explicit_flow(85))
    mapped = map_jats_sample_flows(document)

    assert len(mapped) == 1
    result = mapped[0]
    assert result.status == 'FLOW_BALANCED'
    assert result.reason is None
    assert result.arithmetic['status'] == 'FLOW_BALANCED'
    assert [(operand.role, operand.count) for operand in result.operands] == [
        ('total', 100), ('exclusion', 10), ('exclusion', 5), ('included', 85),
    ]
    assert all(operand.source_anchor.source_sha256 == document.source_sha256 for operand in result.operands)
    assert all(operand.source_anchor.element_path.endswith('/p[1]') for operand in result.operands)
    assert all(operand.source_anchor.quote for operand in result.operands)
    assert result.relation_anchor.quote
    assert result.relation_anchor.source_sha256 == document.source_sha256
    assert isinstance(result.population, FlowPopulation)
    assert all(isinstance(stage, FlowStage) and stage.source_anchor.quote for stage in result.stages)
    assert all(isinstance(edge, FlowTransition) and edge.source_anchor.quote for edge in result.transitions)
    assert all(isinstance(item, FlowExclusion) and item.count_anchor.quote and item.reason_anchor.quote
               for item in result.exclusions)
    assert isinstance(result.arithmetic_relation, FlowArithmeticRelation)
    assert result.arithmetic_relation.disjoint is True
    assert result.arithmetic_relation.exhaustive is True
    assert len(result.arithmetic_relation.operand_anchors) == len(result.operands)
    # Byte offsets refer to the ORIGINAL whole XML paragraph, not token spans;
    # shortened normalized operand quotes are a separate projection.
    assert all(operand.source_anchor.start_byte is not None for operand in result.operands)
    assert all(operand.source_anchor.end_byte is not None for operand in result.operands)
    assert all(operand.source_anchor.start_byte == document.paragraphs[0].source_anchor.start_byte
               for operand in result.operands)
    assert all(operand.source_anchor.end_byte == document.paragraphs[0].source_anchor.end_byte
               for operand in result.operands)


def test_source_mapped_flow_reports_arithmetic_mismatch_as_candidate():
    result = map_jats_sample_flows(_document(_explicit_flow(80)))[0]

    assert result.status == 'FLOW_ARITHMETIC_CANDIDATE'
    assert result.arithmetic['candidate'] == {
        'expected_count': 85,
        'reported_count': 80,
        'difference': -5,
        'source_anchors': [edge.source_anchor for edge in result.relation.edges],
    }
    assert len(result.operands) == 4
    assert result.relation_anchor.source_format == 'jats_xml'


def test_explicit_sequential_subtraction_is_an_eligible_relation():
    paragraph = (
        'Of the 100 participants in cohort Alpha, we excluded 10 with condition A and '
        '5 with condition B. Each subsequent exclusion was subtracted from the remaining '
        'participants, and all remaining participants were included. Finally, '
        '85 participants in cohort Alpha were included.'
    )
    result = map_jats_sample_flows(_document(paragraph))[0]

    assert result.status == 'FLOW_BALANCED'
    assert result.arithmetic_relation.sequential is True
    assert {transition.operation for transition in result.transitions} == {
        'subtract_remaining', 'equals_after_operations',
    }


def test_unknown_or_possible_overlap_never_becomes_arithmetic_candidate():
    unknown = (
        'Of the 100 participants in cohort Alpha, we excluded 10 with condition A and '
        '5 with condition B. Finally, 85 participants in cohort Alpha were included.'
    )
    overlapping = (
        'Of the 100 participants in cohort Alpha, we excluded 10 with condition A and '
        '5 with condition B. The exclusion categories may overlap. Finally, '
        '85 participants in cohort Alpha were included.'
    )

    unknown_result = map_jats_sample_flows(_document(unknown))[0]
    overlap_result = map_jats_sample_flows(_document(overlapping))[0]
    assert unknown_result.status == 'FLOW_RELATION_AMBIGUOUS'
    assert unknown_result.reason == 'FLOW_DISJOINTNESS_EXHAUSTIVENESS_OR_SEQUENCE_NOT_EXPLICIT'
    assert unknown_result.arithmetic is None
    assert unknown_result.arithmetic_relation.operator is None
    assert all(not transition.explicit and transition.operation is None
               for transition in unknown_result.transitions)
    assert overlap_result.status == 'FLOW_RELATION_AMBIGUOUS'
    assert overlap_result.reason == 'FLOW_RELATION_CUE_CONFLICT'
    assert overlap_result.arithmetic is None


def test_source_mapper_rejects_mismatched_count_units_and_groups():
    unit_mismatch = (
        'Of the 100 participants in cohort Alpha, we excluded 10 participants with condition A and '
        '5 records with condition B. The exclusion categories were mutually exclusive and exhaustive, '
        'and all remaining participants were included. Finally, 85 participants in cohort Alpha were included.'
    )
    group_mismatch = (
        'Of the 100 control group participants, we excluded 10 with condition A and '
        '5 with condition B. The exclusion categories were mutually exclusive and exhaustive, '
        'and all remaining participants were included. Finally, 85 intervention group participants were included.'
    )

    unit_result = map_jats_sample_flows(_document(unit_mismatch))[0]
    group_result = map_jats_sample_flows(_document(group_mismatch))[0]
    assert unit_result.status == 'UNSUPPORTED'
    assert unit_result.reason == 'FLOW_OPERAND_UNIT_MISMATCH'
    assert group_result.status == 'UNSUPPORTED'
    assert group_result.reason == 'FLOW_OPERAND_SCOPE_MISMATCH'
    assert unit_result.arithmetic is None
    assert group_result.arithmetic is None


def test_ambiguous_multi_exclusion_flow_remains_non_candidate_regression():
    # Synthetic analogue for a flow paragraph whose exclusions are not
    # declared disjoint, exhaustive, or sequential.
    paragraph = (
        'Of the 1000 participants in cohort Alpha at baseline, we excluded 100 people '
        'below the age threshold, 150 with condition A, 30 with incomplete outcome '
        'information, and 20 without a follow-up response. Finally, 700 participants '
        'were included for analysis, and 500 of them provided a specimen at baseline.'
    )
    result = map_jats_sample_flows(_document(paragraph))[0]

    assert result.status == 'FLOW_RELATION_AMBIGUOUS'
    assert result.reason == 'FLOW_DISJOINTNESS_EXHAUSTIVENESS_OR_SEQUENCE_NOT_EXPLICIT'
    assert [operand.count for operand in result.operands] == [1000, 100, 150, 30, 20, 700]
    assert result.arithmetic is None
    assert result.relation is None
    assert result.relation_anchor.source_format == 'jats_xml'
    assert isinstance(result.population, FlowPopulation)
    assert len(result.stages) == 6
    assert len(result.transitions) == 5
    assert len(result.exclusions) == 4
    assert result.arithmetic_relation.disjoint is None
    assert result.arithmetic_relation.exhaustive is None
    assert all(exclusion.count_anchor.source_sha256 == result.operands[0].source_anchor.source_sha256
               for exclusion in result.exclusions)


def test_source_mapper_does_not_apply_to_non_jats_documents():
    source = b'Of the 100 participants, we excluded 10 and 5. Finally, 85 participants were included.'
    digest = sha256(source).hexdigest()
    # A minimal PaperDocument parsed from text is intentionally not available;
    # direct construction keeps this test focused on the public format gate.
    from researchwitness.paper_document import PaperDocument, Paragraph, SourceAnchor

    anchor = SourceAnchor('source.md', digest, 'markdown', '/p[1]', source.decode())
    paragraph = Paragraph(source.decode(), anchor)
    document = PaperDocument('1.0', 'source.md', digest, 'markdown', 'Test', (), (paragraph,), (), (), ())
    assert map_jats_sample_flows(document) == ()


def test_source_mapper_respects_explicit_result_bound():
    paragraphs = ''.join(f'<p>{_explicit_flow(85)}</p>' for _ in range(4))
    source = (
        '<article><body><sec><title>Results</title>' + paragraphs + '</sec></body></article>'
    ).encode('utf-8')
    document = project_jats_tables(source, include_body_paragraphs=True)

    assert len(map_jats_sample_flows(document, limit=2)) == 2


def test_default_table_projection_does_not_include_body_prose():
    paragraph = _explicit_flow(80)
    source = ('<article><body><p>' + paragraph + '</p></body></article>').encode()
    plain = project_jats_tables(source)
    with_text = project_jats_tables(source, include_body_paragraphs=True)
    assert not plain.paragraphs
    assert len(with_text.paragraphs) == 1
    assert with_text.paragraphs[0].source_anchor.source_sha256 == sha256(source).hexdigest()


def test_body_versus_caption_abstract_and_figure_do_not_conflate():
    from researchwitness import jats_product

    text = _explicit_flow(80)
    source = (
        '<article><front><article-meta><abstract><p>' + text +
        '</p></abstract></article-meta></front><body><sec><p>' + text +
        '</p></sec><table-wrap><caption><p>' + text +
        '</p></caption><table><tr><td>none</td></tr></table></table-wrap>'
        '<fig><caption><p>' + text +
        '</p></caption></fig></body><back><p>' + text +
        '</p></back></article>'
    ).encode()
    result = jats_product.make_report(source, "invented", False, include_prose_flows=True)
    flow = result["sample_flow_review"]
    assert flow["eligible_body_paragraphs"] == 1
    assert flow["relations_mapped"] == 1
    assert flow["candidate_count"] == 1
    assert "body_paragraphs_excluded:2" in flow["projected_source_warnings"]
    assert flow["whole_article_coverage_established"] is False


def test_no_cross_paragraph_composition_or_automatic_scope_inference():
    from researchwitness import jats_product

    p1 = "Of the 100 participants in cohort Alpha, we excluded 10 with condition A and 5 with condition B."
    p2 = ("The exclusion categories were mutually exclusive and exhaustive, "
          "and all remaining participants were included. Finally, "
          "80 participants in cohort Alpha were included.")
    xml = f"<article><body><sec><p>{p1}</p><p>{p2}</p></sec></body></article>".encode()
    report = jats_product.make_report(xml, "invented", False, include_prose_flows=True)
    assert report["sample_flow_review"]["eligible_body_paragraphs"] == 2
    assert report["sample_flow_review"]["candidate_count"] == 0
    assert report["sample_flow_review"]["relations_mapped"] == 0


def test_no_unsafe_inline_xrefs_and_no_hidden_paragraph_truncation():
    from researchwitness import jats_product

    text = _explicit_flow(80)
    data = (
        '<article><body><p>' + text + '</p><p><xref ref-type="bibr" rid="x">'
        + text + '</xref></p></body></article>'
    ).encode()
    flow = jats_product.make_report(data, "invented", False,
                                    include_prose_flows=True)["sample_flow_review"]
    assert flow["relations_mapped"] == 1
    assert flow["candidate_count"] == 1
    assert "body_paragraphs_excluded:1" in flow["projected_source_warnings"]
    nested_source = (
        '<article><body><p><italic><xref ref-type="bibr" rid="r1">'
        + text + '</xref></italic></p></body></article>'
    ).encode()
    nested = jats_product.make_report(
        nested_source, "invented", False, include_prose_flows=True
    )["sample_flow_review"]
    assert nested["candidate_count"] == 0
    assert nested["relations_mapped"] == 0
    assert "body_paragraphs_excluded:1" in nested["projected_source_warnings"]
    assert flow["whole_article_coverage_established"] is False


def test_bundle_replay_preserves_all_flow_outcomes(tmp_path):
    from pathlib import Path
    import json
    from researchwitness import jats_product

    example = Path(__file__).resolve().parents[1] / "examples/synthetic-jats/prose-flow.xml"
    root = tmp_path / "review"
    created = jats_product.audit_source(example, root, "invented", include_prose_flows=True)
    report = json.loads((root / "report.json").read_bytes())
    flow = report["sample_flow_review"]
    assert flow["relations_mapped"] == 3
    assert flow["candidate_count"] == 1
    assert flow["status_counts"] == {
        "FLOW_ARITHMETIC_CANDIDATE": 1,
        "FLOW_BALANCED": 1,
        "FLOW_RELATION_AMBIGUOUS": 1,
    }
    assert all(case["review_state"] == "unreviewed" for case in flow["cases"])
    assert all(case["scientific_error_status"] == "not_established" for case in flow["cases"])
    assert jats_product.replay_bundle(root, created["manifest_sha256"])["status"] == "verified"
    assert "Opt-in JATS prose" in (root / "report.html").read_text(encoding="utf-8")


def test_report_replay_rejects_forged_candidate_even_with_rehashed_manifest(tmp_path):
    import json
    from pathlib import Path
    import pytest
    from researchwitness import jats_product

    example = Path(__file__).resolve().parents[1] / "examples/synthetic-jats/prose-flow.xml"
    root = tmp_path / "review"
    jats_product.audit_source(example, root, "invented", include_prose_flows=True)
    saved = json.loads((root / "report.json").read_bytes())
    saved["sample_flow_review"]["cases"][0]["flow"]["status"] = "FLOW_BALANCED"
    tampered = jats_product.canonical_json(saved)
    (root / "report.json").write_bytes(tampered)
    manifest = json.loads((root / "manifest.json").read_bytes())
    manifest["files"]["report.json"] = {
        "sha256": jats_product.digest(tampered), "bytes": len(tampered),
    }
    (root / "manifest.json").write_bytes(jats_product.canonical_json(manifest))
    with pytest.raises(ValueError, match="replay disagrees"):
        jats_product.replay_bundle(root)


def test_sample_flow_html_escapes_untrusted_normalized_paragraph(tmp_path):
    from researchwitness import jats_product

    text = _explicit_flow(80)
    # Suffix falls inside the emitted normalized source context.
    text = text.replace("were mutually exclusive", "were &lt;script&gt; mutually exclusive")
    source = tmp_path / "flow.xml"
    source.write_bytes(("<article><body><p>" + text + "</p></body></article>").encode())
    target = tmp_path / "review"
    jats_product.audit_source(source, target, "invented", include_prose_flows=True)
    html = (target / "report.html").read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_parser_rejects_external_entity_without_leaking_source(tmp_path):
    import pytest
    from researchwitness import jats_product

    path = tmp_path / "bad.xml"
    path.write_bytes(b'<!DOCTYPE a [ <!ENTITY secret SYSTEM "file:///etc/passwd"> ]>'
                     b'<article><body><p>&secret;</p></body></article>')
    result_dir = tmp_path / "private"
    with pytest.raises(ValueError):
        jats_product.audit_source(path, result_dir, "invented", include_prose_flows=True)
    assert not result_dir.exists()


def test_bounded_body_paragraph_count_fails_instead_of_truncating(monkeypatch):
    import pytest
    import researchwitness.jats_table_projection as table

    monkeypatch.setattr(table, "MAX_BODY_PARAGRAPHS", 1)
    source = b'<article><body><p>A</p><p>B</p></body></article>'
    with pytest.raises(ValueError, match="paragraph limit"):
        table.project_jats_tables(source, include_body_paragraphs=True)


def test_cli_installed_option_and_default_remain_separate(tmp_path):
    from pathlib import Path
    import subprocess
    import sys
    import json
    from researchwitness import jats_product

    root = Path(__file__).resolve().parents[1]
    source = root / "examples/synthetic-jats/prose-flow.xml"
    normal = tmp_path / "default"
    jats_product.audit_source(source, normal, "invented")
    assert "sample_flow_review" not in json.loads((normal / "report.json").read_bytes())
    review = tmp_path / "flows"
    result = subprocess.run(
        [sys.executable, "-m", "researchwitness", "audit-jats", str(source),
         "--document-id", "invented", "--output-dir", str(review),
         "--include-prose-flows"], cwd=root, text=True, capture_output=True, timeout=35)
    assert result.returncode == 0, result.stderr
    replay = subprocess.run(
        [sys.executable, "-m", "researchwitness", "replay-jats", str(review)],
        cwd=root, text=True, capture_output=True, timeout=35)
    assert replay.returncode == 0, replay.stderr


def test_explicit_negated_and_unrelated_partition_terms_do_not_qualify():
    from researchwitness import jats_product

    qualified = _explicit_flow(80)
    variants = (
        qualified.replace("were mutually exclusive", "were not mutually exclusive"),
        qualified.replace("were mutually exclusive", "were neither mutually exclusive nor disjoint"),
        qualified.replace("The exclusion categories were", "The diagnosis categories were"),
    )
    for text in variants:
        raw = ("<article><body><p>" + text + "</p></body></article>").encode()
        report = jats_product.make_report(raw, "invented", False,
                                          include_prose_flows=True)
        cases = report["sample_flow_review"]["cases"]
        assert len(cases) == 1
        assert cases[0]["flow"]["status"] == "FLOW_RELATION_AMBIGUOUS"
        assert report["sample_flow_review"]["candidate_count"] == 0


def test_displaced_quote_is_not_counted_as_primary_research_prose():
    from researchwitness import jats_product

    text = _explicit_flow(80)
    raw = (
        '<article><body><disp-quote><p>Illustrative example: ' + text +
        '</p></disp-quote><sec><p>Unrelated results.</p></sec></body></article>'
    ).encode()
    report = jats_product.make_report(raw, "invented", False,
                                      include_prose_flows=True)
    flow = report["sample_flow_review"]
    assert flow["candidate_count"] == 0
    assert flow["relations_mapped"] == 0
    assert flow["body_paragraphs_observed"] == 2
    assert flow["body_paragraphs_excluded"] == 1
    assert flow["whole_article_coverage_established"] is False


def test_flow_relation_over_cap_refuses_before_creating_output(monkeypatch, tmp_path):
    from researchwitness import jats_product, paper_flow_source

    xml = tmp_path / "overlimit.xml"
    xml.write_bytes(
        ("<article><body><p>" + _explicit_flow(80) +
         "</p><p>" + _explicit_flow(85) + "</p></body></article>").encode()
    )
    monkeypatch.setattr(paper_flow_source, "MAX_MAPPED_RELATIONS", 1)
    out = tmp_path / "not-created"
    import pytest
    with pytest.raises(ValueError, match="relation limit"):
        jats_product.audit_source(xml, out, "invented", include_prose_flows=True)
    assert not out.exists()
