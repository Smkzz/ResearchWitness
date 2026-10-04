"""Allowlisted deterministic proof checkers. Never execute a paper's code."""
from __future__ import annotations
from fractions import Fraction as F
from itertools import product
from typing import Any
from .strict import fields, require, integer, text
from .arithmetic import rational, radical_sum, sqrt_interval, Interval, bounded_fraction

KINDS = {
    'scalar_radical_comparison',
    'polynomial_upper_bound',
    'uc_binary_upper_bound',
    'finite_field_polynomial_residue',
    'finite_field_quadratic_quartic_residue_rule',
    'finite_map_fixed_point',
    'finite_graph_chromatic_lower_bound',
    'finite_pmf_bound',
}

MAX_GRAPH_VERTICES = 256
MAX_GRAPH_EDGES = 8192
MAX_GRAPH_LABEL_LENGTH = 64


def capabilities() -> list[dict[str, Any]]:
    """Return machine-readable checker capabilities for research agents."""
    return [
        {
            'kind': 'scalar_radical_comparison',
            'proves': 'An explicit radical/scalar expression exceeds an explicit bound.',
            'limits': 'Exact rational inputs plus square-root interval enclosures only.',
        },
        {
            'kind': 'polynomial_upper_bound',
            'proves': 'A rational point in a bounded domain violates an explicit polynomial upper bound.',
            'limits': 'At most 8 variables, degree 12, 64 terms.',
        },
        {
            'kind': 'uc_binary_upper_bound',
            'proves': 'The explicit finite independent-source UC witness exceeds the configured functional bound.',
            'limits': 'Specialized regression checker for one binary UC functional.',
        },
        {
            'kind': 'finite_field_polynomial_residue',
            'proves': 'Exact finite-field enumeration gives a solution-count residue outside the allowed residues.',
            'limits': 'Prime fields p<=251; at most 3 enumerated variables, 4 witness parameters, degree 12.',
        },
        {
            'kind': 'finite_field_quadratic_quartic_residue_rule',
            'proves': 'Exact finite-field enumeration contradicts a count-residue rule selected by quadratic/quartic power class.',
            'limits': 'Prime fields p<=251; nonzero classified parameter; bounded polynomial enumeration.',
        },
        {
            'kind': 'finite_map_fixed_point',
            'proves': 'An explicit finite self-map has no fixed point when the formalized conclusion requires one.',
            'limits': 'Checks the finite-map conclusion only; theorem premises must be verified separately.',
        },
        {
            'kind': 'finite_graph_chromatic_lower_bound',
            'proves': 'A proper coloring of an explicit graph uses fewer colors than a claimed chromatic-number lower bound.',
            'limits': 'Simple undirected graph; 1..256 vertices, 0..8,192 edges, labels up to 64 characters, and claimed bound 1..256. Checks a supplied coloring in O(V+E); does not search for an optimal coloring.',
        },
        {
            'kind': 'finite_pmf_bound',
            'proves': 'An exact finite PMF event probability or expected payoff violates a rational bound.',
            'limits': ('At most 8 variables, 64 outcomes per variable, 256 joint states and 64 event clauses; '
                       'categorical outcomes and exact rational masses/payoffs. Empirical validity and '
                       'population/generalized conclusions are outside scope.'),
        },
    ]


def _comparison(left: Interval, right: Interval, detail: dict | None = None) -> dict:
    margin = left.subtract(right)
    if margin.lo > 0:
        status = 'REFUTED_FOR_FORMALIZATION'
    elif margin.hi <= 0:
        status = 'NO_REFUTATION_AT_WITNESS'
    else:
        status = 'INCONCLUSIVE_INTERVAL'
    return {'status': status, 'left': left.record(), 'upper_bound': right.record(),
            'margin': margin.record(), 'detail': detail or {},
            'scope': 'Only this formalization and witness; source alignment is not machine-proved.'}


def _predicate(status: bool, detail: dict, statement: str) -> dict:
    """Encode an exactly decided Boolean counterexample predicate.

    status=True means the witness violates the formalized claim.
    """
    return {
        'status': 'REFUTED_FOR_FORMALIZATION' if status else 'NO_REFUTATION_AT_WITNESS',
        'left': None,
        'upper_bound': None,
        'margin': None,
        'detail': detail,
        'predicate': statement,
        'scope': 'Only this formalization and witness; source alignment is not machine-proved.',
    }


def check(formalization: Any, witness: Any, digits: int = 40) -> dict:
    integer(digits, 1, 80)
    require(type(formalization) is dict, 'Formalization must be an object')
    kind = formalization.get('kind')
    require(type(kind) is str and kind in KINDS, 'Unsupported proof kind')
    if kind == 'scalar_radical_comparison':
        fields(formalization, {'kind', 'left', 'upper_bound'})
        fields(witness, {'kind'})
        require(witness['kind'] == kind, 'Witness type mismatch')
        return _comparison(radical_sum(formalization['left'], digits),
                           radical_sum(formalization['upper_bound'], digits))
    if kind == 'polynomial_upper_bound':
        return _polynomial(formalization, witness)
    if kind == 'uc_binary_upper_bound':
        return _uc_binary(formalization, witness, digits)
    if kind == 'finite_field_polynomial_residue':
        return _finite_field_polynomial_residue(formalization, witness)
    if kind == 'finite_field_quadratic_quartic_residue_rule':
        return _finite_field_quadratic_quartic_residue_rule(formalization, witness)
    if kind == 'finite_graph_chromatic_lower_bound':
        return _finite_graph_chromatic_lower_bound(formalization, witness)
    if kind == 'finite_pmf_bound':
        return _finite_pmf_bound(formalization, witness)
    return _finite_map_fixed_point(formalization, witness)


def _pmf_name(value: Any) -> str:
    name = text(value, 24)
    require(name.isascii() and name.isidentifier(), 'Invalid PMF variable name')
    return name


def _pmf_domains(raw: Any) -> tuple[list[str], dict[str, list[str]], list[tuple[str, ...]]]:
    require(type(raw) is dict and 1 <= len(raw) <= 8, 'Need 1 to 8 finite PMF variables')
    names: list[str] = []
    domains: dict[str, list[str]] = {}
    sample_size = 1
    for raw_name, raw_values in raw.items():
        name = _pmf_name(raw_name)
        require(name not in domains, 'Duplicate PMF variable name')
        require(type(raw_values) is list and 1 <= len(raw_values) <= 64,
                'Each PMF variable needs 1 to 64 outcomes')
        values = [text(value, 100) for value in raw_values]
        require(len(set(values)) == len(values), 'Duplicate PMF outcome')
        sample_size *= len(values)
        require(sample_size <= 256, 'Finite PMF sample-space limit exceeded')
        names.append(name)
        domains[name] = values
    states = list(product(*(domains[name] for name in names)))
    return names, domains, states


def _pmf_assignment(value: Any, names: list[str], domains: dict[str, list[str]],
                    *, partial: bool) -> tuple[str, ...] | dict[str, str]:
    require(type(value) is dict, 'PMF assignment must be an object')
    keys = set(value)
    require(keys <= set(names), 'Unknown PMF variable')
    if not partial:
        require(keys == set(names), 'PMF assignment must name every variable')
    parsed: dict[str, str] = {}
    for name, outcome in value.items():
        require(type(name) is str and name in domains, 'Unknown PMF variable')
        label = text(outcome, 100)
        require(label in domains[name], 'PMF outcome outside declared domain')
        parsed[name] = label
    if partial:
        return parsed
    return tuple(parsed[name] for name in names)


def _finite_pmf_bound(spec: Any, witness: Any) -> dict:
    require(type(spec) is dict, 'Formalization must be an object')
    operation = spec.get('operation')
    if operation == 'probability':
        fields(spec, {'kind', 'operation', 'domains', 'event', 'relation', 'bound'})
    elif operation == 'expectation':
        fields(spec, {'kind', 'operation', 'domains', 'payoffs', 'relation', 'bound'})
    else:
        require(False, 'Unsupported finite PMF operation')
    require(spec['kind'] == 'finite_pmf_bound', 'Formalization type mismatch')
    require(spec['relation'] in ('at_most', 'at_least'), 'Unsupported PMF bound relation')
    bound = rational(spec['bound'])
    names, domains, states = _pmf_domains(spec['domains'])
    if operation == 'probability':
        require(0 <= bound <= 1, 'Probability bound must lie in [0,1]')

    fields(witness, {'kind', 'atoms'})
    require(witness['kind'] == spec['kind'], 'Witness type mismatch')
    atoms = witness['atoms']
    require(type(atoms) is list and 1 <= len(atoms) <= 256, 'Invalid finite PMF support')
    masses: dict[tuple[str, ...], F] = {}
    total = F(0)
    for atom in atoms:
        fields(atom, {'assignment', 'probability'})
        state = _pmf_assignment(atom['assignment'], names, domains, partial=False)
        require(state not in masses, 'Duplicate PMF support atom')
        mass = rational(atom['probability'])
        require(0 < mass <= 1, 'PMF support masses must lie in (0,1]')
        masses[state] = mass
        total = bounded_fraction(total + mass)
    require(total == 1, 'PMF support masses must sum exactly to one')

    if operation == 'probability':
        events = spec['event']
        require(type(events) is list and len(events) <= 64, 'Too many PMF event clauses')
        clauses = [_pmf_assignment(clause, names, domains, partial=True) for clause in events]
        value = F(0)
        for state, mass in masses.items():
            env = dict(zip(names, state))
            if any(all(env[name] == outcome for name, outcome in clause.items())
                   for clause in clauses):
                value = bounded_fraction(value + mass)
        arithmetic = 'event_probability'
        result_detail: dict[str, Any] = {
            'event_union': clauses,
        }
        predicate = 'finite_pmf_event_probability_violates_bound'
    else:
        payoffs = spec['payoffs']
        require(type(payoffs) is list and len(payoffs) == len(states),
                'Payoff table must cover the complete finite sample space')
        payoff_by_state: dict[tuple[str, ...], F] = {}
        for row in payoffs:
            fields(row, {'assignment', 'value'})
            state = _pmf_assignment(row['assignment'], names, domains, partial=False)
            require(state not in payoff_by_state, 'Duplicate payoff assignment')
            payoff_by_state[state] = rational(row['value'])
        require(set(payoff_by_state) == set(states),
                'Payoff table must cover every finite sample-space state exactly once')
        value = F(0)
        for state, mass in masses.items():
            term = bounded_fraction(mass * payoff_by_state[state])
            value = bounded_fraction(value + term)
        arithmetic = 'expected_payoff'
        result_detail = {'payoff_states': len(payoff_by_state)}
        predicate = 'finite_pmf_expected_payoff_violates_bound'

    margin = bounded_fraction(value - bound)
    violates = margin > 0 if spec['relation'] == 'at_most' else margin < 0
    detail = {
        'operation': arithmetic,
        'sample_space_size': len(states),
        'positive_mass_atom_count': len(masses),
        'total_probability_exact': str(total),
        'quantity_exact': str(value),
        'relation': spec['relation'],
        'bound_exact': str(bound),
        'signed_margin_exact': str(margin),
        'omitted_states_have_probability': '0',
        'empirical_or_generalized_conclusion': 'NOT_ESTABLISHED_BY_THIS_CHECKER',
        **result_detail,
    }
    return {
        'status': 'REFUTED_FOR_FORMALIZATION' if violates else 'NO_REFUTATION_AT_WITNESS',
        'left': None,
        'upper_bound': None,
        'margin': None,
        'detail': detail,
        'predicate': predicate,
        'scope': ('Exact arithmetic for the supplied finite PMF and formalization only; '
                  'empirical validity and population/generalized conclusions are not established.'),
    }


def _polynomial(spec: dict, witness: Any) -> dict:
    fields(spec, {'kind', 'domain', 'terms', 'upper_bound'})
    fields(witness, {'kind', 'point'})
    require(witness['kind'] == spec['kind'], 'Witness type mismatch')
    domain, point, terms = spec['domain'], witness['point'], spec['terms']
    require(type(domain) is dict and 1 <= len(domain) <= 8, 'Invalid domain')
    require(type(point) is dict and set(point) == set(domain), 'Point variables must match domain exactly')
    values = {}
    for name, bounds in domain.items():
        require(type(name) is str and name.isascii() and name.isidentifier() and len(name) <= 24,
                'Invalid variable name')
        fields(bounds, {'lower', 'upper', 'lower_closed', 'upper_closed'})
        require(type(bounds['lower_closed']) is bool and type(bounds['upper_closed']) is bool,
                'Endpoint flags must be booleans')
        lo, hi = rational(bounds['lower']), rational(bounds['upper'])
        require(lo <= hi, 'Reversed domain')
        require(lo != hi or (bounds['lower_closed'] and bounds['upper_closed']), 'Empty domain')
        x = rational(point[name])
        require((x >= lo if bounds['lower_closed'] else x > lo) and
                (x <= hi if bounds['upper_closed'] else x < hi), 'Witness outside domain')
        values[name] = x
    require(type(terms) is list and len(terms) <= 64, 'Too many polynomial terms')
    total = F(0)
    for term in terms:
        fields(term, {'coefficient', 'powers'})
        require(type(term['powers']) is dict and set(term['powers']) <= set(domain), 'Unknown polynomial variable')
        value = rational(term['coefficient'])
        require(sum(integer(p, 0, 12) for p in term['powers'].values()) <= 12, 'Total polynomial degree too high')
        for name, power in term['powers'].items():
            value *= values[name] ** power
        total = bounded_fraction(total + bounded_fraction(value))
    bound = rational(spec['upper_bound'])
    return _comparison(Interval(total, total), Interval(bound, bound), {'point': point, 'value_exact': str(total)})


def uc_table(witness: Any) -> dict[tuple[int, int, int], F]:
    """Construct the finite UC model: independent 2-bit sources, bit-index responses.

    Source/model equivalence to a particular paper is outside this checker.
    """
    fields(witness, {'kind', 'gamma', 'alpha', 'b0'})
    require(witness['kind'] == 'uc_binary_upper_bound', 'Witness type mismatch')
    sources = []
    for name in ('gamma', 'alpha'):
        source = witness[name]
        require(type(source) is list and len(source) == 4, 'Four latent weights required')
        values = [rational(x) for x in source]
        require(all(0 <= x <= 1 for x in values) and sum(values) == 1, 'Invalid source probability vector')
        sources.append(values)
    kernel = witness['b0']
    require(type(kernel) is list and len(kernel) == 4, 'Kernel must be 4 by 4')
    table = {}
    for row in kernel:
        require(type(row) is list and len(row) == 4, 'Kernel must be 4 by 4')
    matrix = [[rational(x) for x in row] for row in kernel]
    require(all(0 <= x <= 1 for row in matrix for x in row), 'Conditional probability outside [0,1]')
    labels = ((0, 0), (0, 1), (1, 0), (1, 1))
    for a, b, c in product(range(2), repeat=3):
        table[a, b, c] = sum((sources[0][g] * sources[1][h] *
                              (matrix[g][h] if b == 0 else 1 - matrix[g][h])
                              for g in range(4) for h in range(4)
                              if labels[g][b] == a and labels[h][b] == c), F(0))
    for mass in table.values():
        bounded_fraction(mass)
    require(sum(table.values()) == 1 and all(x >= 0 for x in table.values()), 'Constructed table invalid')
    return table


def _uc_binary(spec: dict, witness: Any, digits: int) -> dict:
    fields(spec, {'kind', 'functional', 'upper_bound'})
    require(spec['functional'] == 'uc_sqrt_penalty_v1', 'Unknown UC functional')
    p = uc_table(witness)
    p000, p001, p010, p011, p100, p101, p110, p111 = (p[t] for t in product(range(2), repeat=3))
    q = F(1, 4)
    penalty = (18 * abs(p000 + p001 + p100 + p101 - q)
               + 18 * abs(p011 + p110 - q)
               + 4 * abs(p010 - q) + 4 * abs(p111 - q)
               + 4 * abs(p010 - p011 - p110 + p111 - q)
               + abs(2 * p010 - 2 * p111)
               + abs(p000 + p001 - p100 - p101)
               + abs(p000 + p100 - p001 - p101))
    left = Interval(-penalty, -penalty)
    for coefficient, mass in ((2, p000), (2, p101), (3, p110)):
        left = left.add(sqrt_interval(mass, digits).scale(F(coefficient)))
    return _comparison(left, radical_sum(spec['upper_bound'], digits),
                       {'probabilities': {''.join(map(str, k)): str(v) for k, v in p.items()},
                        'penalty_exact': str(penalty),
                        'global_optimum': 'NOT_ESTABLISHED', 'global_upper_bound': 'NOT_ESTABLISHED'})


def _prime(value: Any) -> int:
    p = integer(value, 2, 251)
    d = 2
    while d * d <= p:
        require(p % d != 0, 'Field modulus must be prime')
        d += 1
    return p


def _finite_name(value: Any) -> str:
    value = text(value, 24)
    require(value.isascii() and value.isidentifier(), 'Invalid finite-field symbol')
    return value


def _ff_enumerate(spec: dict, witness: Any, extra_required: set[str]) -> tuple[int, dict[str, int], list[str], int]:
    base = {'kind', 'prime', 'variables', 'parameters', 'terms', 'point_count_adjustment', 'modulus'}
    fields(spec, base | extra_required)
    fields(witness, {'kind', 'parameters'})
    require(witness['kind'] == spec['kind'], 'Witness type mismatch')
    p = _prime(spec['prime'])
    variables = spec['variables']
    parameters = spec['parameters']
    require(type(variables) is list and 1 <= len(variables) <= 3, 'Need 1 to 3 enumerated variables')
    require(type(parameters) is list and len(parameters) <= 4, 'Too many finite-field parameters')
    variables = [_finite_name(x) for x in variables]
    parameters = [_finite_name(x) for x in parameters]
    require(len(set(variables + parameters)) == len(variables) + len(parameters), 'Duplicate finite-field symbol')
    supplied = witness['parameters']
    require(type(supplied) is dict and set(supplied) == set(parameters), 'Witness parameters must match exactly')
    param_values = {name: integer(value, -10**9, 10**9) % p for name, value in supplied.items()}
    terms = spec['terms']
    require(type(terms) is list and 1 <= len(terms) <= 64, 'Invalid finite-field polynomial')
    parsed_terms: list[tuple[int, dict[str, int]]] = []
    symbols = set(variables + parameters)
    for term in terms:
        fields(term, {'coefficient', 'powers'})
        coefficient = integer(term['coefficient'], -10**9, 10**9) % p
        powers = term['powers']
        require(type(powers) is dict and set(powers) <= symbols, 'Unknown finite-field polynomial symbol')
        parsed = {name: integer(power, 0, 12) for name, power in powers.items()}
        require(sum(parsed.values()) <= 12, 'Finite-field polynomial degree too high')
        parsed_terms.append((coefficient, parsed))
    adjustment = integer(spec['point_count_adjustment'], -1000, 1000)
    modulus = integer(spec['modulus'], 2, 4096)
    enumeration_size = p ** len(variables)
    require(enumeration_size <= 2_000_000, 'Finite-field enumeration budget exceeded')
    require(enumeration_size * len(parsed_terms) <= 5_000_000, 'Finite-field work budget exceeded')
    count = 0
    for values in product(range(p), repeat=len(variables)):
        env = dict(param_values)
        env.update(dict(zip(variables, values)))
        total = 0
        for coefficient, powers in parsed_terms:
            value = coefficient
            for name, power in powers.items():
                value = (value * pow(env[name], power, p)) % p
            total = (total + value) % p
        if total == 0:
            count += 1
    count += adjustment
    require(count >= 0, 'Negative adjusted solution count')
    return p, param_values, variables, count


def _finite_field_polynomial_residue(spec: dict, witness: Any) -> dict:
    p, param_values, variables, count = _ff_enumerate(spec, witness, {'allowed_residues'})
    modulus = spec['modulus']
    allowed = spec['allowed_residues']
    require(type(allowed) is list and 1 <= len(allowed) <= modulus, 'Invalid allowed residues')
    allowed = [integer(x, 0, modulus - 1) for x in allowed]
    require(len(set(allowed)) == len(allowed), 'Duplicate allowed residue')
    residue = count % modulus
    violates = residue not in set(allowed)
    return _predicate(violates, {
        'prime': p,
        'enumerated_variables': variables,
        'parameters_mod_p': {k: param_values[k] for k in sorted(param_values)},
        'point_count_adjustment': spec['point_count_adjustment'],
        'total_solution_count': count,
        'modulus': modulus,
        'observed_residue': residue,
        'allowed_residues': allowed,
        'enumeration_size': p ** len(variables),
    }, 'solution_count_modulus_in_allowed_residues')


def _finite_field_quadratic_quartic_residue_rule(spec: dict, witness: Any) -> dict:
    p, param_values, variables, count = _ff_enumerate(
        spec, witness, {'classification_parameter', 'expected_residues'})
    parameter = _finite_name(spec['classification_parameter'])
    require(parameter in param_values, 'Classification parameter must be a witness parameter')
    value = param_values[parameter]
    require(value != 0, 'Power-classified parameter must be nonzero')
    expected = spec['expected_residues']
    fields(expected, {'quartic_residue', 'quadratic_nonquartic', 'quadratic_nonresidue'})
    modulus = spec['modulus']
    parsed_expected: dict[str, list[int]] = {}
    for name, residues in expected.items():
        require(type(residues) is list and 1 <= len(residues) <= modulus, 'Invalid expected residue list')
        parsed = [integer(x, 0, modulus - 1) for x in residues]
        require(len(set(parsed)) == len(parsed), 'Duplicate expected residue')
        parsed_expected[name] = parsed
    nonzero = range(1, p)
    squares = {pow(x, 2, p) for x in nonzero}
    fourths = {pow(x, 4, p) for x in nonzero}
    if value in fourths:
        power_class = 'quartic_residue'
    elif value in squares:
        power_class = 'quadratic_nonquartic'
    else:
        power_class = 'quadratic_nonresidue'
    allowed = parsed_expected[power_class]
    residue = count % modulus
    return _predicate(residue not in set(allowed), {
        'prime': p,
        'enumerated_variables': variables,
        'parameters_mod_p': {k: param_values[k] for k in sorted(param_values)},
        'classification_parameter': parameter,
        'power_class': power_class,
        'point_count_adjustment': spec['point_count_adjustment'],
        'total_solution_count': count,
        'modulus': modulus,
        'observed_residue': residue,
        'expected_residues_for_class': allowed,
        'enumeration_size': p ** len(variables),
    }, 'solution_count_residue_matches_quadratic_quartic_power_class_rule')

def _finite_map_fixed_point(spec: dict, witness: Any) -> dict:
    fields(spec, {'kind', 'universe', 'conclusion'})
    fields(witness, {'kind', 'mapping'})
    require(witness['kind'] == spec['kind'], 'Witness type mismatch')
    universe = spec['universe']
    require(type(universe) is list and 1 <= len(universe) <= 256, 'Invalid finite universe')
    universe = [text(x, 100) for x in universe]
    require(len(set(universe)) == len(universe), 'Duplicate universe element')
    require(spec['conclusion'] == 'has_fixed_point', 'Unsupported finite-map conclusion')
    mapping = witness['mapping']
    require(type(mapping) is dict and set(mapping) == set(universe), 'Mapping domain must equal universe')
    require(all(type(v) is str and v in set(universe) for v in mapping.values()), 'Mapping must be a self-map')
    fixed = sorted(x for x in universe if mapping[x] == x)
    return _predicate(not fixed, {
        'universe_size': len(universe),
        'mapping': {k: mapping[k] for k in sorted(mapping)},
        'fixed_points': fixed,
        'theorem_premises': 'NOT_ESTABLISHED_BY_THIS_CHECKER',
    }, 'finite_self_map_has_fixed_point')


def _graph_label(value: Any) -> str:
    value = text(value, MAX_GRAPH_LABEL_LENGTH)
    require(all(ord(char) >= 32 for char in value), 'Graph labels must be printable')
    return value


def _finite_graph_chromatic_lower_bound(spec: dict, witness: Any) -> dict:
    fields(spec, {'kind', 'vertices', 'edges', 'minimum_colors'})
    fields(witness, {'kind', 'coloring'})
    require(witness['kind'] == spec['kind'], 'Witness type mismatch')

    vertices = spec['vertices']
    require(type(vertices) is list and 1 <= len(vertices) <= MAX_GRAPH_VERTICES,
            'Invalid finite graph vertex list')
    vertices = [_graph_label(vertex) for vertex in vertices]
    vertex_set = set(vertices)
    require(len(vertex_set) == len(vertices), 'Duplicate graph vertex')

    raw_edges = spec['edges']
    require(type(raw_edges) is list and len(raw_edges) <= MAX_GRAPH_EDGES,
            'Invalid finite graph edge list')
    edges: list[tuple[str, str]] = []
    edge_set: set[tuple[str, str]] = set()
    for edge in raw_edges:
        require(type(edge) is list and len(edge) == 2, 'Graph edges must be endpoint pairs')
        left, right = (_graph_label(endpoint) for endpoint in edge)
        require(left in vertex_set and right in vertex_set, 'Graph edge endpoint is not a vertex')
        require(left != right, 'Self-loops are unsupported in simple graphs')
        normalized = tuple(sorted((left, right)))
        require(normalized not in edge_set, 'Duplicate graph edge')
        edge_set.add(normalized)
        edges.append(normalized)

    minimum_colors = integer(spec['minimum_colors'], 1, MAX_GRAPH_VERTICES)
    coloring = witness['coloring']
    require(type(coloring) is dict and set(coloring) == vertex_set,
            'Coloring domain must equal graph vertices exactly')
    parsed_coloring = {vertex: _graph_label(coloring[vertex]) for vertex in vertices}
    conflicts = [(left, right) for left, right in edges
                 if parsed_coloring[left] == parsed_coloring[right]]
    require(not conflicts, 'Witness coloring is not proper')

    color_classes: dict[str, list[str]] = {}
    for vertex, color in parsed_coloring.items():
        color_classes.setdefault(color, []).append(vertex)
    colors_used = len(color_classes)
    return _predicate(colors_used < minimum_colors, {
        'vertex_count': len(vertices),
        'edge_count': len(edges),
        'minimum_colors_claimed': minimum_colors,
        'colors_used': colors_used,
        'color_classes': color_classes,
    }, 'chromatic_number_at_least_minimum_colors')
