"""Machine-readable applicability contracts for paper-screen detectors."""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = '1.1'

_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        'detector_id': 'explicit_count_marker_scan',
        'version': CONTRACT_VERSION,
        'implementation_status': 'ACTIVE_SOURCE_MAPPED',
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
        'implementation_status': 'ACTIVE_SOURCE_MAPPED',
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
        'implementation_status': 'ACTIVE_SOURCE_MAPPED',
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
        'implementation_status': 'IMPLEMENTED_HELPER',
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
        'implementation_status': 'EXPERIMENTAL',
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
        'implementation_status': 'IMPLEMENTED_HELPER',
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
        'implementation_status': 'IMPLEMENTED_HELPER',
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
    {
        'detector_id': 'jats_cell_ratio_percentage_recomputation',
        'version': CONTRACT_VERSION,
        'implementation_status': 'ACTIVE_SOURCE_MAPPED',
        'purpose': 'exact_same_cell_arithmetic_candidate',
        'required_source_structure': ['JATS_TBODY_CELL_WITH_EXPLICIT_N_OVER_N_PERCENT'],
        'required_operands': ['integer numerator', 'integer denominator', 'displayed percentage in the same cell'],
        'required_context': [
            'same-cell operands', 'source hash and table/cell element path',
            'known display precision', 'bounded explicit footnote semantics',
        ],
        'allowed_ambiguity': ['unrelated table grid errors do not alter the same-cell operands'],
        'rounding_policy': 'Decimal ratio rounded with ROUND_HALF_UP at the printed percentage precision',
        'units': ['count', 'count', 'percent'],
        'exclusions': [
            'PDF or Markdown', 'weighted or adjusted values', 'overlap or multiple response',
            'missing-data or changing-denominator cues', 'unknown footnote semantics',
            'cell or row-label references that alter scope',
        ],
        'positive_result_establishes': 'The explicit same-cell n/N ratio does not round to the displayed percentage under the stated rule.',
        'positive_result_does_not_establish': 'Which printed operand is wrong, whether the cell was faithfully captured, or whether any conclusion changes.',
        'unsupported_or_incomplete_reasons': [
            'CELL_SPAN_UNSUPPORTED', 'CELL_FOOTNOTE_OR_CROSS_REFERENCE_SCOPE',
            'CELL_FOOTNOTE_MARKER_UNRESOLVED', 'ROW_LABEL_SCOPE_UNRESOLVED',
            'UNSAFE_TABLE_SCOPE_CUE', 'FOOTNOTE_SCOPE_CUE', 'FOOTNOTE_SEMANTICS_UNRESOLVED',
            'OPERANDS_OUTSIDE_PROPORTION_DOMAIN', 'DIRECT_RATIO_CELL_LIMIT', 'RATIO_CANDIDATE_LIMIT',
        ],
    },
    {
        'detector_id': 'jats_sample_flow_arithmetic',
        'version': CONTRACT_VERSION,
        'implementation_status': 'ACTIVE_SOURCE_MAPPED',
        'purpose': 'explicit_flow_arithmetic_candidate',
        'required_source_structure': ['ONE_SOURCE_ANCHORED_JATS_PARAGRAPH'],
        'required_operands': ['starting count', 'two or more exclusion counts', 'included count'],
        'required_context': [
            'same population and unit', 'same group and timepoint',
            'explicit exclusion relation', 'source path and quoted operands',
        ],
        'allowed_ambiguity': ['unresolved overlap or scope produces FLOW_RELATION_AMBIGUOUS only'],
        'rounding_policy': 'exact integer subtraction',
        'units': ['participants', 'patients', 'records', 'reports', 'studies'],
        'exclusions': [
            'cross-paragraph joining', 'figure/image extraction', 'nested or overlapping categories',
            'unresolved arms, attrition, missing-data, or analysis-set transitions',
        ],
        'positive_result_establishes': 'A source-explicit disjoint/exhaustive or sequential flow relation fails exact integer balance.',
        'positive_result_does_not_establish': 'Which source count is wrong or whether a broader conclusion changes.',
        'unsupported_or_incomplete_reasons': [
            'FLOW_RELATION_AMBIGUOUS', 'FLOW_DISJOINTNESS_EXHAUSTIVENESS_OR_SEQUENCE_NOT_EXPLICIT',
            'FLOW_OPERAND_SCOPE_MISMATCH', 'FLOW_OPERAND_UNIT_MISMATCH',
            'FLOW_PARAGRAPH_EXCEEDS_LIMIT', 'FLOW_EXCLUSION_LIMIT',
        ],
    },
    {
        'detector_id': 'jats_sd_se_n_recomputation',
        'version': CONTRACT_VERSION,
        'implementation_status': 'EXPERIMENTAL',
        'purpose': 'bounded_summary_statistic_arithmetic_candidate',
        'required_source_structure': ['RELIABLE_JATS_TABLE_GRID', 'COMMON_N_SD_SE_HEADER_SCOPE'],
        'required_operands': ['one n', 'one SD', 'one SE in a single body row'],
        'required_context': [
            'same row, group, unit, and timepoint', 'explicit row label',
            'source anchors for all three operands', 'unweighted simple summary context',
        ],
        'allowed_ambiguity': ['method-specific SE may differ; keep candidate for human method review'],
        'rounding_policy': 'Decimal SD/sqrt(n) at 60-digit precision; ROUND_HALF_UP at printed SE precision',
        'units': ['sample_count', 'standard_deviation', 'standard_error'],
        'exclusions': [
            'SEM header treated as an unresolved near-match', 'weighted or adjusted estimates',
            'clustered or repeated measures', 'transformed scales', 'model-derived standard errors',
        ],
        'positive_result_establishes': 'The reported SE differs from SD/sqrt(n) at its displayed precision under the simple-summary assumption.',
        'positive_result_does_not_establish': 'That the paper uses this SE method, which operand is wrong, or whether any conclusion changes.',
        'unsupported_or_incomplete_reasons': [
            'TABLE_STRUCTURE_NOT_RELIABLE', 'TABLE_HAS_SCOPE_OR_TRANSFORM_AMBIGUITY',
            'SEM_HEADER_NOT_ACCEPTED_AS_SE', 'OPERAND_HEADER_PATH_MISSING',
            'OPERAND_SCOPE_OR_UNIT_HEADER_MISMATCH', 'SOURCE_ANCHOR_MISSING_OR_MISMATCHED',
        ],
    },
    {
        'detector_id': 'prisma_synthesis_flow',
        'version': CONTRACT_VERSION,
        'implementation_status': 'ACTIVE_SOURCE_MAPPED',
        'purpose': 'explicit_review_record_arithmetic_candidate',
        'required_source_structure': ['ONE_SOURCE_ANCHORED_JATS_PARAGRAPH'],
        'required_operands': ['records identified', 'duplicates removed', 'records screened'],
        'required_context': [
            'PRISMA, systematic-review, or literature-search context',
            'one labelled record population and explicit ordered stages',
            'source anchors for all three counts and the transition',
        ],
        'allowed_ambiguity': ['unparsed stages remain unsupported and separately source-located'],
        'rounding_policy': 'exact integer subtraction: identified minus duplicates removed',
        'units': ['records'],
        'exclusions': [
            'records/reports/studies are not interchangeable', 'multiple database counts',
            'full-text assessment and study-inclusion stages', 'qualitative/quantitative synthesis subsets',
            'computer vision', 'OCR', 'inferred missing transitions',
        ],
        'positive_result_establishes': 'The explicitly labelled identified-minus-duplicates relation differs from the reported screened-record count.',
        'positive_result_does_not_establish': 'That downstream study selection is correct, which count is wrong, or that a review conclusion changes.',
        'unsupported_or_incomplete_reasons': [
            'UNSUPPORTED_IMAGE_FLOW', 'PRISMA_SOURCE_OBJECT_LIMIT', 'PRISMA_PARAGRAPH_LIMIT',
            'PRISMA_SCOPE_OR_STAGE_AMBIGUOUS', 'PRISMA_LABELLED_TRANSITION_NOT_RECOGNIZED',
            'PRISMA_COUNT_OUT_OF_BOUNDS', 'PRISMA_DUPLICATES_EXCEED_IDENTIFIED_RECORDS',
            'PRISMA_FLOW_RELATION_NOT_IMPLEMENTED',
        ],
    },
    {
        'detector_id': 'jats_unadjusted_2x2_odds_ratio',
        'version': CONTRACT_VERSION,
        'implementation_status': 'ACTIVE_SOURCE_MAPPED',
        'purpose': 'crude_2x2_odds_ratio_arithmetic_candidate',
        'required_source_structure': ['ONE_RELIABLE_JATS_TABLE_BODY_ROW'],
        'required_operands': [
            'exposed events', 'exposed non-events', 'unexposed events',
            'unexposed non-events', 'reported odds ratio',
        ],
        'required_context': [
            'explicit event/non-event header polarity', 'exposed-versus-unexposed orientation',
            'one common outcome and explicit timepoint', 'explicit unadjusted odds-ratio header',
            'source anchors for all five operands',
        ],
        'allowed_ambiguity': ['all unresolved table scope or estimate semantics produce no arithmetic candidate'],
        'rounding_policy': 'exact Fraction cross-product; ROUND_HALF_UP at displayed odds-ratio precision',
        'units': ['count', 'odds_ratio'],
        'exclusions': [
            'adjusted/model-derived estimates', 'weighting, clustering, imputation, or standardization',
            'zero-cell correction without an explicit policy', 'multiple outcome rows',
            'confidence-interval text in place of an exact statistic',
        ],
        'positive_result_establishes': 'The reported unadjusted exposed-versus-unexposed odds ratio differs from the exact 2x2 cross-product at displayed precision.',
        'positive_result_does_not_establish': 'Causality, which printed count is wrong, or whether any conclusion changes.',
        'unsupported_or_incomplete_reasons': [
            'MODEL_ADJUSTED_WEIGHTED_OR_COMPLEX_CONTEXT', 'TABLE_STRUCTURE_NOT_RELIABLE',
            'EXACT_2X2_AND_ORIENTATION_HEADERS_REQUIRED', 'TIMEPOINT_UNSPECIFIED',
            'ZERO_CELL_POLICY_UNSPECIFIED', 'ONE_OUTCOME_ROW_REQUIRED',
            'SOURCE_ANCHOR_MISSING_OR_MISMATCHED',
        ],
    },
    {
        'detector_id': 'simple_rate_recomputation',
        'version': CONTRACT_VERSION,
        'implementation_status': 'UNSUPPORTED',
        'purpose': 'explicit_rate_arithmetic_candidate',
        'required_source_structure': ['SOURCE_MAPPED_EXPLICIT_RATE_OPERANDS'],
        'required_operands': ['event count', 'person-time exposure', 'scale', 'reported rate'],
        'required_context': ['same outcome and population', 'unadjusted rate', 'explicit exposure construction'],
        'allowed_ambiguity': ['hidden standardization or model-derived rates are unsupported'],
        'rounding_policy': 'not_implemented',
        'units': ['events', 'person_time', 'rate'],
        'exclusions': ['adjustment', 'weighting', 'standardization', 'regression-derived rate', 'incomplete exposure'],
        'positive_result_establishes': 'Not implemented; no rate result is generated.',
        'positive_result_does_not_establish': 'No paper rate is currently recomputed by this contract.',
        'unsupported_or_incomplete_reasons': ['EXPLICIT_RATE_OPERAND_MAPPING_NOT_IMPLEMENTED', 'HIDDEN_RATE_MODEL'],
    },
)


def contract_registry() -> list[dict[str, Any]]:
    """Return contracts with explicit source, scope, and output declarations."""
    source_formats = {
        'explicit_count_marker_scan': ['txt', 'md', 'markdown', 'pdf'],
        'table_percentage_recomputation': ['jats_xml'],
        'markdown_table_percentage_recomputation': ['md', 'markdown'],
        'explicit_sample_flow_arithmetic': [],
        'explicit_exclusion_flow_locator': ['txt', 'md', 'markdown', 'pdf'],
        'two_by_two_effect_size_recomputation': [],
        'cross_section_numeric_identity': [],
        'jats_cell_ratio_percentage_recomputation': ['jats_xml'],
        'jats_sample_flow_arithmetic': ['jats_xml'],
        'jats_sd_se_n_recomputation': ['jats_xml'],
        'prisma_synthesis_flow': ['jats_xml'],
        'jats_unadjusted_2x2_odds_ratio': ['jats_xml'],
        'simple_rate_recomputation': [],
    }
    document_objects = {
        'explicit_count_marker_scan': ['extracted prose with byte offsets'],
        'table_percentage_recomputation': ['JATS table', 'resolved header hierarchy', 'body cells'],
        'markdown_table_percentage_recomputation': ['Markdown pipe table', 'header row', 'body rows'],
        'explicit_sample_flow_arithmetic': ['explicit flow graph input'],
        'explicit_exclusion_flow_locator': ['extracted prose'],
        'two_by_two_effect_size_recomputation': ['explicit 2x2 operand model'],
        'cross_section_numeric_identity': ['source-anchored numeric assertions'],
        'jats_cell_ratio_percentage_recomputation': ['JATS table cell', 'bounded footnote model'],
        'jats_sample_flow_arithmetic': ['JATS paragraph'],
        'jats_sd_se_n_recomputation': ['reliable JATS table grid', 'n/SD/SE rows'],
        'prisma_synthesis_flow': ['JATS prose paragraph', 'source-located table/figure cues'],
        'jats_unadjusted_2x2_odds_ratio': ['JATS resolved table header paths', 'one body row', 'five source-anchored count/stat cells'],
        'simple_rate_recomputation': [],
    }
    output_kinds = {
        'explicit_count_marker_scan': ['count assertions', 'candidate count conflicts', 'possible scope differences'],
        'table_percentage_recomputation': ['table eligibility', 'percentage arithmetic candidates'],
        'markdown_table_percentage_recomputation': ['Markdown table eligibility', 'percentage candidates'],
        'explicit_sample_flow_arithmetic': ['flow arithmetic status'],
        'explicit_exclusion_flow_locator': ['ambiguous flow questions'],
        'two_by_two_effect_size_recomputation': ['effect size arithmetic result'],
        'cross_section_numeric_identity': ['identity-matched contradiction candidate'],
        'jats_cell_ratio_percentage_recomputation': ['per-table coverage', 'same-cell ratio candidates'],
        'jats_sample_flow_arithmetic': ['typed flow entities', 'balanced status', 'ambiguous flow', 'arithmetic candidates'],
        'jats_sd_se_n_recomputation': ['per-table coverage', 'SD/SE/n checks and candidates'],
        'prisma_synthesis_flow': ['source-mapped record relation', 'balanced status', 'arithmetic candidate', 'unsupported flow reason'],
        'jats_unadjusted_2x2_odds_ratio': ['per-table eligibility', 'source-mapped crude odds-ratio check', 'arithmetic candidate'],
        'simple_rate_recomputation': ['unsupported eligibility status'],
    }
    registry = []
    for contract in _CONTRACTS:
        result = {key: list(value) if isinstance(value, list) else value for key, value in contract.items()}
        result.update({
            'supported_source_formats': source_formats[contract['detector_id']],
            'required_document_objects': document_objects[contract['detector_id']],
            'scope_requirements': list(contract['required_context']),
            'unit_requirements': list(contract['units']),
            'statistical_assumptions': (
                ['SE equals SD divided by square root of n only for an unweighted simple summary under the stated row scope.']
                if contract['detector_id'] == 'jats_sd_se_n_recomputation' else []
            ),
            'ambiguity_conditions': list(contract['allowed_ambiguity']),
            'outputs': output_kinds[contract['detector_id']],
        })
        registry.append(result)
    return registry


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
