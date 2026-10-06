"""Machine-readable applicability contracts for paper-screen detectors."""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = '1.1'

_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        'detector_id': 'explicit_count_marker_scan',
        'version': CONTRACT_VERSION,
        'implementation_status': 'ACTIVE_SOURCE_DETECTOR',
        'purpose': 'candidate_discovery_only',
        'required_source_structure': ['PROSE_TEXT_RELIABLE'],
        'required_operands': ['two or more explicit n/N integer assertions'],
        'required_context': ['source anchors', 'separate prose passages'],
        'allowed_ambiguity': ['cohort identity may differ; keep as candidate context only'],
        'rounding_policy': 'not_applicable',
        'units': ['count'],
        'exclusions': ['JATS prose until source-native text anchors are mapped'],
        'positive_result_establishes': 'Different explicit count strings occur in separate passages.',
        'positive_result_does_not_establish': 'That the counts refer to one population, are inconsistent, or affect a conclusion.',
        'unsupported_or_incomplete_reasons': ['PROSE_TEXT_UNAVAILABLE', 'SOURCE_NATIVE_ANCHOR_UNAVAILABLE'],
    },
    {
        'detector_id': 'table_percentage_recomputation',
        'version': CONTRACT_VERSION,
        'implementation_status': 'ACTIVE_JATS_TABLE_DETECTOR',
        'purpose': 'exact_arithmetic_candidate',
        'required_source_structure': ['RESOLVED_TABLE_GRID', 'EXPLICIT_HEADER_HIERARCHY'],
        'required_operands': ['one integer numerator', 'one explicit denominator', 'one displayed percentage'],
        'required_context': [
            'denominator applies to the same cell by resolved header',
            'row identity and measure header are available',
            'display precision is known',
        ],
        'allowed_ambiguity': ['none affecting the operands or denominator scope'],
        'rounding_policy': 'ROUND_HALF_UP to displayed precision; exact ties round away from zero',
        'units': ['count', 'percent'],
        'exclusions': [
            'PDF table layout', 'local or unresolved denominator', 'footnoted operands or denominator',
            'weighted or adjusted estimates', 'multiple response or overlapping categories',
            'missing-data or available-case subset cue',
        ],
        'positive_result_establishes': 'The displayed percentage differs from ROUND_HALF_UP of the exact count/denominator ratio at its displayed precision.',
        'positive_result_does_not_establish': 'That the paper is wrong, that the table values were extracted faithfully, or that any conclusion changes.',
        'unsupported_or_incomplete_reasons': [
            'TABLE_STRUCTURE_UNSUPPORTED', 'NO_EXPLICIT_COLUMN_DENOMINATOR',
            'CONFLICTING_HEADER_DENOMINATORS', 'LOCAL_DENOMINATOR', 'LOCAL_GROUP_DENOMINATOR_INDICATED',
            'FOOTNOTE_SCOPE_UNRESOLVED', 'FOOTNOTED_OR_SCOPED_ROW_LABEL',
            'WEIGHTED_OR_ADJUSTED', 'OVERLAPPING_OR_MULTIPLE_RESPONSE', 'MISSING_DATA_SCOPE',
        ],
    },
    {
        'detector_id': 'markdown_table_percentage_recomputation',
        'version': CONTRACT_VERSION,
        'implementation_status': 'ACTIVE_LEGACY_MARKDOWN_DETECTOR',
        'purpose': 'legacy_candidate_discovery_with_fail_closed_layout_guards',
        'required_source_structure': ['RECTANGULAR_MARKDOWN_PIPE_TABLE'],
        'required_operands': ['one integer numerator', 'one explicit denominator', 'one displayed percentage'],
        'required_context': ['same-column header', 'known displayed precision', 'stable row and column alignment'],
        'allowed_ambiguity': ['none affecting row width, denominator, or footnote scope'],
        'rounding_policy': 'ROUND_HALF_UP to displayed precision; exact ties round away from zero',
        'units': ['count', 'percent'],
        'exclusions': ['ragged table', 'local denominator', 'footnoted operand or denominator', 'weighted or adjusted values'],
        'positive_result_establishes': 'The displayed value differs from exact count/denominator arithmetic under the parsed Markdown layout.',
        'positive_result_does_not_establish': 'That Markdown preserves the publisher layout or that a paper conclusion changes.',
        'unsupported_or_incomplete_reasons': ['RAGGED_TABLE', 'LOCAL_DENOMINATOR', 'FOOTNOTE_SCOPE_UNRESOLVED'],
    },
    {
        'detector_id': 'explicit_sample_flow_arithmetic',
        'version': CONTRACT_VERSION,
        'implementation_status': 'PURE_MODEL_NOT_SOURCE_MAPPED',
        'purpose': 'exact_arithmetic_candidate',
        'required_source_structure': ['EXPLICIT_FLOW_NODES_AND_OPERATION'],
        'required_operands': ['stage counts', 'explicit add/subtract relation'],
        'required_context': ['same population and time scope', 'disjoint exclusions', 'exhaustive relation'],
        'allowed_ambiguity': ['none affecting the operation'],
        'rounding_policy': 'exact integer arithmetic',
        'units': ['count'],
        'exclusions': ['overlapping exclusions', 'separate arms', 'unresolved attrition or missing-data subsets'],
        'positive_result_establishes': 'The explicitly stated flow operation does not balance over its declared nodes.',
        'positive_result_does_not_establish': 'That the paper is wrong or that a broader study conclusion changes.',
        'unsupported_or_incomplete_reasons': ['FLOW_RELATION_AMBIGUOUS', 'SCOPE_MISMATCH', 'OVERLAP_NOT_RULED_OUT'],
    },
    {
        'detector_id': 'explicit_exclusion_flow_locator',
        'version': CONTRACT_VERSION,
        'implementation_status': 'ACTIVE_AMBIGUITY_LOCATOR_NO_ARITHMETIC',
        'purpose': 'ambiguous_flow_discovery_only',
        'required_source_structure': ['PROSE_TEXT_RELIABLE'],
        'required_operands': ['starting count', 'one or more exclusion counts', 'included count'],
        'required_context': ['source anchors'],
        'allowed_ambiguity': ['overlap and scope may remain unresolved; output only FLOW_RELATION_AMBIGUOUS'],
        'rounding_policy': 'not_applicable',
        'units': ['count'],
        'exclusions': ['arithmetic candidate generation'],
        'positive_result_establishes': 'A sentence resembles a sample flow and needs a human scope review.',
        'positive_result_does_not_establish': 'That the exclusions are additive or that the counts are inconsistent.',
        'unsupported_or_incomplete_reasons': ['FLOW_RELATION_AMBIGUOUS', 'PROSE_TEXT_UNAVAILABLE'],
    },
    {
        'detector_id': 'two_by_two_effect_size_recomputation',
        'version': CONTRACT_VERSION,
        'implementation_status': 'PURE_OPERAND_CALCULATOR_NOT_SOURCE_MAPPED',
        'purpose': 'exact_arithmetic_candidate',
        'required_source_structure': ['EXPLICIT_UNADJUSTED_2X2_TABLE'],
        'required_operands': ['all four cell counts', 'reported RR or OR', 'display precision'],
        'required_context': ['common outcome and follow-up', 'unadjusted estimate', 'declared reference group'],
        'allowed_ambiguity': ['none; model-adjusted or clustered estimates are excluded'],
        'rounding_policy': 'ROUND_HALF_UP to displayed precision; exact ties round away from zero',
        'units': ['risk_ratio', 'odds_ratio', 'difference_in_proportions'],
        'exclusions': ['covariate adjustment', 'weighting', 'clustering', 'imputation', 'zero-cell correction not specified'],
        'positive_result_establishes': 'A recomputed crude 2x2 effect measure differs from the displayed value under the stated convention.',
        'positive_result_does_not_establish': 'That a fitted model result is incorrect or that causal interpretation is invalid.',
        'unsupported_or_incomplete_reasons': ['MODEL_ADJUSTED', 'OPERANDS_MISSING', 'FOLLOW_UP_MISMATCH', 'ZERO_CELL_POLICY_UNSPECIFIED'],
    },
    {
        'detector_id': 'cross_section_numeric_identity',
        'version': CONTRACT_VERSION,
        'implementation_status': 'PURE_ASSERTION_COMPARATOR_NOT_SOURCE_MAPPED',
        'purpose': 'strict_identity_contradiction_candidate',
        'required_source_structure': ['SOURCE_ANCHORED_NUMERIC_ASSERTIONS'],
        'required_operands': ['value', 'unit', 'statistic type'],
        'required_context': ['population', 'group', 'outcome', 'timepoint', 'adjustment status'],
        'allowed_ambiguity': ['incomplete identity produces POSSIBLE_SCOPE_DIFFERENCE only'],
        'rounding_policy': 'intersection of display-precision intervals',
        'units': ['assertion-specific'],
        'exclusions': ['semantically nearby but incompletely identified values'],
        'positive_result_establishes': 'Two source-anchored values with a complete matching identity differ beyond their display intervals.',
        'positive_result_does_not_establish': 'Which value is correct or whether any conclusion changes.',
        'unsupported_or_incomplete_reasons': ['IDENTITY_INCOMPLETE', 'SOURCE_ANCHOR_MISSING', 'UNIT_MISMATCH'],
    },
)


def contract_registry() -> list[dict[str, Any]]:
    """Return a JSON-safe copy of all current detector contracts."""
    return [
        {key: list(value) if isinstance(value, list) else value for key, value in contract.items()}
        for contract in _CONTRACTS
    ]


def eligibility(
    detector_id: str,
    status: str,
    source_format: str,
    reasons: list[str] | tuple[str, ...] = (),
    table_id: str | None = None,
    checked_operands: int = 0,
) -> dict[str, Any]:
    if detector_id not in {contract['detector_id'] for contract in _CONTRACTS}:
        raise ValueError(f'No detector contract registered for {detector_id}')
    result: dict[str, Any] = {
        'detector_id': detector_id,
        'contract_version': CONTRACT_VERSION,
        'status': status,
        'source_format': source_format,
        'reasons': list(dict.fromkeys(reasons)),
        'checked_operands': checked_operands,
    }
    if table_id is not None:
        result['table_id'] = table_id
    return result


def source_capabilities(source_format: str, extraction_status: str) -> dict[str, str]:
    """State the format boundary independently for prose and tables."""
    text_ok = extraction_status == 'TEXT_AVAILABLE'
    partial = extraction_status == 'PARTIAL_TEXT'
    if source_format == 'pdf':
        prose = 'PROSE_TEXT_RELIABLE' if text_ok else ('EXTRACTION_DEGRADED' if partial else 'EXTRACTION_FAILED')
        tables = 'TABLE_STRUCTURE_UNSUPPORTED'
    elif source_format == 'jats_xml':
        prose = 'SOURCE_NATIVE_PROSE_AVAILABLE' if text_ok else 'EXTRACTION_FAILED'
        tables = 'STRUCTURED_JATS_TABLES' if text_ok else 'TABLE_STRUCTURE_UNSUPPORTED'
    elif source_format in ('md', 'markdown'):
        prose = 'PROSE_TEXT_RELIABLE' if text_ok else 'EXTRACTION_FAILED'
        tables = 'MARKDOWN_TABLE_ADAPTER'
    else:
        prose = 'PROSE_TEXT_RELIABLE' if text_ok else 'EXTRACTION_FAILED'
        tables = 'TABLE_STRUCTURE_UNSUPPORTED'
    if extraction_status == 'NO_EXTRACTABLE_TEXT' and source_format == 'pdf':
        prose = 'IMAGE_ONLY'
    return {'prose': prose, 'tables': tables}
