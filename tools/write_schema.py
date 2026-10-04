"""Generate the v1 interchange schema. Cross-file and arithmetic checks live in the core."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def obj(properties, required=None, **kwargs):
    return {
        'type': 'object',
        'properties': properties,
        'required': list(properties) if required is None else required,
        'additionalProperties': False,
        **kwargs,
    }


def text(n):
    return {'type': 'string', 'minLength': 1, 'maxLength': n}


def arr(item, lo=0, hi=64):
    return {'type': 'array', 'items': item, 'minItems': lo, 'maxItems': hi}


def enum(*values):
    return {'enum': list(values)}


def ref(name):
    return {'$ref': '#/$defs/' + name}


def make():
    rational = {
        'type': 'string',
        'maxLength': 130,
        'pattern': r'^-?(?:0|[1-9][0-9]{0,63})(?:/[1-9][0-9]{0,63})?$',
    }
    defs = {
        'hash': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
        'identifier': {
            'type': 'string',
            'minLength': 1,
            'maxLength': 100,
            'pattern': '^[A-Za-z0-9_.-]+$',
        },
        'rational': rational,
        'strings': dict(arr(text(4000), 1), uniqueItems=True),
        'radical': obj({
            'constant': ref('rational'),
            'terms': arr(obj({'coefficient': ref('rational'), 'radicand': ref('rational')}), hi=32),
        }),
        'bounds': obj({
            'lower': ref('rational'),
            'upper': ref('rational'),
            'lower_closed': {'type': 'boolean'},
            'upper_closed': {'type': 'boolean'},
        }),
    }
    scalar = obj({
        'kind': enum('scalar_radical_comparison'),
        'left': ref('radical'),
        'upper_bound': ref('radical'),
    })
    domain = {
        'type': 'object',
        'minProperties': 1,
        'maxProperties': 8,
        'propertyNames': {'pattern': '^[A-Za-z_][A-Za-z0-9_]{0,23}$'},
        'additionalProperties': ref('bounds'),
    }
    powers = {
        'type': 'object',
        'maxProperties': 8,
        'additionalProperties': {'type': 'integer', 'minimum': 0, 'maximum': 12},
    }
    polynomial = obj({
        'kind': enum('polynomial_upper_bound'),
        'domain': domain,
        'terms': arr(obj({'coefficient': ref('rational'), 'powers': powers})),
        'upper_bound': ref('rational'),
    })
    uc = obj({
        'kind': enum('uc_binary_upper_bound'),
        'functional': enum('uc_sqrt_penalty_v1'),
        'upper_bound': ref('radical'),
    })
    symbol = {'type': 'string', 'minLength': 1, 'maxLength': 24,
              'pattern': '^[A-Za-z_][A-Za-z0-9_]*$'}
    expression = ref('expression')
    defs['expression'] = {'oneOf': [
        obj({'op': enum('const'), 'value': ref('rational')}),
        obj({'op': enum('var'), 'name': symbol}),
        obj({'op': enum('add'), 'args': arr(expression, 2, 8)}),
        obj({'op': enum('sub'), 'left': expression, 'right': expression}),
        obj({'op': enum('mul'), 'args': arr(expression, 2, 8)}),
        obj({'op': enum('div'), 'left': expression, 'right': expression}),
        obj({'op': enum('neg'), 'arg': expression}),
        obj({'op': enum('pow'), 'base': expression,
             'exponent': {'type': 'integer', 'minimum': 0, 'maximum': 12}}),
    ]}
    rational_expression = obj({
        'kind': enum('rational_expression_upper_bound'),
        'domain': domain,
        'expression': expression,
        'upper_bound': ref('rational'),
    })
    ff_powers = {
        'type': 'object', 'maxProperties': 7,
        'additionalProperties': {'type': 'integer', 'minimum': 0, 'maximum': 12},
    }
    finite_field = obj({
        'kind': enum('finite_field_polynomial_residue'),
        'prime': {'type': 'integer', 'minimum': 2, 'maximum': 251},
        'variables': arr(symbol, 1, 3),
        'parameters': arr(symbol, 0, 4),
        'terms': arr(obj({
            'coefficient': {'type': 'integer', 'minimum': -1000000000, 'maximum': 1000000000},
            'powers': ff_powers,
        }), 1, 64),
        'point_count_adjustment': {'type': 'integer', 'minimum': -1000, 'maximum': 1000},
        'modulus': {'type': 'integer', 'minimum': 2, 'maximum': 4096},
        'allowed_residues': arr({'type': 'integer', 'minimum': 0, 'maximum': 4095}, 1, 4096),
    })
    finite_field_power_rule = obj({
        'kind': enum('finite_field_quadratic_quartic_residue_rule'),
        'prime': {'type': 'integer', 'minimum': 2, 'maximum': 251},
        'variables': arr(symbol, 1, 3),
        'parameters': arr(symbol, 0, 4),
        'terms': arr(obj({
            'coefficient': {'type': 'integer', 'minimum': -1000000000, 'maximum': 1000000000},
            'powers': ff_powers,
        }), 1, 64),
        'point_count_adjustment': {'type': 'integer', 'minimum': -1000, 'maximum': 1000},
        'modulus': {'type': 'integer', 'minimum': 2, 'maximum': 4096},
        'classification_parameter': symbol,
        'expected_residues': obj({
            'quartic_residue': arr({'type': 'integer', 'minimum': 0, 'maximum': 4095}, 1, 4096),
            'quadratic_nonquartic': arr({'type': 'integer', 'minimum': 0, 'maximum': 4095}, 1, 4096),
            'quadratic_nonresidue': arr({'type': 'integer', 'minimum': 0, 'maximum': 4095}, 1, 4096),
        }),
    })
    finite_map = obj({
        'kind': enum('finite_map_fixed_point'),
        'universe': arr(text(100), 1, 256),
        'conclusion': enum('has_fixed_point'),
    })
    graph_vertices = {
        'type': 'array',
        'items': text(64),
        'minItems': 1,
        'maxItems': 256,
        'uniqueItems': True,
    }
    graph_edge = {'type': 'array', 'items': text(64), 'minItems': 2, 'maxItems': 2}
    graph_edges = {
        'type': 'array',
        'items': graph_edge,
        'minItems': 0,
        'maxItems': 8192,
        'uniqueItems': True,
    }
    finite_graph = obj({
        'kind': enum('finite_graph_chromatic_lower_bound'),
        'vertices': graph_vertices,
        'edges': graph_edges,
        'minimum_colors': {'type': 'integer', 'minimum': 1, 'maximum': 256},
    })
    pmf_outcomes = arr(text(100), 1, 64)
    pmf_outcomes['uniqueItems'] = True
    pmf_domains = {
        'type': 'object',
        'minProperties': 1,
        'maxProperties': 8,
        'propertyNames': {'pattern': '^[A-Za-z_][A-Za-z0-9_]{0,23}$'},
        'additionalProperties': pmf_outcomes,
    }
    pmf_assignment = {
        'type': 'object',
        'maxProperties': 8,
        'propertyNames': {'pattern': '^[A-Za-z_][A-Za-z0-9_]{0,23}$'},
        'additionalProperties': text(100),
    }
    pmf_probability = obj({
        'kind': enum('finite_pmf_bound'),
        'operation': enum('probability'),
        'domains': pmf_domains,
        'event': arr(pmf_assignment, 0, 64),
        'relation': enum('at_most', 'at_least'),
        'bound': ref('rational'),
    })
    pmf_expectation = obj({
        'kind': enum('finite_pmf_bound'),
        'operation': enum('expectation'),
        'domains': pmf_domains,
        'payoffs': arr(obj({'assignment': pmf_assignment, 'value': ref('rational')}), 1, 256),
        'relation': enum('at_most', 'at_least'),
        'bound': ref('rational'),
    })
    defs['formalization'] = {
        'oneOf': [scalar, polynomial, rational_expression, uc, finite_field,
                  finite_field_power_rule, finite_map, finite_graph,
                  pmf_probability, pmf_expectation]
    }

    case = obj({
        'schema_version': enum('1.0'),
        'case_id': ref('identifier'),
        'artifacts': {
            'type': 'object',
            'minProperties': 1,
            'maxProperties': 64,
            'additionalProperties': ref('hash'),
        },
        'source': obj({
            'artifact': text(240),
            'text_artifact': text(240),
            'identifier': text(2000),
            'version': text(100),
            'capture_status': enum('unverified', 'captured', 'synthetic'),
            'correction_check': obj({
                'checked_on': {'type': 'string', 'format': 'date', 'minLength': 10, 'maxLength': 10},
                'status': enum('unchecked', 'none_found', 'present'),
                'evidence_artifact': text(240),
            }),
        }),
        'claim': obj({
            'id': ref('identifier'),
            'statement': text(8000),
            'scope': text(4000),
            'assumptions': ref('strings'),
            'excluded_claims': ref('strings'),
            'anchor': obj({
                'offset': {'type': 'integer', 'minimum': 0, 'maximum': 16 * 1024 * 1024},
                'quote': text(8000),
            }),
            'formalization': ref('formalization'),
        }),
        'witness_artifact': text(240),
        'unresolved_objections': dict(arr(text(4000)), uniqueItems=True),
        'disclosure': enum('private'),
    })
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:researchwitness:capsule:1.0',
        'title': 'ResearchWitness private evidence capsule 1.0',
        'description': (
            'Structural validation for deterministic formalization-level evidence bundles. '
            'The Python core additionally checks bytes, paths, resource bounds, anchors and arithmetic.'
        ),
        **case,
        '$defs': defs,
    }


if __name__ == '__main__':
    out = ROOT / 'schemas'
    out.mkdir(exist_ok=True)
    (out / 'case.schema.json').write_text(json.dumps(make(), indent=2) + '\n')
