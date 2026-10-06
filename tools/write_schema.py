"""Generate the v1 interchange schema. Cross-file and arithmetic checks live in the core."""
import json
from pathlib import Path
import sys

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
    modular_value = {'type': 'integer', 'minimum': -1000000000, 'maximum': 1000000000}
    modular = obj({
        'kind': enum('modular_linear_system'),
        'modulus': {'type': 'integer', 'minimum': 2, 'maximum': 4096},
        'matrix': arr(arr(modular_value, 1, 16), 1, 16),
        'rhs': arr(modular_value, 1, 16),
        'conclusion': enum('has_solution', 'no_solution'),
    })
    defs['formalization'] = {
        'oneOf': [scalar, polynomial, rational_expression, uc, finite_field,
                  finite_field_power_rule, finite_map, finite_graph,
                  pmf_probability, pmf_expectation, modular]
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


def make_intake_schema():
    """Generate the agent-facing intake schema, including all checker witnesses."""
    capsule = make()
    defs = capsule['$defs']
    rational = ref('rational')
    symbol_pattern = '^[A-Za-z_][A-Za-z0-9_]{0,23}$'
    variable_values = {
        'type': 'object', 'minProperties': 1, 'maxProperties': 8,
        'propertyNames': {'pattern': symbol_pattern}, 'additionalProperties': rational,
    }
    finite_parameters = {
        'type': 'object', 'maxProperties': 4,
        'propertyNames': {'pattern': symbol_pattern},
        'additionalProperties': {'type': 'integer', 'minimum': -1000000000, 'maximum': 1000000000},
    }
    pmf_assignment = {
        'type': 'object', 'maxProperties': 8,
        'propertyNames': {'pattern': symbol_pattern}, 'additionalProperties': text(100),
    }
    witness_schemas = [
        obj({'kind': enum('scalar_radical_comparison')}, ['kind']),
        obj({'kind': enum('polynomial_upper_bound'), 'point': variable_values}),
        obj({'kind': enum('rational_expression_upper_bound'), 'point': variable_values}),
        obj({'kind': enum('uc_binary_upper_bound'),
             'gamma': arr(rational, 4, 4), 'alpha': arr(rational, 4, 4),
             'b0': arr(arr(rational, 4, 4), 4, 4)}),
        obj({'kind': enum('finite_field_polynomial_residue'), 'parameters': finite_parameters}),
        obj({'kind': enum('finite_field_quadratic_quartic_residue_rule'), 'parameters': finite_parameters}),
        obj({'kind': enum('finite_map_fixed_point'),
             'mapping': {'type': 'object', 'minProperties': 1, 'maxProperties': 256,
                         'additionalProperties': text(100)}}),
        obj({'kind': enum('finite_graph_chromatic_lower_bound'),
             'coloring': {'type': 'object', 'minProperties': 1, 'maxProperties': 256,
                          'propertyNames': {'maxLength': 64}, 'additionalProperties': text(64)}}),
        obj({'kind': enum('finite_pmf_bound'),
             'atoms': arr(obj({'assignment': pmf_assignment, 'probability': rational}), 1, 256)}),
    ]
    modular_integer = {'type': 'integer', 'minimum': -1000000000, 'maximum': 1000000000}
    witness_schemas.append(obj({
        'kind': enum('modular_linear_system'),
        'certificate': obj({
            'type': enum('solution', 'annihilator'),
            'vector': arr(modular_integer, 1, 16),
        }),
    }))
    defs['intake_witness'] = {'oneOf': witness_schemas}

    path = text(240)
    date_schema = {'type': 'string', 'format': 'date', 'minLength': 10, 'maxLength': 10}
    intake = obj({
        'intake_version': enum('0.1'),
        'case_id': text(100),
        'source': obj({
            'identifier': text(2000), 'version': text(100), 'text_file': path,
            'capture_status': enum('unverified', 'captured', 'synthetic'),
            'correction_check': obj({
                'checked_on': date_schema,
                'status': enum('unchecked', 'none_found', 'present'),
                'evidence_file': path,
            }),
        }),
        'claim': obj({
            'id': text(100), 'statement': text(8000), 'scope': text(4000),
            'assumptions': arr(text(4000), 1, 10000),
            'excluded_claims': arr(text(4000), 1, 10000),
            'quote': text(8000),
            'quote_offset': {'type': 'integer', 'minimum': 0, 'maximum': 16 * 1024 * 1024},
            'formalization': ref('formalization'),
        }, required=['id', 'statement', 'scope', 'assumptions', 'excluded_claims', 'quote', 'formalization']),
        'witness': ref('intake_witness'),
        'unresolved_objections': arr(text(4000), 0, 10000),
        'notes_files': arr(path, 0, 32),
    }, required=['intake_version', 'case_id', 'source', 'claim', 'witness', 'unresolved_objections'])

    kind_names = [
        'scalar_radical_comparison', 'polynomial_upper_bound', 'rational_expression_upper_bound',
        'uc_binary_upper_bound', 'finite_field_polynomial_residue',
        'finite_field_quadratic_quartic_residue_rule', 'finite_map_fixed_point',
        'finite_graph_chromatic_lower_bound', 'finite_pmf_bound', 'modular_linear_system',
    ]
    intake['allOf'] = [
        {
            'if': {
                'required': ['claim'],
                'properties': {'claim': {
                    'required': ['formalization'],
                    'properties': {'formalization': {
                        'required': ['kind'],
                        'properties': {'kind': {'const': kind}},
                    }},
                }},
            },
            'then': {'properties': {'witness': {
                'properties': {'kind': {'const': kind}},
            }}},
        }
        for kind in kind_names
    ]
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:researchwitness:agent-intake:0.1',
        'title': 'ResearchWitness agent intake 0.1',
        'description': (
            'Structural validation for agent-prepared intake. The Python validator additionally checks '
            'safe local paths, artifact availability, unique quote anchoring, witness semantics, and exact arithmetic.'
        ),
        **intake,
        '$defs': defs,
    }


def make_review_schema():
    """Generate the broad, multi-area paper-review ledger schema."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from researchwitness.review import AREA_STATUSES, FINDING_STATUSES, REVIEW_AREAS

    path = text(240)
    hash_files = dict(arr(path, 0, 32), uniqueItems=True)
    area = lambda: obj({
        'status': enum(*sorted(AREA_STATUSES)),
        'method': text(2000),
        'notes': text(4000),
        'evidence_files': hash_files,
    })
    areas = obj({name: area() for name in REVIEW_AREAS})
    finding = obj({
        'id': {'type': 'string', 'minLength': 1, 'maxLength': 100,
               'pattern': '^[A-Za-z0-9_.-]+$'},
        'area': enum(*REVIEW_AREAS),
        'status': enum(*sorted(FINDING_STATUSES)),
        'location': text(1000),
        'statement': text(8000),
        'quote': text(8000),
        'rationale': text(4000),
        'evidence_files': hash_files,
        'quote_offset': {'type': 'integer', 'minimum': 0, 'maximum': 16 * 1024 * 1024},
        'verification_bundle': path,
        'summary_check': path,
    }, required=['id', 'area', 'status', 'location', 'statement', 'quote', 'rationale', 'evidence_files'])
    finding['allOf'] = [
        {
            'if': {'properties': {'status': {'const': 'formalization_replay'}}, 'required': ['status']},
            'then': {'required': ['verification_bundle'], 'not': {'required': ['summary_check']}},
        },
        {
            'if': {'properties': {'status': {'const': 'tabular_summary_replay'}}, 'required': ['status']},
            'then': {'required': ['summary_check'], 'not': {'required': ['verification_bundle']}},
        },
        {
            'if': {
                'properties': {'status': {'enum': ['candidate', 'unsupported', 'dismissed']}},
                'required': ['status'],
            },
            'then': {'not': {'anyOf': [
                {'required': ['verification_bundle']}, {'required': ['summary_check']},
            ]}},
        },
    ]
    review = obj({
        'review_version': enum('0.1'),
        'review_id': text(100),
        'reviewed_on': {'type': 'string', 'format': 'date', 'minLength': 10, 'maxLength': 10},
        'source': obj({
            'identifier': text(2000),
            'version': text(100),
            'text_file': path,
            'capture_status': enum('unverified', 'captured', 'synthetic'),
        }),
        'areas': areas,
        'findings': arr(finding, 0, 256),
    })
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:researchwitness:paper-review:0.1',
        'title': 'ResearchWitness broad paper-review ledger 0.1',
        'description': (
            'Structural schema for a multi-area research-paper review. Candidate observations are unverified; '
            'the Python validator checks source quote anchors, local evidence files, and linked checker replays.'
        ),
        **review,
    }


def make_summary_check_schema():
    """Generate the exact input schema for univariate tabular-summary checks."""
    rational = {
        'type': 'string',
        'maxLength': 130,
        'pattern': r'^-?(?:0|[1-9][0-9]{0,63})(?:/[1-9][0-9]{0,63})?$',
    }
    path = text(240)
    source = obj({
        'identifier': text(2000),
        'version': text(100),
        'text_file': path,
        'capture_status': enum('unverified', 'captured', 'synthetic'),
        'quote': text(8000),
        'quote_offset': {'type': 'integer', 'minimum': 0, 'maximum': 16 * 1024 * 1024},
    }, required=['identifier', 'version', 'text_file', 'capture_status', 'quote'])
    csv_file = obj({
        'path': path,
        'format': enum('csv', 'tsv'),
        'header': {'const': True},
        'column_name': text(200),
        'missing_values': arr({'type': 'string', 'maxLength': 200}, 0, 32),
        'missing_policy': enum('reject', 'drop'),
    })
    csv_file['properties']['missing_values']['uniqueItems'] = True
    indexed_file = obj({
        'path': path,
        'format': enum('csv', 'tsv'),
        'header': {'const': False},
        'column_index': {'type': 'integer', 'minimum': 0, 'maximum': 255},
        'missing_values': arr({'type': 'string', 'maxLength': 200}, 0, 32),
        'missing_policy': enum('reject', 'drop'),
    })
    indexed_file['properties']['missing_values']['uniqueItems'] = True
    file_input = {
        'oneOf': [csv_file, indexed_file],
    }
    data = obj({
        'column': text(200),
        'data_source': text(2000),
        'transformation': text(2000),
        'values': arr(rational, 1, 4096),
        'file': file_input,
    }, required=['column', 'data_source', 'transformation'])
    data['oneOf'] = [
        {'required': ['values'], 'not': {'required': ['file']}},
        {'required': ['file'], 'not': {'required': ['values']}},
    ]
    count_summary = obj({
        'statistic': enum('count'),
        'value': {'type': 'integer', 'minimum': 0, 'maximum': 4096},
        'tolerance': rational,
    })
    numeric_summary = obj({
        'statistic': enum('sum', 'mean', 'median', 'minimum', 'maximum',
                          'sample_variance', 'population_variance'),
        'value': rational,
        'tolerance': rational,
    })
    report = {
        'type': 'array',
        'items': {'oneOf': [count_summary, numeric_summary]},
        'minItems': 1,
        'maxItems': 32,
    }
    report['uniqueItems'] = True
    check = obj({
        'summary_check_version': enum('0.1'),
        'source': source,
        'data': data,
        'reported': report,
    })
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:researchwitness:tabular-summary-check:0.1',
        'title': 'ResearchWitness exact tabular-summary check 0.1',
        'description': (
            'Exact univariate descriptive-statistic recomputation from supplied rational values or a bounded '
            'local CSV/TSV column. File extraction selects one column and applies an explicit missing-value '
            'policy; arbitrary filtering, grouping, and transformations are not performed.'
        ),
        **check,
        '$defs': {'rational': rational},
    }


def make_paper_audit_schema():
    """Generate the bounded screening report schema (not a paper-truth schema)."""
    hash_value = {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}
    empty_text = {'type': 'string', 'maxLength': 2000}
    small_int_string = {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,8})$'}
    anchor = obj({
        'text_file': enum('extracted-text.txt'),
        'quote': text(75),
        'start_byte': {'type': 'integer', 'minimum': 0, 'maximum': 32 * 1024 * 1024},
        'end_byte': {'type': 'integer', 'minimum': 1, 'maximum': 32 * 1024 * 1024},
        'line_number': {'type': 'integer', 'minimum': 1, 'maximum': 1_000_000},
        'context': {'type': 'string', 'maxLength': 2000},
        'page_number': {'type': 'integer', 'minimum': 1, 'maximum': 500},
        'page_offset_start_byte': {'type': 'integer', 'minimum': 0, 'maximum': 512 * 1024},
        'page_offset_end_byte': {'type': 'integer', 'minimum': 1, 'maximum': 512 * 1024},
        'section': {'type': 'string', 'maxLength': 2000},
    }, required=['text_file', 'quote', 'start_byte', 'end_byte', 'line_number', 'context'])
    stage_cue = obj({'stage': enum(
        'screened', 'eligible', 'enrolled', 'randomized', 'excluded', 'completed',
        'analyzed', 'follow_up', 'available',
    ), 'cue': text(200)})
    assertion_scope = obj({
        'region': enum('MARKDOWN_TABLE_CELL', 'PROSE_CONTEXT'),
        'nearby_context': {'type': 'string', 'maxLength': 600},
        'study_stage': {'oneOf': [{'type': 'null'}, text(40)]},
        'stage_cues': arr(stage_cue, 0, 8),
    })
    assertion = obj({
        'id': {'type': 'string', 'pattern': '^count-[0-9]{4}$'},
        'kind': enum('explicit_count_marker'),
        'marker': enum('n', 'N'),
        'surface_value': {'type': 'string', 'pattern': '^[0-9]{1,9}$'},
        'value_exact': small_int_string,
        'anchor': anchor,
        'scope': assertion_scope,
    })
    page = obj({
        'page_number': {'type': 'integer', 'minimum': 1, 'maximum': 500},
        'character_count': {'type': 'integer', 'minimum': 0, 'maximum': 512 * 1024},
        'status': enum('TEXT_EXTRACTED', 'NO_EXTRACTABLE_TEXT'),
        'text_start_byte': {'type': 'integer', 'minimum': 0, 'maximum': 16 * 1024 * 1024},
        'text_end_byte': {'type': 'integer', 'minimum': 0, 'maximum': 16 * 1024 * 1024},
    })
    section = obj({
        'heading': empty_text,
        'level': {'type': 'integer', 'minimum': 1, 'maximum': 6},
        'start_byte': {'type': 'integer', 'minimum': 0, 'maximum': 32 * 1024 * 1024},
        'line_number': {'type': 'integer', 'minimum': 1, 'maximum': 1_000_000},
    })
    count_anomaly = obj({
        'id': {'type': 'string', 'pattern': '^conflicting-[nN]-values(?:-[0-9]{2})?$'},
        'type': enum('CONFLICTING_EXPLICIT_COUNT_MARKERS'),
        'status': enum('CANDIDATE_ANOMALY'),
        'marker': enum('n', 'N'),
        'values_exact': arr(small_int_string, 2, 512),
        'assertion_ids': arr({'type': 'string', 'pattern': '^count-[0-9]{4}$'}, 2, 512),
        'source_anchors': arr(anchor, 2, 512),
        'scope_stage': arr(text(40), 0, 9),
        'interpretation': text(1000),
        'required_review': text(1000),
    })
    table_anomaly = obj({
        'id': {'type': 'string', 'pattern': '^table-percentage-[0-9]{4}$'},
        'type': enum('TABLE_PERCENTAGE_ARITHMETIC_MISMATCH'),
        'status': enum('CANDIDATE_ANOMALY'),
        'numerator_exact': small_int_string,
        'denominator_exact': small_int_string,
        'reported_percent': {'type': 'string', 'pattern': '^[0-9]{1,3}(?:\\.[0-9]{1,6})?$'},
        'recomputed_percent': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,2})(?:\\.[0-9]{1,6})?$'},
        'rounding_tolerance_percentage_points': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]?)(?:\\.[0-9]{1,6})?$'},
        'scope_label': empty_text,
        'table': empty_text,
        'source_anchors': arr(anchor, 3, 3),
        'adversarial_review': obj({
            'status': enum('ARITHMETIC_RECOMPUTED_WITH_SCOPE_OBJECTIONS'),
            'objections_considered': arr(text(500), 1, 8),
            'limitations': arr(text(500), 1, 8),
        }),
        'interpretation': text(1000),
        'required_review': text(1000),
    })
    flow_anomaly = obj({
        'id': {'type': 'string', 'pattern': '^exclusion-flow-[0-9]{4}$'},
        'type': enum('EXPLICIT_EXCLUSION_FLOW_ARITHMETIC_MISMATCH'),
        'status': enum('CANDIDATE_ANOMALY'),
        'source_total_exact': small_int_string,
        'excluded_values_exact': arr(small_int_string, 1, 64),
        'reported_included_exact': small_int_string,
        'expected_included_exact': {'type': 'string', 'pattern': '^-?(?:0|[1-9][0-9]{0,10})$'},
        'difference_exact': {'type': 'string', 'pattern': '^-?(?:0|[1-9][0-9]{0,10})$'},
        'source_anchors': arr(anchor, 3, 66),
        'interpretation': text(1000),
        'required_review': text(1000),
    })
    candidate = {'oneOf': [count_anomaly, table_anomaly, flow_anomaly]}
    scope_difference = obj({
        'id': {'type': 'string', 'pattern': '^(?:scope-[0-9]{4}|table-scope-[0-9]{4})$'},
        'type': enum(
            'MULTIPLE_COUNT_SCOPES_IN_ONE_PASSAGE', 'DIFFERENT_EXPLICIT_STUDY_STAGES',
            'POSSIBLE_ROW_SPECIFIC_DENOMINATOR',
        ),
        'status': enum('POSSIBLE_SAMPLE_FLOW_DIFFERENCE'),
        'marker': enum('n', 'N'),
        'values_exact': arr(small_int_string, 2, 512),
        'stage_labels': arr(text(40), 2, 2),
        'reported_percent': {'type': 'string', 'pattern': '^[0-9]{1,3}(?:\\.[0-9]{1,6})?$'},
        'numerator_exact': small_int_string,
        'column_denominator_exact': small_int_string,
        'compatible_alternate_denominators_exact': arr(small_int_string, 1, 16),
        'scope_label': empty_text,
        'table': empty_text,
        'source_anchors': arr(anchor, 1, 512),
        'interpretation': text(1000),
        'required_review': text(1000),
    }, required=['id', 'type', 'status', 'source_anchors', 'interpretation', 'required_review'])
    report = obj({
        'paper_audit_version': enum('0.2'),
        'decision': enum(
            'CANDIDATES_FOUND', 'CANDIDATES_FOUND_IN_INCOMPLETE_SCAN',
            'NO_CANDIDATES_IN_SUPPORTED_SCAN', 'SCAN_INCOMPLETE_NO_CANDIDATES',
            'EXTRACTION_UNAVAILABLE_OR_EMPTY',
        ),
        'source': obj({
            'identifier': text(2000),
            'version': text(100),
            'capture_status': enum('unverified'),
            'source_file': enum('source.txt', 'source.md', 'source.markdown', 'source.pdf'),
            'sha256': hash_value,
        }),
        'extraction': obj({
            'status': enum(
                'TEXT_AVAILABLE', 'PARTIAL_TEXT', 'NO_EXTRACTABLE_TEXT',
                'PARSER_UNAVAILABLE', 'MALFORMED_OR_UNSUPPORTED', 'LIMIT_OR_UNSUPPORTED',
                'RESOURCE_LIMIT_OR_TIMEOUT', 'WORKER_FAILED', 'WORKER_PROTOCOL_ERROR',
            ),
            'extractor': text(200),
            'original_format': enum('txt', 'md', 'markdown', 'pdf'),
            'source_bytes': {'type': 'integer', 'minimum': 0, 'maximum': 32 * 1024 * 1024},
            'text_file': enum('extracted-text.txt'),
            'text_sha256': hash_value,
            'text_bytes': {'type': 'integer', 'minimum': 0, 'maximum': 32 * 1024 * 1024},
            'page_count': {'oneOf': [{'type': 'null'}, {'type': 'integer', 'minimum': 0, 'maximum': 500}]},
            'page_map': arr(page, 0, 500),
            'warnings': arr(text(5000), 0, 16),
            'ocr_performed': {'const': False},
        }),
        'paper_structure': obj({
            'sections': arr(section, 0, 512),
            'layout_status': enum('TEXT_OR_MARKDOWN_OFFSETS', 'PDF_PAGE_AND_EXTRACTED_TEXT_OFFSETS_ONLY'),
        }),
        'discovery': obj({
            'provider': enum('deterministic_local_heuristic'),
            'discoverer': enum('explicit_count_marker_scan'),
            'scan_complete': {'type': 'boolean'},
            'assertions': arr(assertion, 0, 512),
            'candidate_anomalies': arr(count_anomaly, 0, 2),
            'possible_scope_differences': arr(scope_difference, 0, 128),
            'table_count_assertions_not_cross_compared': {'type': 'integer', 'minimum': 0, 'maximum': 512},
            'limitations': arr(text(1000), 1, 16),
        }),
        'arithmetic_screens': obj({
            'table_percentages': obj({
                'discoverer': enum('markdown_table_percentage_recomputation'),
                'findings': arr(table_anomaly, 0, 256),
                'possible_scope_differences': arr(scope_difference, 0, 128),
                'checked_cells': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
                'cells_scanned': {'type': 'integer', 'minimum': 0, 'maximum': 100_001},
                'supported': {'type': 'boolean'},
                'scan_complete': {'type': 'boolean'},
                'limitations': arr(text(1000), 0, 16),
            }),
            'sample_exclusion_flow': obj({
                'discoverer': enum('explicit_exclusion_flow_arithmetic_screen'),
                'candidate_anomalies': arr(flow_anomaly, 0, 64),
                'scan_complete': {'type': 'boolean'},
                'limitations': arr(text(1000), 0, 16),
            }),
        }),
        'candidate_anomalies': arr(candidate, 0, 322),
        'possible_scope_differences': arr(scope_difference, 0, 256),
        'checks_attempted': arr(enum(
            'explicit_count_marker_scan', 'markdown_table_percentage_recomputation',
            'explicit_exclusion_flow_arithmetic_screen',
        ), 0, 3),
        'verified_findings': arr({'type': 'object'}, 0, 0),
        'unresolved_questions': arr(text(1000), 0, 322),
        'unsupported_checks': arr(text(500), 1, 16),
        'known_corrections': obj({'status': enum('NOT_CHECKED')}),
        'paper_error_established': {'const': False},
        'meaning': text(1000),
    })
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:researchwitness:paper-audit-report:0.2',
        'title': 'ResearchWitness bounded paper-screening report 0.2',
        'description': (
            'Bounded numeric screening for explicit repeated counts, selected Markdown table percentages, and one '
            'explicit sample-exclusion pattern. All flags remain candidates; a negative result does not establish correctness.'
        ),
        **report,
    }


if __name__ == '__main__':
    out = ROOT / 'schemas'
    out.mkdir(exist_ok=True)
    package_out = ROOT / 'researchwitness' / 'schemas'
    package_out.mkdir(exist_ok=True)
    for name, schema in (
        ('case.schema.json', make()),
        ('intake.schema.json', make_intake_schema()),
        ('review.schema.json', make_review_schema()),
        ('summary-check.schema.json', make_summary_check_schema()),
        ('paper-audit.schema.json', make_paper_audit_schema()),
    ):
        rendered = json.dumps(schema, indent=2) + '\n'
        (out / name).write_text(rendered, encoding='utf-8')
        (package_out / name).write_text(rendered, encoding='utf-8')
