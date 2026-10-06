"""Identity-gated comparison of source-anchored numeric assertions."""
from researchwitness.cross_section import compare_numeric_assertions
from researchwitness.paper_document import NumericAssertion, SourceAnchor


def _assertion(value: str, *, population='participants', group='treatment', outcome='response',
               timepoint='week 12', adjustment_status='unadjusted'):
    return NumericAssertion(
        value=value,
        unit='percent',
        statistic_type='proportion_percent',
        numerator=None,
        denominator=None,
        population=population,
        group=group,
        outcome=outcome,
        timepoint=timepoint,
        adjustment_status=adjustment_status,
        source_anchor=SourceAnchor('source.xml', 'b' * 64, 'jats_xml', '/article[1]/p[1]', value),
        structural_provenance=('jats:prose',),
    )


def test_same_complete_identity_with_disjoint_rounding_intervals_is_a_candidate():
    result = compare_numeric_assertions([_assertion('12.0'), _assertion('18.0')])
    assert len(result['candidates']) == 1
    assert result['candidates'][0]['type'] == 'CROSS_SECTION_NUMERIC_CONTRADICTION'
    assert result['possible_scope_differences'] == []


def test_nearby_values_with_different_timepoints_are_not_contradictions():
    result = compare_numeric_assertions([_assertion('12.0'), _assertion('18.0', timepoint='baseline')])
    assert result['candidates'] == []
    assert result['possible_scope_differences'] == []


def test_incomplete_identity_can_only_create_a_scope_note():
    result = compare_numeric_assertions([_assertion('12.0', timepoint=None), _assertion('18.0', timepoint=None)])
    assert result['candidates'] == []
    assert len(result['possible_scope_differences']) == 1
    assert result['possible_scope_differences'][0]['status'] == 'POSSIBLE_SCOPE_DIFFERENCE'
