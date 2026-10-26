"""Operand-level flow and 2x2 calculation contracts."""
from __future__ import annotations

from researchwitness.paper_flow import (
    FlowEdge, FlowNode, FlowOperation, FlowRelation, FlowScope, check_flow_relation,
)
from researchwitness.paper_document import SourceAnchor
from researchwitness.paper_statistics import recompute_two_by_two


def _anchor(path: str) -> SourceAnchor:
    return SourceAnchor('source.xml', 'a' * 64, 'jats_xml', path, 'quoted value')


def _flow(disjoint: bool | None, exhaustive: bool | None, scope: FlowScope | None = None):
    scope = scope or FlowScope('participants', 'all', 'baseline')
    nodes = (
        FlowNode('start', 'starting cohort', 100, scope, _anchor('/start')),
        FlowNode('removed', 'excluded', 10, scope, _anchor('/removed')),
        FlowNode('included', 'analyzed', 85, scope, _anchor('/included')),
    )
    edges = (
        FlowEdge('start', 'removed', 'subtract', True, disjoint, exhaustive, _anchor('/edge1')),
        FlowEdge('start', 'included', 'equals_after_operations', True, disjoint, exhaustive, _anchor('/edge2')),
    )
    return FlowRelation(nodes, edges, FlowOperation('included', ('start', 'removed'), 'subtract', True))


def test_flow_model_emits_candidate_only_when_scope_and_additivity_are_explicit():
    ambiguous = check_flow_relation(_flow(None, None))
    assert ambiguous['status'] == 'FLOW_RELATION_AMBIGUOUS'
    assert ambiguous['candidate'] is None

    supported_mismatch = check_flow_relation(_flow(True, True))
    assert supported_mismatch['status'] == 'FLOW_ARITHMETIC_CANDIDATE'
    assert supported_mismatch['candidate']['expected_count'] == 90
    assert supported_mismatch['candidate']['reported_count'] == 85

    balanced = _flow(True, True)
    balanced_nodes = tuple(
        FlowNode(node.identifier, node.label, 90 if node.identifier == 'included' else node.count,
                 node.scope, node.source_anchor) for node in balanced.nodes
    )
    assert check_flow_relation(FlowRelation(balanced_nodes, balanced.edges, balanced.operation))['status'] == 'FLOW_BALANCED'


def test_flow_model_refuses_scope_mismatch():
    relation = _flow(True, True)
    nodes = list(relation.nodes)
    nodes[-1] = FlowNode('included', 'analyzed', 85, FlowScope('participants', 'arm A', 'baseline'), _anchor('/included'))
    result = check_flow_relation(FlowRelation(tuple(nodes), relation.edges, relation.operation))
    assert result['status'] == 'FLOW_RELATION_AMBIGUOUS'
    assert result['candidate'] is None


def test_flow_model_refuses_edges_that_do_not_encode_declared_operation():
    relation = _flow(True, True)
    unrelated = FlowEdge('removed', 'included', 'add', True, True, True, _anchor('/unrelated'))
    result = check_flow_relation(FlowRelation(relation.nodes, relation.edges + (unrelated,), relation.operation))
    assert result['status'] == 'FLOW_RELATION_AMBIGUOUS'
    assert result['reason'] == 'FLOW_GRAPH_DOES_NOT_MATCH_OPERATION'
    assert result['candidate'] is None


def test_sequential_exclusions_and_prisma_record_counts_use_explicit_operations():
    scope = FlowScope('participants', 'all', 'baseline')
    participants = FlowRelation(
        nodes=(
            FlowNode('start', 'starting cohort', 100, scope, _anchor('/start')),
            FlowNode('first', 'first exclusion', 10, scope, _anchor('/first')),
            FlowNode('second', 'subsequent exclusion', 5, scope, _anchor('/second')),
            FlowNode('included', 'analysis cohort', 85, scope, _anchor('/included')),
        ),
        edges=(
            FlowEdge('start', 'first', 'subtract', True, True, True, _anchor('/edge1')),
            FlowEdge('start', 'second', 'subtract_remaining', True, True, True, _anchor('/edge2')),
            FlowEdge('start', 'included', 'equals_after_operations', True, True, True, _anchor('/edge3')),
        ),
        operation=FlowOperation('included', ('start', 'first', 'second'), 'subtract', True),
    )
    assert check_flow_relation(participants)['status'] == 'FLOW_BALANCED'

    records_scope = FlowScope('records', 'all databases', 'search date')
    prisma = FlowRelation(
        nodes=(
            FlowNode('identified', 'records identified', 120, records_scope, _anchor('/identified')),
            FlowNode('duplicates', 'duplicates removed', 25, records_scope, _anchor('/duplicates')),
            FlowNode('screened', 'records screened', 95, records_scope, _anchor('/screened')),
        ),
        edges=(
            FlowEdge('identified', 'duplicates', 'remove_duplicates', True, True, True, _anchor('/edge4')),
            FlowEdge('identified', 'screened', 'equals_after_operations', True, True, True, _anchor('/edge5')),
        ),
        operation=FlowOperation('screened', ('identified', 'duplicates'), 'subtract', True),
    )
    assert check_flow_relation(prisma)['status'] == 'FLOW_BALANCED'


def test_two_by_two_risk_ratio_odds_ratio_and_difference_are_exact_inputs():
    common = dict(
        exposed_events=10, exposed_non_events=90, reference_events=20, reference_non_events=80,
        reference_group_explicit=True, timepoint_explicit=True, adjustment_status='unadjusted',
    )
    rr = recompute_two_by_two(**common, measure='risk_ratio', reported='0.5')
    assert rr['status'] == 'CONSISTENT_WITH_ROUNDING'
    assert (rr['exact_numerator'], rr['exact_denominator']) == ('1', '2')
    or_result = recompute_two_by_two(**common, measure='odds_ratio', reported='0.444')
    assert or_result['status'] == 'CONSISTENT_WITH_ROUNDING'
    diff = recompute_two_by_two(**common, measure='difference_in_proportions', reported='-0.1')
    assert diff['status'] == 'CONSISTENT_WITH_ROUNDING'


def test_two_by_two_mismatch_is_only_an_arithmetic_candidate():
    result = recompute_two_by_two(
        exposed_events=10, exposed_non_events=90, reference_events=20, reference_non_events=80,
        measure='risk_ratio', reported='0.8', reference_group_explicit=True,
        timepoint_explicit=True, adjustment_status='unadjusted',
    )
    assert result['status'] == 'ARITHMETIC_CANDIDATE'
    assert result['candidate']['reported'] == '0.8'


def test_two_by_two_returns_unsupported_for_adjustment_unknown_or_zero_policy():
    inputs = dict(
        exposed_events=10, exposed_non_events=90, reference_events=20, reference_non_events=80,
        measure='risk_ratio', reported='0.5', reference_group_explicit=True, timepoint_explicit=True,
    )
    assert recompute_two_by_two(**inputs, adjustment_status='unknown')['status'] == 'UNSUPPORTED'
    zero = recompute_two_by_two(
        exposed_events=10, exposed_non_events=0, reference_events=20, reference_non_events=80,
        measure='odds_ratio', reported='2', reference_group_explicit=True,
        timepoint_explicit=True, adjustment_status='unadjusted',
    )
    assert zero['reason'] == 'ZERO_CELL_POLICY_UNSPECIFIED'


def test_two_by_two_rounds_half_unit_ties_away_from_zero_and_caps_operands():
    common = dict(
        exposed_events=1, exposed_non_events=7, reference_events=0, reference_non_events=8,
        measure='difference_in_proportions', reference_group_explicit=True,
        timepoint_explicit=True, adjustment_status='unadjusted',
    )
    # 0.125 - 0% rounds to 0.13 under the contract's ROUND_HALF_UP rule.
    tie = recompute_two_by_two(**common, reported='0.12')
    assert tie['status'] == 'ARITHMETIC_CANDIDATE'
    assert tie['recomputed_at_display_precision'] == '0.13'
    too_large = recompute_two_by_two(
        **{**common, 'exposed_events': 1_000_000_001}, reported='100',
    )
    assert too_large['status'] == 'UNSUPPORTED'
    assert too_large['reason'] == 'RESOURCE_LIMIT_EXCEEDED'
