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
    nullable_text = {'oneOf': [text(500), {'type': 'null'}]}
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
    structured_anchor = obj({
        'source_file': enum('source.xml', 'source.nxml'),
        'source_sha256': hash_value,
        'source_format': enum('jats_xml'),
        'element_path': text(4000),
        'quote': {'type': 'string', 'maxLength': 1000},
        'start_byte': {'oneOf': [{'type': 'null'}, {'type': 'integer', 'minimum': 0, 'maximum': 32 * 1024 * 1024}]},
        'end_byte': {'oneOf': [{'type': 'null'}, {'type': 'integer', 'minimum': 0, 'maximum': 32 * 1024 * 1024}]},
    }, required=['source_file', 'source_sha256', 'source_format', 'element_path', 'quote', 'start_byte', 'end_byte'])
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
    structured_table_anomaly = obj({
        'id': {'type': 'string', 'pattern': '^structured-table-percentage-[0-9]{4}$'},
        'type': enum('STRUCTURED_TABLE_PERCENTAGE_ARITHMETIC_MISMATCH'),
        'status': enum('CANDIDATE_ANOMALY'),
        'relation_id': hash_value,
        'table_id': {'type': 'string', 'maxLength': 500},
        'table_caption': empty_text,
        'numerator_exact': small_int_string,
        'denominator_exact': small_int_string,
        'reported_percent': {'type': 'string', 'pattern': '^[0-9]{1,3}(?:\\.[0-9]{1,6})?$'},
        'recomputed_percent': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,2})(?:\\.[0-9]{1,8})?$'},
        'recomputed_at_display_precision': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,2})(?:\\.[0-9]{1,6})?$'},
        'display_precision': {'type': 'integer', 'minimum': 0, 'maximum': 6},
        'rounding_tolerance_percentage_points': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]?)(?:\\.[0-9]{1,7})?$'},
        'row_identity': empty_text,
        'effective_headers': arr(text(2000), 1, 32),
        'source_anchors': arr(structured_anchor, 3, 3),
        'interpretation': text(1000),
        'required_review': text(1000),
    })
    cell_ratio_anomaly = obj({
        'id': {'type': 'string', 'pattern': '^jats-cell-ratio-percentage-[0-9]{4}$'},
        'type': enum('JATS_CELL_RATIO_PERCENTAGE_MISMATCH'),
        'status': enum('CANDIDATE_ANOMALY'),
        'relation_id': hash_value,
        'table_key': hash_value,
        'table_id': {'type': 'string', 'maxLength': 500},
        'table_label': empty_text,
        'table_caption': empty_text,
        'row_identity': empty_text,
        'numerator_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,8})$'},
        'denominator_exact': {'type': 'string', 'pattern': '^[1-9][0-9]{0,8}$'},
        'reported_percent': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,2})(?:\\.[0-9]{1,6})?$'},
        'recomputed_percent': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,2})(?:\\.[0-9]{1,8})?$'},
        'recomputed_at_display_precision': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,2})(?:\\.[0-9]{1,6})?$'},
        'display_precision': {'type': 'integer', 'minimum': 0, 'maximum': 6},
        'source_anchors': arr(structured_anchor, 1, 1),
        'interpretation': text(1000),
        'required_review': text(1000),
    })
    sd_se_n_anomaly = obj({
        'id': {'type': 'string', 'pattern': '^jats-sd-se-n-[0-9]{4}$'},
        'type': enum('JATS_SD_SE_N_ARITHMETIC_MISMATCH'),
        'status': enum('CANDIDATE_ANOMALY'),
        'table_id': {'type': 'string', 'maxLength': 500},
        'row_index': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'row_identity': empty_text,
        'n_exact': {'type': 'string', 'pattern': '^[1-9][0-9]{0,9}$'},
        'sd_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})(?:\\.[0-9]{1,8})?$'},
        'reported_se': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})(?:\\.[0-9]{1,8})?$'},
        'recomputed_se_at_display_precision': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})(?:\\.[0-9]{1,8})?$'},
        'display_precision': {'type': 'integer', 'minimum': 0, 'maximum': 8},
        'difference_at_display_precision': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})(?:\\.[0-9]{1,8})?$'},
        'source_anchors': arr(obj({
            'role': enum('n', 'sd', 'se'),
            'source_anchor': structured_anchor,
        }), 3, 3),
        'interpretation': text(1000),
        'required_review': text(1000),
    })
    jats_flow_anomaly = obj({
        'id': {'type': 'string', 'pattern': '^jats-sample-flow-[0-9]{4}$'},
        'type': enum('JATS_SAMPLE_FLOW_ARITHMETIC_MISMATCH'),
        'status': enum('CANDIDATE_ANOMALY'),
        'source_total_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,12})$'},
        'excluded_values_exact': arr({'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,12})$'}, 2, 32),
        'reported_included_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,12})$'},
        'expected_included_exact': {'type': 'string', 'pattern': '^-?(?:0|[1-9][0-9]{0,13})$'},
        'difference_exact': {'type': 'string', 'pattern': '^-?(?:0|[1-9][0-9]{0,13})$'},
        'source_anchors': arr(structured_anchor, 4, 35),
        'interpretation': text(1000),
        'required_review': text(1000),
    })
    prisma_count = {'oneOf': [
        {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,12})$'},
        {'type': 'null'},
    ]}
    prisma_signed_count = {'oneOf': [
        {'type': 'string', 'pattern': '^-?(?:0|[1-9][0-9]{0,12})$'},
        {'type': 'null'},
    ]}
    prisma_source_anchor = obj({
        'role': enum('records_identified', 'duplicates_removed', 'records_screened', 'transition', 'relation'),
        'source_anchor': structured_anchor,
    })
    prisma_relation = obj({
        'status': enum('PRISMA_FLOW_BALANCED', 'PRISMA_FLOW_ARITHMETIC_CANDIDATE', 'UNSUPPORTED'),
        'reason': nullable_text,
        'unit': {'const': 'records'},
        'records_identified_exact': prisma_count,
        'duplicates_removed_exact': prisma_count,
        'records_screened_exact': prisma_count,
        'expected_screened_exact': prisma_count,
        'difference_exact': prisma_signed_count,
        'source_anchors': arr(prisma_source_anchor, 1, 4),
    })
    prisma_anomaly = obj({
        'id': {'type': 'string', 'pattern': '^jats-prisma-flow-[0-9]{4}$'},
        'type': enum('JATS_PRISMA_FLOW_ARITHMETIC_MISMATCH'),
        'status': enum('CANDIDATE_ANOMALY'),
        'records_identified_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,12})$'},
        'duplicates_removed_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,12})$'},
        'reported_screened_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,12})$'},
        'expected_screened_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,12})$'},
        'difference_exact': {'type': 'string', 'pattern': '^-?(?:0|[1-9][0-9]{0,12})$'},
        'source_anchors': arr(structured_anchor, 4, 4),
        'interpretation': text(1000),
        'required_review': text(1000),
    })
    two_by_two_count = {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})$'}
    two_by_two_rational = {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,19})$'}
    two_by_two_number = {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})(?:\\.[0-9]{1,8})?$'}
    two_by_two_check = obj({
        'status': enum('CONSISTENT_WITH_ROUNDING', 'ARITHMETIC_CANDIDATE'),
        'reason': nullable_text,
        'table_id': {'type': 'string', 'maxLength': 500},
        'row_index': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'row_identity': empty_text,
        'timepoint': {'type': 'string', 'maxLength': 500},
        'measure': {'const': 'odds_ratio'},
        'exposed_events_exact': two_by_two_count,
        'exposed_non_events_exact': two_by_two_count,
        'unexposed_events_exact': two_by_two_count,
        'unexposed_non_events_exact': two_by_two_count,
        'reported_odds_ratio': two_by_two_number,
        'exact_numerator': two_by_two_rational,
        'exact_denominator': two_by_two_rational,
        'recomputed_at_display_precision': two_by_two_number,
        'display_precision': {'type': 'integer', 'minimum': 0, 'maximum': 8},
        'source_anchors': arr(structured_anchor, 5, 5),
    })
    two_by_two_table = obj({
        'table_id': {'type': 'string', 'maxLength': 500},
        'status': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
        'potential_objects': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'applicable_objects': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'eligible_objects': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'checked_objects': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'skipped_objects': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'candidate_count': {'type': 'integer', 'minimum': 0, 'maximum': 256},
        'checks': arr(two_by_two_check, 0, 1),
        'skip_reasons': arr(obj({
            'reason': text(200),
            'row_index': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        }, required=['reason']), 0, 16),
        'scan_complete': {'type': 'boolean'},
    })
    two_by_two_anomaly = obj({
        'id': {'type': 'string', 'pattern': '^jats-unadjusted-2x2-or-[0-9]{4}$'},
        'type': enum('JATS_UNADJUSTED_2X2_ODDS_RATIO_MISMATCH'),
        'status': enum('CANDIDATE_ANOMALY'),
        'table_id': {'type': 'string', 'maxLength': 500},
        'row_identity': empty_text,
        'timepoint': {'type': 'string', 'maxLength': 500},
        'exposed_events_exact': two_by_two_count,
        'exposed_non_events_exact': two_by_two_count,
        'unexposed_events_exact': two_by_two_count,
        'unexposed_non_events_exact': two_by_two_count,
        'reported_odds_ratio': two_by_two_number,
        'exact_numerator': two_by_two_rational,
        'exact_denominator': two_by_two_rational,
        'recomputed_at_display_precision': two_by_two_number,
        'display_precision': {'type': 'integer', 'minimum': 0, 'maximum': 8},
        'source_anchors': arr(structured_anchor, 5, 5),
        'interpretation': text(1000),
        'required_review': text(1000),
    })
    candidate = {'oneOf': [
        count_anomaly, table_anomaly, flow_anomaly, structured_table_anomaly,
        cell_ratio_anomaly, sd_se_n_anomaly, jats_flow_anomaly, prisma_anomaly,
        two_by_two_anomaly,
    ]}
    nullable_count = {'oneOf': [
        {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
        {'type': 'null'},
    ]}
    object_counts = obj({
        'unit': text(100),
        'potential': nullable_count,
        'applicable': nullable_count,
        'applicability_unknown': nullable_count,
        'eligible': nullable_count,
        'checked': nullable_count,
        'skipped': nullable_count,
        'candidates': nullable_count,
    }, required=['unit', 'potential', 'applicable', 'eligible', 'checked', 'skipped', 'candidates'])
    operand_counts = obj({
        'unit': text(100),
        'potential': nullable_count,
        'applicable': nullable_count,
        'eligible': nullable_count,
        'checked': nullable_count,
        'skipped': nullable_count,
        'candidates': nullable_count,
        'candidate_count_known': {'type': 'boolean'},
    }, required=['unit', 'potential', 'eligible', 'checked', 'skipped', 'candidates'])
    percentage_status_counts = obj({
        'NOT_APPLICABLE': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'ELIGIBLE_CHECKED_MATCH': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'ELIGIBLE_CHECKED_MISMATCH': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'INCOMPLETE': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'UNSUPPORTED': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
    })
    percentage_reason_counts = {
        'type': 'object', 'maxProperties': 32,
        'propertyNames': {'pattern': '^[A-Z][A-Z0-9_]{1,79}$'},
        'additionalProperties': {'type': 'integer', 'minimum': 1, 'maximum': 50_000},
    }
    percentage_reason_code = enum(
        'TABLE_STRUCTURE_UNSUPPORTED', 'SOURCE_SCOPE_AMBIGUOUS', 'CONFLICTING_HEADER_DENOMINATORS',
        'LOCAL_ROW_DENOMINATOR', 'FOOTNOTE_SCOPE_UNRESOLVED', 'WEIGHTED_RESULT', 'ADJUSTED_RESULT',
        'MISSINGNESS_CHANGES_DENOMINATOR', 'MULTIPLE_RESPONSE', 'CATEGORY_OVERLAP_RELEVANT_TO_RELATION',
        'DENOMINATOR_NOT_EXPLICIT', 'PERCENT_UNIT_NOT_EXPLICIT', 'GROUPED_INTEGER_FORMAT_UNSUPPORTED',
        'DECIMAL_SEPARATOR_UNSUPPORTED', 'MALFORMED_NUMERIC_TOKEN', 'OPERANDS_OUTSIDE_PROPORTION_DOMAIN',
        'CANDIDATE_LIMIT',
    )
    percentage_relation = obj({
        'relation_id': hash_value,
        'relation_type': enum('CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE', 'DIRECT_N_OVER_N_PERCENTAGE'),
        'detector_id': enum('table_percentage_recomputation', 'jats_cell_ratio_percentage_recomputation'),
        'contract_version': enum('1.2'),
        'table_key': hash_value,
        'status': enum('NOT_APPLICABLE', 'ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH', 'INCOMPLETE', 'UNSUPPORTED'),
        'primary_skip_reason': {'oneOf': [percentage_reason_code, {'type': 'null'}]},
        'secondary_skip_reasons': {
            'type': 'array', 'items': percentage_reason_code, 'minItems': 0, 'maxItems': 16,
            'uniqueItems': True,
        },
        'source_anchor': structured_anchor,
        'denominator_source_anchor': {'oneOf': [structured_anchor, {'type': 'null'}]},
        'numerator_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,8})$'},
        'denominator_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,8})$'},
        'reported_percent': {'type': 'string', 'pattern': '^[0-9]{1,3}(?:\\.[0-9]{1,6})?$'},
        'display_precision': {'type': 'integer', 'minimum': 0, 'maximum': 6},
        'recomputed_at_display_precision': {'type': 'string', 'pattern': '^[0-9]{1,3}(?:\\.[0-9]{1,6})?$'},
        'finding_emitted': {'type': 'boolean'},
        'row_identity': empty_text,
    }, required=[
        'relation_id', 'relation_type', 'detector_id', 'contract_version', 'table_key', 'status', 'primary_skip_reason',
        'secondary_skip_reasons', 'source_anchor', 'denominator_source_anchor',
    ])
    percentage_relation['allOf'] = [
        {
            'if': {
                'properties': {'detector_id': {'const': 'table_percentage_recomputation'}},
                'required': ['detector_id'],
            },
            'then': {'properties': {'relation_type': {'const': 'CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE'}}},
        },
        {
            'if': {
                'properties': {'detector_id': {'const': 'jats_cell_ratio_percentage_recomputation'}},
                'required': ['detector_id'],
            },
            'then': {'properties': {'relation_type': {'const': 'DIRECT_N_OVER_N_PERCENTAGE'}}},
        },
        {
            'if': {
                'properties': {'status': {'enum': ['INCOMPLETE', 'UNSUPPORTED']}},
                'required': ['status'],
            },
            'then': {
                'properties': {'primary_skip_reason': percentage_reason_code},
                'not': {'required': [
                    'numerator_exact', 'denominator_exact', 'reported_percent', 'display_precision',
                    'recomputed_at_display_precision', 'finding_emitted',
                ]},
            },
        },
        {
            'if': {
                'properties': {'status': {'enum': ['ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH']}},
                'required': ['status'],
            },
            'then': {
                'required': [
                    'numerator_exact', 'denominator_exact', 'reported_percent', 'display_precision',
                    'recomputed_at_display_precision', 'finding_emitted',
                ],
                'properties': {
                    'primary_skip_reason': {'type': 'null'},
                    'secondary_skip_reasons': {'maxItems': 0},
                },
            },
        },
        {
            'if': {
                'properties': {'status': {'const': 'ELIGIBLE_CHECKED_MATCH'}},
                'required': ['status'],
            },
            'then': {'properties': {'finding_emitted': {'const': False}}},
        },
        {
            'if': {
                'properties': {'status': {'const': 'NOT_APPLICABLE'}},
                'required': ['status'],
            },
            'then': {
                'properties': {
                    'primary_skip_reason': {'type': 'null'},
                    'secondary_skip_reasons': {'maxItems': 0},
                },
                'not': {'required': [
                    'numerator_exact', 'denominator_exact', 'reported_percent', 'display_precision',
                    'recomputed_at_display_precision', 'finding_emitted',
                ]},
            },
        },
    ]
    percentage_relation_telemetry = obj({
        'potential_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'applicable_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'eligible_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'checked_matches': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'checked_mismatches': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'checked_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'incomplete_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'unsupported_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'skipped_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'status_counts': percentage_status_counts,
        'primary_skip_reason_counts': percentage_reason_counts,
        'secondary_skip_reason_counts_overlapping': percentage_reason_counts,
        'accounting_invariant': {'const': True},
    })
    coverage_table = obj({
        'table_ref': obj({'source_sha256': hash_value, 'element_path': text(4096)}),
        'table_id': {'type': 'string', 'maxLength': 500},
        'label': empty_text,
        'caption': empty_text,
        'display_text_truncated': {'type': 'boolean'},
        'parser_status': enum('STRUCTURE_RELIABLE', 'TABLE_STRUCTURE_UNSUPPORTED'),
        'status': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
        'applicability': enum('APPLICABLE', 'UNKNOWN', 'UNSUPPORTED', 'NOT_APPLICABLE'),
        'reasons': arr(text(200), 0, 32),
        'reasons_truncated': {'type': 'boolean'},
        'skip_reasons': arr(text(200), 0, 32),
        'candidate_findings_omitted': nullable_count,
        'counts': obj({'objects': object_counts, 'operands': operand_counts}),
    })
    coverage_detector = obj({
        'detector_id': {'type': 'string', 'minLength': 1, 'maxLength': 100},
        'scope': enum('table', 'paper'),
        'status': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
        'status_counts': {
            'type': 'object', 'maxProperties': 4, 'additionalProperties': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
        },
        'object_counts': object_counts,
        'operand_counts': operand_counts,
        'reasons': arr(text(200), 0, 16),
        'reasons_truncated': {'type': 'boolean'},
        'unmatched_result_count': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
        'percentage_relation_telemetry': {'oneOf': [percentage_relation_telemetry, {'type': 'null'}]},
        'percentage_relation_telemetry_complete': {'type': 'boolean'},
        'tables': arr(coverage_table, 0, 1000),
    }, required=['detector_id', 'scope', 'status', 'object_counts', 'operand_counts', 'tables'])
    coverage_detector['allOf'] = [{
        'if': {
            'properties': {
                'detector_id': enum(
                    'table_percentage_recomputation', 'jats_cell_ratio_percentage_recomputation',
                ),
            },
            'required': ['detector_id'],
        },
        'then': {
            'required': ['percentage_relation_telemetry', 'percentage_relation_telemetry_complete'],
            'oneOf': [
                {
                    'properties': {
                        'percentage_relation_telemetry': percentage_relation_telemetry,
                        'percentage_relation_telemetry_complete': {'const': True},
                    },
                    'required': ['percentage_relation_telemetry', 'percentage_relation_telemetry_complete'],
                },
                {
                    'properties': {
                        'percentage_relation_telemetry': {'type': 'null'},
                        'percentage_relation_telemetry_complete': {'const': False},
                        'status': {'const': 'INCOMPLETE'},
                    },
                    'required': [
                        'percentage_relation_telemetry', 'percentage_relation_telemetry_complete', 'status',
                    ],
                },
            ],
        },
        'else': {
            'not': {
                'anyOf': [
                    {'required': ['percentage_relation_telemetry']},
                    {'required': ['percentage_relation_telemetry_complete']},
                ],
            },
        },
    }]
    paper_coverage = obj({
        'coverage_version': enum('1'),
        'source_sha256': hash_value,
        'scope_note': text(2000),
        'paper': obj({
            'tables': obj({
                'discovered': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
                'parsed': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
                'structure_reliable': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
                'structure_unsupported': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
                'parser_status_counts': {
                    'type': 'object', 'maxProperties': 2,
                    'additionalProperties': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
                },
            }),
            'detectors_reported': {'type': 'integer', 'minimum': 0, 'maximum': 32},
        }),
        'detectors': arr(coverage_detector, 0, 32),
    })
    cell_ratio_table = obj({
        'table_key': hash_value,
        'table_id': {'type': 'string', 'maxLength': 500},
        'label': empty_text,
        'caption': empty_text,
        'source_anchor': structured_anchor,
        'parser_status': enum('STRUCTURE_RELIABLE', 'TABLE_STRUCTURE_UNSUPPORTED'),
        'potential_objects': {'type': 'integer', 'minimum': 0, 'maximum': 50_001},
        'applicable_objects': {'type': 'integer', 'minimum': 0, 'maximum': 50_001},
        'eligible_objects': {'type': 'integer', 'minimum': 0, 'maximum': 50_001},
        'checked_objects': {'type': 'integer', 'minimum': 0, 'maximum': 50_001},
        'skipped_objects': {'type': 'integer', 'minimum': 0, 'maximum': 50_001},
        'candidate_count': {'type': 'integer', 'minimum': 0, 'maximum': 256},
        'potential_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'applicable_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'eligible_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'checked_matches': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'checked_mismatches': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'incomplete_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'unsupported_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'skipped_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'primary_skip_reason_counts': percentage_reason_counts,
        'relations': arr(percentage_relation, 0, 50_000),
        'status': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
        'reasons': arr(text(200), 0, 32),
        'skip_reasons': arr(text(100), 0, 32),
        'candidate_findings_omitted': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
    })
    cell_ratio_screen = obj({
        'detector_id': enum('jats_cell_ratio_percentage_recomputation'),
        'operand_unit': enum('n_over_N_percent_cell'),
        'findings': arr(cell_ratio_anomaly, 0, 256),
        'tables': arr(cell_ratio_table, 0, 1000),
        'potential_cells': {'type': 'integer', 'minimum': 0, 'maximum': 50_001},
        'checked_cells': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'skipped_cells': {'type': 'integer', 'minimum': 0, 'maximum': 50_001},
        'relations': arr(percentage_relation, 0, 50_000),
        'relation_telemetry': percentage_relation_telemetry,
        'candidate_findings_omitted': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
        'scan_complete': {'type': 'boolean'},
        'limitations': arr(text(200), 0, 100),
    })
    summary_stat_source_anchor = obj({'role': enum('n', 'sd', 'se'), 'source_anchor': structured_anchor})
    summary_stat_check = obj({
        'status': enum('CONSISTENT_WITH_ROUNDING', 'ARITHMETIC_CANDIDATE'),
        'type': {'oneOf': [enum('JATS_SD_SE_N_ARITHMETIC_MISMATCH'), {'type': 'null'}]},
        'table_id': {'type': 'string', 'maxLength': 500},
        'row_index': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'row_identity': empty_text,
        'n_exact': {'type': 'string', 'pattern': '^[1-9][0-9]{0,9}$'},
        'sd_exact': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})(?:\\.[0-9]{1,8})?$'},
        'reported_se': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})(?:\\.[0-9]{1,8})?$'},
        'recomputed_se_at_display_precision': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})(?:\\.[0-9]{1,8})?$'},
        'display_precision': {'type': 'integer', 'minimum': 0, 'maximum': 8},
        'difference_at_display_precision': {'type': 'string', 'pattern': '^(?:0|[1-9][0-9]{0,9})(?:\\.[0-9]{1,8})?$'},
        'source_anchors': arr(summary_stat_source_anchor, 3, 3),
    })
    summary_stat_table = obj({
        'table_id': {'type': 'string', 'maxLength': 500},
        'applicability': enum('APPLICABLE', 'NOT_APPLICABLE'),
        'eligibility': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
        'status': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
        'potential_objects': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'checked_objects': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'skipped_objects': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'checked_rows': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        'checks': arr(summary_stat_check, 0, 10_000),
        'candidate_count': {'type': 'integer', 'minimum': 0, 'maximum': 256},
        'candidates': arr(summary_stat_check, 0, 256),
        'skip_reasons': arr(obj({
            'reason': text(200),
            'row_index': {'type': 'integer', 'minimum': 0, 'maximum': 10_000},
        }, required=['reason']), 0, 10_000),
        'scan_complete': {'type': 'boolean'},
    })
    summary_stat_screen = obj({
        'detector_id': enum('jats_sd_se_n_recomputation'),
        'operand_unit': enum('eligible_sd_se_n_row'),
        'rounding_policy': {'type': 'string', 'maxLength': 200},
        'findings': arr(summary_stat_check, 0, 256),
        'tables': arr(summary_stat_table, 0, 1000),
        'scan_complete': {'type': 'boolean'},
        'limitations': arr(text(200), 0, 100),
    })
    nullable_bool = {'oneOf': [{'type': 'boolean'}, {'type': 'null'}]}
    flow_scope = obj({'population': text(500), 'group': text(500), 'timepoint': text(500)})
    flow_operand = obj({
        'identifier': text(100),
        'role': enum('total', 'exclusion', 'included'),
        'count': {'type': 'integer', 'minimum': 0, 'maximum': 1_000_000_000_000},
        'unit': text(100), 'population': text(500), 'group': text(500), 'timepoint': text(500),
        'source_anchor': structured_anchor,
    })
    flow_population = obj({
        'identifier': text(100), 'label': text(500), 'count_unit': text(100),
        'group': text(500), 'timepoint': text(500), 'source_anchor': structured_anchor,
    })
    flow_stage = obj({
        'identifier': text(100), 'label': text(100),
        'count': {'type': 'integer', 'minimum': 0, 'maximum': 1_000_000_000_000},
        'count_unit': text(100), 'scope': flow_scope, 'source_anchor': structured_anchor,
    })
    flow_transition = obj({
        'source_stage': text(100), 'target_stage': text(100), 'operation': nullable_text,
        'explicit': {'type': 'boolean'}, 'disjoint': nullable_bool, 'exhaustive': nullable_bool,
        'scope': flow_scope, 'source_anchor': structured_anchor,
    })
    flow_exclusion = obj({
        'identifier': text(100),
        'count': {'type': 'integer', 'minimum': 0, 'maximum': 1_000_000_000_000},
        'count_unit': text(100), 'population': text(500), 'reason': text(1000),
        'group': text(500), 'timepoint': text(500), 'count_anchor': structured_anchor,
        'reason_anchor': structured_anchor,
    })
    flow_arithmetic_relation = obj({
        'total_operand': text(100), 'exclusion_operands': arr(text(100), 0, 32),
        'included_operand': text(100), 'operator': nullable_text,
        'explicit': {'type': 'boolean'}, 'disjoint': nullable_bool, 'exhaustive': nullable_bool,
        'sequential': {'type': 'boolean'}, 'source_anchor': structured_anchor,
        'operand_anchors': arr(structured_anchor, 0, 34),
    })
    nullable_flow_entity = lambda entity: {'oneOf': [entity, {'type': 'null'}]}
    source_flow = obj({
        'id': {'type': 'string', 'pattern': '^source-flow-[0-9]{4}$'},
        'status': enum('FLOW_BALANCED', 'FLOW_ARITHMETIC_CANDIDATE', 'FLOW_RELATION_AMBIGUOUS', 'UNSUPPORTED'),
        'reason': nullable_text,
        'source_anchor': structured_anchor,
        'operands': arr(flow_operand, 0, 66),
        'population': nullable_flow_entity(flow_population),
        'stages': arr(flow_stage, 0, 66),
        'transitions': arr(flow_transition, 0, 66),
        'exclusions': arr(flow_exclusion, 0, 32),
        'arithmetic_relation': nullable_flow_entity(flow_arithmetic_relation),
        'arithmetic_status': enum('FLOW_BALANCED', 'FLOW_ARITHMETIC_CANDIDATE', 'FLOW_RELATION_AMBIGUOUS', 'UNSUPPORTED'),
    })
    source_flow_screen = obj({
        'detector_id': enum('jats_sample_flow_arithmetic'),
        'flows': arr(source_flow, 0, 256),
        'findings': arr(jats_flow_anomaly, 0, 256),
        'status': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
        'potential_objects': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
        'applicable_objects': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
        'eligible_objects': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
        'checked_objects': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
        'skipped_objects': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
        'candidate_count': {'type': 'integer', 'minimum': 0, 'maximum': 256},
        'scan_complete': {'type': 'boolean'},
        'limitations': arr(text(200), 0, 100),
    })
    prisma_object = {'oneOf': [
        obj({'kind': enum('figure'), 'label': empty_text, 'caption': empty_text,
             'graphic_present': {'type': 'boolean'}, 'source_anchor': structured_anchor}),
        obj({'kind': enum('table'), 'label': empty_text, 'caption': empty_text,
             'source_anchor': structured_anchor}),
        obj({'kind': enum('prose'), 'text': text(4000), 'source_anchor': structured_anchor}),
    ]}
    prisma_screen = obj({
        'detector_id': enum('prisma_synthesis_flow'),
        'status': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
        'objects': arr(prisma_object, 0, 256),
        'relations': arr(prisma_relation, 0, 256),
        'findings': arr(prisma_anomaly, 0, 256),
        'scan_complete': {'type': 'boolean'},
        'limitations': arr(text(200), 0, 16),
        'image_contents_read': {'const': False},
        'ocr_performed': {'const': False},
    })
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
        'paper_audit_version': enum('0.2', '0.3', '0.4'),
        'decision': enum(
            'CANDIDATES_FOUND', 'CANDIDATES_FOUND_IN_INCOMPLETE_SCAN',
            'NO_CANDIDATES_IN_SUPPORTED_SCAN', 'SCAN_INCOMPLETE_NO_CANDIDATES',
            'EXTRACTION_UNAVAILABLE_OR_EMPTY',
        ),
        'source': obj({
            'identifier': text(2000),
            'version': text(100),
            'capture_status': enum('unverified'),
            'source_file': enum('source.txt', 'source.md', 'source.markdown', 'source.pdf', 'source.xml', 'source.nxml'),
            'sha256': hash_value,
        }),
        'extraction': obj({
            'status': enum(
                'TEXT_AVAILABLE', 'PARTIAL_TEXT', 'NO_EXTRACTABLE_TEXT',
                'PARSER_UNAVAILABLE', 'MALFORMED_OR_UNSUPPORTED', 'LIMIT_OR_UNSUPPORTED',
                'RESOURCE_LIMIT_OR_TIMEOUT', 'WORKER_FAILED', 'WORKER_PROTOCOL_ERROR',
            ),
            'extractor': text(200),
            'original_format': enum('txt', 'md', 'markdown', 'pdf', 'jats_xml'),
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
            'layout_status': enum('TEXT_OR_MARKDOWN_OFFSETS', 'PDF_PAGE_AND_EXTRACTED_TEXT_OFFSETS_ONLY',
                                  'JATS_ELEMENT_PATHS_AND_TABLE_GRIDS', 'JATS_STRUCTURE_UNAVAILABLE'),
            'document_model': {'oneOf': [{'type': 'null'}, obj({
                'file': enum('paper-document.json'),
                'sha256': hash_value,
                'model_version': enum('1.0', '1.1'),
                'section_count': {'type': 'integer', 'minimum': 0, 'maximum': 512},
                'paragraph_count': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
                'table_count': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
                'figure_count': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
                'numeric_assertion_count': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
            }, required=['file', 'sha256', 'model_version', 'section_count', 'paragraph_count',
                         'table_count', 'numeric_assertion_count'])]},
        }, required=['sections', 'layout_status']),
        'source_capabilities': obj({
            'prose': enum('PROSE_TEXT_RELIABLE', 'SOURCE_NATIVE_PROSE_AVAILABLE', 'TABLE_STRUCTURE_UNSUPPORTED',
                          'EXTRACTION_DEGRADED', 'IMAGE_ONLY', 'EXTRACTION_FAILED'),
            'tables': enum('TABLE_STRUCTURE_UNSUPPORTED', 'STRUCTURED_JATS_TABLES', 'MARKDOWN_TABLE_ADAPTER'),
        }),
        'coverage': {'oneOf': [{'type': 'null'}, paper_coverage]},
        'detector_eligibility': arr(obj({
            'detector_id': enum('explicit_count_marker_scan', 'table_percentage_recomputation',
                                'markdown_table_percentage_recomputation', 'explicit_sample_flow_arithmetic',
                                'explicit_exclusion_flow_locator', 'two_by_two_effect_size_recomputation',
                                'cross_section_numeric_identity', 'jats_cell_ratio_percentage_recomputation',
                                'jats_sample_flow_arithmetic', 'jats_sd_se_n_recomputation',
                                'prisma_synthesis_flow', 'jats_unadjusted_2x2_odds_ratio',
                                'simple_rate_recomputation'),
            'contract_version': enum('1.0', '1.1', '1.2'),
            'status': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
            'source_format': enum('txt', 'md', 'markdown', 'pdf', 'jats_xml'),
            'reasons': arr(text(500), 0, 16),
            'checked_operands': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
            'table_id': {'type': 'string', 'maxLength': 500},
        }, required=['detector_id', 'contract_version', 'status', 'source_format', 'reasons', 'checked_operands']), 0, 4000),
        'detector_contracts': arr(obj({
            'detector_id': {'type': 'string', 'maxLength': 100},
            'version': enum('1.0', '1.1', '1.2'),
            'implementation_status': {'type': 'string', 'maxLength': 60},
            'purpose': {'type': 'string', 'maxLength': 100},
            'required_source_structure': arr(text(500), 1, 8),
            'required_operands': arr(text(500), 1, 16),
            'required_context': arr(text(500), 1, 16),
            'allowed_ambiguity': arr(text(500), 0, 8),
            'rounding_policy': {'type': 'string', 'maxLength': 200},
            'units': arr(text(100), 1, 8),
            'exclusions': arr(text(500), 0, 16),
            'positive_result_establishes': {'type': 'string', 'maxLength': 1000},
            'positive_result_does_not_establish': {'type': 'string', 'maxLength': 1000},
            'unsupported_or_incomplete_reasons': arr(text(200), 1, 16),
            'relationship_types': obj({
                'checked': arr(text(100), 1, 4),
                'out_of_scope': arr(text(100), 1, 8),
            }),
            'supported_source_formats': arr(text(100), 0, 8),
            'required_document_objects': arr(text(500), 0, 16),
            'scope_requirements': arr(text(500), 0, 16),
            'unit_requirements': arr(text(100), 0, 8),
            'statistical_assumptions': arr(text(500), 0, 16),
            'ambiguity_conditions': arr(text(500), 0, 8),
            'outputs': arr(text(200), 0, 16),
        }, required=['detector_id', 'version', 'implementation_status', 'purpose', 'required_source_structure', 'required_operands',
                     'required_context', 'allowed_ambiguity', 'rounding_policy', 'units', 'exclusions',
                     'positive_result_establishes', 'positive_result_does_not_establish',
                     'unsupported_or_incomplete_reasons']), 4, 16),
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
                'tables_seen': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
            }, required=['discoverer', 'findings', 'possible_scope_differences', 'checked_cells',
                         'cells_scanned', 'supported', 'scan_complete', 'limitations']),
            'sample_exclusion_flow': obj({
                'discoverer': enum('explicit_exclusion_flow_arithmetic_screen'),
                'candidate_anomalies': arr(flow_anomaly, 0, 64),
                'ambiguous_relations': arr(obj({
                    'id': {'type': 'string', 'pattern': '^ambiguous-flow-[0-9]{4}$'},
                    'status': enum('FLOW_RELATION_AMBIGUOUS'),
                    'source_total_exact': small_int_string,
                    'excluded_values_exact': arr(small_int_string, 1, 64),
                    'reported_included_exact': small_int_string,
                    'source_anchors': arr(anchor, 3, 66),
                    'interpretation': text(1000),
                    'required_review': text(1000),
                }), 0, 64),
                'scan_complete': {'type': 'boolean'},
                'limitations': arr(text(1000), 0, 16),
            }, required=['discoverer', 'candidate_anomalies', 'scan_complete', 'limitations']),
            'structured_table_percentages': obj({
                'detector_id': enum('table_percentage_recomputation'),
                'findings': arr(structured_table_anomaly, 0, 256),
                'tables': arr(obj({
                    'table_id': {'type': 'string', 'maxLength': 500},
                    'status': enum('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'),
                    'reasons': arr(text(200), 0, 32),
                    'candidate_findings_omitted': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'checked_cells': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
                    'candidate_count': {'type': 'integer', 'minimum': 0, 'maximum': 256},
                    'potential_objects': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'potential_cells': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'potential_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'applicable_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'eligible_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'checked_matches': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'checked_mismatches': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'incomplete_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'unsupported_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'skipped_relations': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                    'primary_skip_reason_counts': percentage_reason_counts,
                    'relations': arr(percentage_relation, 0, 50_000),
                }), 0, 1000),
                'checked_cells': {'type': 'integer', 'minimum': 0, 'maximum': 100_000},
                'relations': arr(percentage_relation, 0, 50_000),
                'relation_telemetry': percentage_relation_telemetry,
                'candidate_findings_omitted': {'type': 'integer', 'minimum': 0, 'maximum': 50_000},
                'scan_complete': {'type': 'boolean'},
                'limitations': arr(text(200), 0, 100),
            }),
            'cell_ratio_percentages': cell_ratio_screen,
            'percentage_relation_telemetry': percentage_relation_telemetry,
            'sd_se_n_statistics': summary_stat_screen,
            'source_mapped_sample_flow': source_flow_screen,
            'prisma_synthesis_flow': prisma_screen,
            'jats_unadjusted_2x2_odds_ratio': obj({
                'detector_id': enum('jats_unadjusted_2x2_odds_ratio'),
                'operand_unit': enum('explicit_2x2_row'),
                'findings': arr(two_by_two_anomaly, 0, 256),
                'tables': arr(two_by_two_table, 0, 1000),
                'scan_complete': {'type': 'boolean'},
                'limitations': arr(text(200), 0, 100),
            }),
        }, required=['table_percentages', 'sample_exclusion_flow']),
        'candidate_anomalies': arr(candidate, 0, 1200),
        'possible_scope_differences': arr(scope_difference, 0, 256),
        'checks_attempted': arr(enum(
            'explicit_count_marker_scan', 'markdown_table_percentage_recomputation',
            'explicit_exclusion_flow_arithmetic_screen',
            'jats_table_percentage_recomputation',
            'jats_cell_ratio_percentage_recomputation', 'jats_sd_se_n_recomputation',
            'jats_sample_flow_arithmetic', 'prisma_synthesis_flow',
            'jats_unadjusted_2x2_odds_ratio',
        ), 0, 9),
        'verified_findings': arr({'type': 'object'}, 0, 0),
        'unresolved_questions': arr(text(1000), 0, 1200),
        'unsupported_checks': arr(text(500), 1, 16),
        'known_corrections': obj({'status': enum('NOT_CHECKED')}),
        'paper_error_established': {'const': False},
        'meaning': text(1000),
    }, required=[
        'paper_audit_version', 'decision', 'source', 'extraction', 'paper_structure', 'discovery',
        'arithmetic_screens', 'candidate_anomalies', 'possible_scope_differences', 'checks_attempted',
        'verified_findings', 'unresolved_questions', 'unsupported_checks', 'known_corrections',
        'paper_error_established', 'meaning',
    ])
    report['allOf'] = [{
        'if': {
            'properties': {'paper_audit_version': {'const': '0.4'}},
            'required': ['paper_audit_version'],
        },
        'then': {
            'required': ['coverage'],
            'properties': {
                'arithmetic_screens': {'required': [
                    'cell_ratio_percentages', 'sd_se_n_statistics',
                    'source_mapped_sample_flow', 'prisma_synthesis_flow',
                    'jats_unadjusted_2x2_odds_ratio',
                ]},
                'detector_contracts': {'items': {'required': [
                    'supported_source_formats', 'required_document_objects', 'scope_requirements',
                    'unit_requirements', 'statistical_assumptions', 'ambiguity_conditions', 'outputs',
                ]}},
            },
        },
    }]
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:researchwitness:paper-audit-report:0.4',
        'title': 'ResearchWitness bounded paper-screening report 0.4',
        'description': (
            'Source-aware paper screening with machine-readable eligibility contracts. All flags remain candidates; '
            'a negative result does not establish correctness.'
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
