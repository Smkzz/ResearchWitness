"""Explicit sample-flow graph types and conservative arithmetic validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .paper_document import SourceAnchor


@dataclass(frozen=True, slots=True)
class FlowScope:
    population: str | None
    group: str | None
    timepoint: str | None

    def key(self) -> tuple[str, str, str] | None:
        values = (self.population, self.group, self.timepoint)
        if any(value is None or not value.strip() for value in values):
            return None
        return tuple(value.casefold().strip() for value in values if value is not None)


@dataclass(frozen=True, slots=True)
class FlowNode:
    identifier: str
    label: str
    count: int
    scope: FlowScope
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class FlowEdge:
    source: str
    target: str
    operation: str
    explicit: bool
    disjoint: bool | None
    exhaustive: bool | None
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class FlowOperation:
    result_node: str
    input_nodes: tuple[str, ...]
    operator: str
    explicitly_stated: bool


@dataclass(frozen=True, slots=True)
class FlowRelation:
    nodes: tuple[FlowNode, ...]
    edges: tuple[FlowEdge, ...]
    operation: FlowOperation


def check_flow_relation(relation: FlowRelation) -> dict[str, Any]:
    """Check only a same-scope, explicit, disjoint and exhaustive integer flow."""
    node_by_id = {node.identifier: node for node in relation.nodes}
    operation = relation.operation
    if len(node_by_id) != len(relation.nodes):
        return {'status': 'FLOW_RELATION_AMBIGUOUS', 'reason': 'DUPLICATE_FLOW_NODE_ID', 'candidate': None}
    result = node_by_id.get(operation.result_node)
    inputs = [node_by_id.get(node_id) for node_id in operation.input_nodes]
    if result is None or any(node is None for node in inputs):
        return {'status': 'FLOW_RELATION_AMBIGUOUS', 'reason': 'FLOW_NODE_MISSING', 'candidate': None}
    concrete_inputs = [node for node in inputs if node is not None]
    if (len(concrete_inputs) < 2 or len(set(operation.input_nodes)) != len(operation.input_nodes)
            or operation.result_node in operation.input_nodes):
        return {'status': 'FLOW_RELATION_AMBIGUOUS', 'reason': 'FLOW_OPERATION_SHAPE_UNSUPPORTED', 'candidate': None}
    all_nodes = [result, *concrete_inputs]
    if any(type(node.count) is not int or node.count < 0 or node.count > 1_000_000_000_000 for node in all_nodes):
        return {'status': 'FLOW_RELATION_AMBIGUOUS', 'reason': 'FLOW_COUNT_OUT_OF_BOUNDS', 'candidate': None}
    scope_keys = [node.scope.key() for node in [result, *concrete_inputs]]
    if None in scope_keys or len(set(scope_keys)) != 1:
        return {'status': 'FLOW_RELATION_AMBIGUOUS', 'reason': 'SCOPE_MISMATCH_OR_INCOMPLETE', 'candidate': None}
    if operation.operator == 'subtract':
        expected_edges = {
            *((operation.input_nodes[0], excluded_id) for excluded_id in operation.input_nodes[1:]),
            (operation.input_nodes[0], operation.result_node),
        }
    elif operation.operator == 'add':
        expected_edges = {(node_id, operation.result_node) for node_id in operation.input_nodes}
    else:
        return {'status': 'FLOW_RELATION_AMBIGUOUS', 'reason': 'UNSUPPORTED_FLOW_OPERATOR', 'candidate': None}
    actual_edges = [(edge.source, edge.target) for edge in relation.edges]
    if (not operation.explicitly_stated or len(actual_edges) != len(set(actual_edges))
            or set(actual_edges) != expected_edges):
        return {'status': 'FLOW_RELATION_AMBIGUOUS', 'reason': 'FLOW_GRAPH_DOES_NOT_MATCH_OPERATION', 'candidate': None}
    relevant_edges = list(relation.edges)
    expected_edge_operations = {
        (operation.input_nodes[0], operation.result_node): {'equals_after_operations', operation.operator}
    } if operation.operator == 'subtract' else {}
    if operation.operator == 'subtract':
        for excluded_id in operation.input_nodes[1:]:
            expected_edge_operations[(operation.input_nodes[0], excluded_id)] = {
                'subtract', 'subtract_remaining', 'remove_duplicates',
            }
    else:
        expected_edge_operations = {
            (node_id, operation.result_node): {'add', 'sum'} for node_id in operation.input_nodes
        }
    if (not relevant_edges
            or any(not edge.explicit or edge.disjoint is not True or edge.exhaustive is not True
                   or edge.operation not in expected_edge_operations.get((edge.source, edge.target), set())
                   for edge in relevant_edges)):
        return {'status': 'FLOW_RELATION_AMBIGUOUS', 'reason': 'OVERLAP_NOT_RULED_OUT_OR_RELATION_NOT_EXPLICIT', 'candidate': None}
    if operation.operator == 'subtract':
        expected = concrete_inputs[0].count - sum(node.count for node in concrete_inputs[1:])
    elif operation.operator == 'add':
        expected = sum(node.count for node in concrete_inputs)
    if expected == result.count:
        return {'status': 'FLOW_BALANCED', 'reason': None, 'candidate': None}
    return {
        'status': 'FLOW_ARITHMETIC_CANDIDATE',
        'reason': None,
        'candidate': {
            'expected_count': expected,
            'reported_count': result.count,
            'difference': result.count - expected,
            'source_anchors': [edge.source_anchor for edge in relevant_edges],
        },
    }
