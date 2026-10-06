"""Source mapping tests for the narrow JATS prose sample-flow adapter."""
from __future__ import annotations

from hashlib import sha256

from researchwitness.jats import parse_jats
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
    return parse_jats(source, 'sample.xml')


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
    # JATS paragraph text is a projection; the adapter must not invent original
    # XML byte offsets for token-level quotes.
    assert all(operand.source_anchor.start_byte is None for operand in result.operands)


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
    document = parse_jats(source, 'sample.xml')

    assert len(map_jats_sample_flows(document, limit=2)) == 2
