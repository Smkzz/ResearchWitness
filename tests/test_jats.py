"""JATS structure preservation, strict eligibility, and bounded arithmetic tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from researchwitness.jats import parse_jats
from researchwitness.paper_audit import run_paper_audit
from researchwitness.paper_contracts import contract_registry
from researchwitness.paper_document import NumericAssertion
from researchwitness.strict import Invalid
from researchwitness.table_arithmetic import check_structured_table_percentages

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/paper-audit.schema.json').read_text(encoding='utf-8'))


def _source(table: str, prose: str = '<p>At baseline, 20 participants were enrolled.</p>') -> bytes:
    return (
        '<article><front><article-meta><title-group><article-title>Example trial</article-title>'
        '</title-group><abstract><p>Objective.</p></abstract></article-meta></front><body>'
        '<sec><title>Results</title>' + prose + table + '</sec></body></article>'
    ).encode('utf-8')


def _simple_table(value: str = '2 (8.0%)', header: str = 'All (N=20)', extra: str = '') -> bytes:
    return _source(
        '<table-wrap id="T1"><label>Table 1</label><caption><title>Outcomes</title></caption>'
        '<table><thead><tr><th>Characteristic</th><th>' + header + '</th></tr></thead><tbody>'
        '<tr><th scope="row">Event</th><td>' + value + '</td></tr></tbody></table>'
        + extra + '</table-wrap>'
    )


def _run_jats(tmp_path: Path, source: bytes):
    source_path = tmp_path / 'paper.xml'
    source_path.write_bytes(source)
    output = tmp_path / 'screening'
    result = run_paper_audit(source_path, output)
    report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
    assert not list(Draft202012Validator(SCHEMA).iter_errors(report))
    return result, report, output


def test_jats_tables_use_source_linked_model_and_exact_percentage_contract(tmp_path):
    _, report, output = _run_jats(tmp_path, _simple_table())

    assert report['source_capabilities'] == {
        'prose': 'SOURCE_NATIVE_PROSE_AVAILABLE', 'tables': 'STRUCTURED_JATS_TABLES',
    }
    assert report['paper_structure']['layout_status'] == 'JATS_ELEMENT_PATHS_AND_TABLE_GRIDS'
    assert report['paper_structure']['document_model']['table_count'] == 1
    assert report['coverage']['paper']['tables']['discovered'] == 1
    coverage = {item['detector_id']: item for item in report['coverage']['detectors']}
    assert coverage['table_percentage_recomputation']['scope'] == 'table'
    assert coverage['table_percentage_recomputation']['object_counts']['potential'] == 1
    assert coverage['jats_cell_ratio_percentage_recomputation']['tables'][0]['parser_status'] == 'STRUCTURE_RELIABLE'
    assert (output / 'paper-document.json').is_file()
    model = json.loads((output / 'paper-document.json').read_text(encoding='utf-8'))
    assert model['source_sha256'] == report['source']['sha256']
    assert model['tables'][0]['table_id'] == 'T1'
    assert model['tables'][0]['structure_status'] == 'STRUCTURE_RELIABLE'
    finding = report['candidate_anomalies'][0]
    assert finding['type'] == 'STRUCTURED_TABLE_PERCENTAGE_ARITHMETIC_MISMATCH'
    assert (finding['numerator_exact'], finding['denominator_exact']) == ('2', '20')
    assert finding['recomputed_percent'] == '10'
    assert finding['rounding_tolerance_percentage_points'] == '0.05'
    assert len(finding['source_anchors']) == 3
    assert all(anchor['source_sha256'] == report['source']['sha256'] for anchor in finding['source_anchors'])
    assert '/table-wrap[1]/table[1]/tbody[1]/tr[1]/td[1]' in finding['source_anchors'][-1]['element_path']
    assert report['paper_error_established'] is False
    html = (output / 'report.html').read_text(encoding='utf-8')
    assert 'What this source could support' in html
    assert 'Capability coverage' in html and '1/1 tables checked' in html
    assert "ResearchWitness has not determined whether this affects the paper's conclusions." in html


def test_direct_cell_ratio_is_reported_with_exact_jats_anchor(tmp_path):
    source = _source(
        '<table-wrap id="T-ratio"><label>Table 2</label><caption><title>Disposition</title></caption>'
        '<table><thead><tr><th>Group</th><th>Value</th></tr></thead><tbody>'
        '<tr><th scope="row">Transferred</th><td>11/233 (1.8%)</td></tr>'
        '</tbody></table></table-wrap>'
    )
    _, report, _ = _run_jats(tmp_path, source)

    candidates = [item for item in report['candidate_anomalies']
                  if item['type'] == 'JATS_CELL_RATIO_PERCENTAGE_MISMATCH']
    assert len(candidates) == 1
    candidate = candidates[0]
    assert (candidate['numerator_exact'], candidate['denominator_exact']) == ('11', '233')
    assert candidate['recomputed_at_display_precision'] == '4.7'
    assert candidate['source_anchors'][0]['element_path'].endswith('/tbody[1]/tr[1]/td[1]')
    ratio_coverage = next(item for item in report['coverage']['detectors']
                          if item['detector_id'] == 'jats_cell_ratio_percentage_recomputation')
    assert ratio_coverage['tables'][0]['counts']['operands']['checked'] == 1


def test_source_mapped_flow_candidate_reaches_report_and_coverage(tmp_path):
    prose = (
        'Of the 100 participants in cohort Alpha, we excluded 10 with condition A and '
        '5 with condition B. The exclusion categories were mutually exclusive and exhaustive, '
        'and all remaining participants were included. Finally, 80 participants in cohort Alpha '
        'were included.'
    )
    _, report, _ = _run_jats(tmp_path, _source('', '<p>' + prose + '</p>'))

    flow_finding = next(item for item in report['candidate_anomalies']
                        if item['type'] == 'JATS_SAMPLE_FLOW_ARITHMETIC_MISMATCH')
    assert flow_finding['expected_included_exact'] == '85'
    flow_screen = report['arithmetic_screens']['source_mapped_sample_flow']
    assert flow_screen['status'] == 'ELIGIBLE'
    assert flow_screen['checked_objects'] == 1
    flow_coverage = next(item for item in report['coverage']['detectors']
                         if item['detector_id'] == 'jats_sample_flow_arithmetic')
    assert flow_coverage['object_counts']['checked'] == 1
    assert flow_coverage['object_counts']['candidates'] == 1


def test_prisma_figure_is_explicitly_unsupported_without_image_or_ocr(tmp_path):
    source = (
        '<article><front><article-meta><title-group><article-title>Review</article-title>'
        '</title-group></article-meta></front><body><sec><fig id="flow1"><label>Figure 1</label>'
        '<caption><title>PRISMA flow diagram of study selection</title></caption>'
        '<graphic href="flow.png"/></fig></sec></body></article>'
    ).encode('utf-8')
    _, report, _ = _run_jats(tmp_path, source)

    screen = report['arithmetic_screens']['prisma_synthesis_flow']
    assert screen['status'] == 'UNSUPPORTED'
    assert screen['limitations'] == ['UNSUPPORTED_IMAGE_FLOW']
    assert screen['image_contents_read'] is False
    assert screen['ocr_performed'] is False
    coverage = next(item for item in report['coverage']['detectors']
                    if item['detector_id'] == 'prisma_synthesis_flow')
    assert coverage['object_counts']['potential'] == 1
    assert coverage['object_counts']['checked'] == 0


def test_explicit_prisma_count_candidate_reaches_report_and_coverage(tmp_path):
    source = _source(
        '',
        '<p>PRISMA systematic review: records identified: 100; duplicates removed: 20; '
        'records screened: 79.</p>',
    )
    _, report, _ = _run_jats(tmp_path, source)

    finding = next(item for item in report['candidate_anomalies']
                   if item['type'] == 'JATS_PRISMA_FLOW_ARITHMETIC_MISMATCH')
    assert finding['expected_screened_exact'] == '80'
    assert len(finding['source_anchors']) == 4
    screen = report['arithmetic_screens']['prisma_synthesis_flow']
    assert screen['status'] == 'ELIGIBLE'
    assert screen['relations'][0]['status'] == 'PRISMA_FLOW_ARITHMETIC_CANDIDATE'
    coverage = next(item for item in report['coverage']['detectors']
                    if item['detector_id'] == 'prisma_synthesis_flow')
    assert coverage['object_counts']['checked'] == 1
    assert coverage['object_counts']['candidates'] == 1


def test_unadjusted_two_by_two_candidate_reaches_report_and_granular_coverage(tmp_path):
    source = _source(
        '<table-wrap id="T-2x2"><label>Table 4</label>'
        '<caption><title>2x2 mortality at 30 days</title></caption><table><thead><tr>'
        '<th>Outcome</th><th>Exposed event</th><th>Exposed non-event</th>'
        '<th>Unexposed event</th><th>Unexposed non-event</th>'
        '<th>Unadjusted odds ratio (exposed vs unexposed)</th></tr></thead><tbody>'
        '<tr><th scope="row">30-day mortality</th><td>12</td><td>88</td><td>6</td>'
        '<td>94</td><td>2.20</td></tr></tbody></table></table-wrap>'
    )
    _, report, _ = _run_jats(tmp_path, source)

    finding = next(item for item in report['candidate_anomalies']
                   if item['type'] == 'JATS_UNADJUSTED_2X2_ODDS_RATIO_MISMATCH')
    assert finding['recomputed_at_display_precision'] == '2.14'
    assert len(finding['source_anchors']) == 5
    screen = report['arithmetic_screens']['jats_unadjusted_2x2_odds_ratio']
    assert screen['tables'][0]['status'] == 'ELIGIBLE'
    assert screen['tables'][0]['checked_objects'] == 1
    coverage = next(item for item in report['coverage']['detectors']
                    if item['detector_id'] == 'jats_unadjusted_2x2_odds_ratio')
    assert coverage['object_counts']['eligible'] == 1
    assert coverage['operand_counts']['checked'] == 1


def test_structured_percentage_candidate_limit_is_bounded_and_incomplete():
    rows = ''.join(
        f'<tr><th scope="row">Outcome {index}</th><td>1 (0%)</td></tr>'
        for index in range(257)
    )
    source = _source(
        '<table-wrap id="T-limit"><label>Table 1</label><table><thead><tr>'
        '<th>Outcome</th><th>n (%) N=100</th></tr></thead><tbody>' + rows
        + '</tbody></table></table-wrap>'
    )
    report = check_structured_table_percentages(parse_jats(source))

    assert len(report['findings']) == 256
    assert report['scan_complete'] is False
    assert report['tables'][0]['status'] == 'INCOMPLETE'
    assert 'STRUCTURED_TABLE_CANDIDATE_LIMIT' in report['tables'][0]['reasons']


def test_figure_caption_is_source_mapped_without_reading_graphic_content():
    source = (
        '<article><body><fig id="f1"><label>Figure 1</label>'
        '<caption><title>PRISMA flow diagram of study selection</title></caption>'
        '<graphic href="flow.png"/></fig></body></article>'
    ).encode('utf-8')
    document = parse_jats(source, 'source.xml')

    assert len(document.figures) == 1
    figure = document.figures[0]
    assert figure.label == 'Figure 1'
    assert figure.caption == 'PRISMA flow diagram of study selection'
    assert figure.graphic_present is True
    assert figure.source_anchor.source_sha256 == document.source_sha256
    assert figure.source_anchor.element_path.endswith('/fig[1]')
    assert figure.source_anchor.quote == figure.caption


def test_grouped_two_row_headers_keep_all_and_no_columns_aligned():
    source = _source(
        '<table-wrap id="T2" position="float" specific-use="primary"><label>Table 2</label>'
        '<caption><title>Grouped outcomes</title></caption>'
        '<table><thead><tr><th rowspan="2">Characteristic</th><th colspan="2">All</th>'
        '<th colspan="2">No</th></tr><tr><th>n=20</th><th>n=10</th><th>n=20</th><th>n=10</th></tr></thead>'
        '<tbody><tr><th scope="row">Event</th><td>2 (10.0%)</td><td>1 (10.0%)</td>'
        '<td>4 (20.0%)</td><td>1 (10.0%)</td></tr></tbody></table></table-wrap>'
    )
    document = parse_jats(source)
    table = document.tables[0]
    assert table.structure_status == 'STRUCTURE_RELIABLE'
    assert table.label == 'Table 2'
    assert table.wrap_metadata == (('id', 'T2'), ('position', 'float'), ('specific-use', 'primary'))
    assert len(table.spans) == 3
    assert table.columns[1].header_hierarchy == ('All', 'n=20')
    assert table.columns[3].header_hierarchy == ('No', 'n=20')
    cells = table.rows[-1].cells
    assert cells[1].effective_headers == ('All', 'n=20')
    assert cells[3].effective_headers == ('No', 'n=20')
    assert document.numeric_assertions[0].denominator == '20'
    from researchwitness.table_arithmetic import check_structured_table_percentages

    screen = check_structured_table_percentages(document)
    assert screen['findings'] == []
    assert screen['tables'][0]['status'] == 'ELIGIBLE'


def test_nonstandard_but_explicit_row_stub_header_preserves_row_identity(tmp_path):
    source = _source(
        '<table-wrap id="repigmentation"><table><thead><tr><th>Repigmentation</th>'
        '<th>Group 1 (n=30)</th><th>Group 2 (n=30)</th></tr></thead><tbody>'
        '<tr><td>At least 75%</td><td>23 (73.3%)</td><td>23 (70%)</td></tr>'
        '</tbody></table></table-wrap>'
    )
    _, report, _ = _run_jats(tmp_path, source)
    assert len(report['candidate_anomalies']) == 2
    assert all(item['row_identity'] == 'At least 75%' for item in report['candidate_anomalies'])


@pytest.mark.parametrize(
    ('reported', 'expected_candidates'),
    [('33%', 0), ('33.3%', 0), ('33.33%', 0), ('33.2%', 1)],
)
def test_display_precision_controls_rounding_tolerance(tmp_path, reported, expected_candidates):
    source = _simple_table(value=f'1 ({reported})', header='All (N=3)')
    _, report, _ = _run_jats(tmp_path, source)
    assert len(report['candidate_anomalies']) == expected_candidates
    result = report['arithmetic_screens']['structured_table_percentages']
    assert result['checked_cells'] == 1


@pytest.mark.parametrize(('reported', 'expected_candidates'), [('12%', 1), ('13%', 0)])
def test_exact_half_unit_uses_round_half_up_policy(tmp_path, reported, expected_candidates):
    source = _simple_table(value=f'1 ({reported})', header='All (N=8)')
    _, report, _ = _run_jats(tmp_path, source)
    assert len(report['candidate_anomalies']) == expected_candidates
    if expected_candidates:
        assert report['candidate_anomalies'][0]['recomputed_at_display_precision'] == '13'


def test_local_row_denominator_is_not_replaced_by_the_column_denominator():
    source = _source(
        '<table-wrap id="T3"><table><thead><tr><th>Outcome</th><th>All (N=20)</th></tr></thead>'
        '<tbody><tr><th scope="row">Event (n=10)</th><td>2 (10.0%)</td></tr></tbody></table></table-wrap>'
    )
    document = parse_jats(source)
    from researchwitness.table_arithmetic import check_structured_table_percentages

    result = check_structured_table_percentages(document)
    assert result['findings'] == []
    assert result['tables'][0]['status'] == 'INCOMPLETE'
    assert 'LOCAL_ROW_DENOMINATOR' in result['tables'][0]['reasons']


def test_explicit_category_block_with_smaller_complete_case_denominator_is_incomplete():
    document = parse_jats(_source(
        '<table-wrap id="available-cases"><caption><title>Patient characteristics</title></caption>'
        '<table><thead><tr><th>Characteristic</th><th>Responded (n=20)</th></tr></thead><tbody>'
        '<tr><th scope="row">Charlson index</th><td></td></tr>'
        '<tr><th scope="row">0</th><td>7 (70%)</td></tr>'
        '<tr><th scope="row">1</th><td>2 (20%)</td></tr>'
        '<tr><th scope="row">&gt;1</th><td>1 (10%)</td></tr>'
        '</tbody></table></table-wrap>'
    ))
    from researchwitness.table_arithmetic import check_structured_table_percentages

    result = check_structured_table_percentages(document)
    assert result['findings'] == []
    assert result['tables'][0]['status'] == 'INCOMPLETE'
    assert 'LOCAL_GROUP_DENOMINATOR_INDICATED' in result['tables'][0]['reasons']


def test_rates_per_person_time_remain_outside_count_percentage_contract(tmp_path):
    source = _source(
        '<table-wrap id="rates"><table><thead><tr><th>Outcome</th><th>Exposure</th></tr></thead>'
        '<tbody><tr><th scope="row">Incidence rate</th><td>14.5 per 1000 person-years</td></tr>'
        '</tbody></table></table-wrap>'
    )
    _, report, _ = _run_jats(tmp_path, source)
    assert report['candidate_anomalies'] == []
    assert report['detector_eligibility'][1]['status'] == 'NOT_APPLICABLE'


def test_footnoted_header_denominator_is_preserved_but_not_used(tmp_path):
    source = _source(
        '<table-wrap id="T4"><table><thead><tr><th>Outcome</th><th>All (N=20)'
        '<xref ref-type="table-fn" rid="fn1">*</xref></th></tr></thead><tbody>'
        '<tr><th scope="row">Event</th><td>2 (8.0%)</td></tr></tbody></table>'
        '<table-wrap-foot><fn id="fn1"><label>*</label><p>p &lt; 0.05.</p></fn></table-wrap-foot>'
        '</table-wrap>'
    )
    _, report, _ = _run_jats(tmp_path, source)
    assert report['candidate_anomalies'] == []
    model_path = tmp_path / 'screening' / 'paper-document.json'
    model = json.loads(model_path.read_text(encoding='utf-8'))
    assert model['tables'][0]['footnotes'][0]['identifier'] == 'fn1'
    assert model['tables'][0]['rows'][0]['cells'][1]['footnote_references'] == ['fn1']
    assert report['detector_eligibility'][1]['status'] == 'INCOMPLETE'


def test_footnoted_row_label_scope_suppresses_global_denominator(tmp_path):
    source = _source(
        '<table-wrap id="T4-row-note"><table><thead><tr><th>Characteristic</th><th>All (N=1854)</th></tr></thead>'
        '<tbody><tr><th scope="row">Male<xref ref-type="table-fn" rid="sex-note">a</xref></th>'
        '<td>1083 (58.5%)</td></tr></tbody></table><table-wrap-foot>'
        '<fn id="sex-note"><label>a</label><p>Sex data were unknown for 3 cases.</p></fn>'
        '</table-wrap-foot></table-wrap>'
    )
    _, report, _ = _run_jats(tmp_path, source)
    assert report['candidate_anomalies'] == []
    result = report['arithmetic_screens']['structured_table_percentages']['tables'][0]
    assert result['status'] == 'INCOMPLETE'
    assert 'FOOTNOTED_OR_SCOPED_ROW_LABEL' in result['reasons']


@pytest.mark.parametrize('cue', ['weighted estimate', 'adjusted percentage', 'multiple responses allowed', 'missing data excluded'])
def test_weighted_adjusted_overlap_and_missingness_cues_suppress_candidates(tmp_path, cue):
    source = _simple_table(value='2 (8.0%)', header=f'All (N=20), {cue}')
    _, report, _ = _run_jats(tmp_path, source)
    assert report['candidate_anomalies'] == []
    table_result = next(item for item in report['arithmetic_screens']['structured_table_percentages']['tables'])
    assert table_result['status'] == 'UNSUPPORTED'


@pytest.mark.parametrize(('denominator', 'reported', 'row_count'), [(3, '33.3%', 3), (7, '14.3%', 7)])
def test_valid_display_rounding_is_not_rejected_for_99_9_or_100_1_sums(
    tmp_path, denominator, reported, row_count,
):
    rows = ''.join(
        f'<tr><th scope="row">Category {index + 1}</th><td>1 ({reported})</td></tr>'
        for index in range(row_count)
    )
    source = _source(
        '<table-wrap id="rounded-sum"><table><thead><tr><th>Outcome</th>'
        f'<th>All (N={denominator})</th></tr></thead><tbody>{rows}</tbody></table></table-wrap>'
    )
    _, report, _ = _run_jats(tmp_path, source)
    assert report['candidate_anomalies'] == []
    assert report['arithmetic_screens']['structured_table_percentages']['checked_cells'] == row_count


def test_ragged_jats_table_reports_incomplete_coverage_and_skips_all_cells(tmp_path):
    source = _source(
        '<table-wrap id="T5"><table><thead><tr><th>Outcome</th><th>All (N=20)</th></tr></thead><tbody>'
        '<tr><th scope="row">Event</th><td>2 (8.0%)</td></tr>'
        '<tr><th scope="row">Other</th></tr></tbody></table></table-wrap>'
    )
    _, report, _ = _run_jats(tmp_path, source)
    assert report['candidate_anomalies'] == []
    table = json.loads((tmp_path / 'screening' / 'paper-document.json').read_text())['tables'][0]
    assert table['structure_status'] == 'TABLE_STRUCTURE_UNSUPPORTED'
    assert any('ragged' in reason for reason in table['limitations'])
    assert report['arithmetic_screens']['structured_table_percentages']['tables'][0]['status'] == 'INCOMPLETE'
    assert 'Table checking incomplete' in (tmp_path / 'screening' / 'report.html').read_text()


def test_flow_shape_is_a_scope_question_not_a_subtraction_candidate(tmp_path):
    prose = ('Of the 100 study participants, we excluded 10 with condition A and 5 with condition B. '
             'Finally, 80 participants were included.\n')
    source_path = tmp_path / 'paper.txt'
    source_path.write_text(prose, encoding='utf-8')
    output = tmp_path / 'screening'
    run_paper_audit(source_path, output)
    report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
    assert not list(Draft202012Validator(SCHEMA).iter_errors(report))
    assert report['candidate_anomalies'] == []
    assert len(report['arithmetic_screens']['sample_exclusion_flow']['ambiguous_relations']) == 1
    locator = next(item for item in report['detector_eligibility']
                   if item['detector_id'] == 'explicit_exclusion_flow_locator')
    assert locator['status'] == 'INCOMPLETE'


def test_strict_identity_key_requires_every_scope_dimension():
    source = parse_jats(_simple_table())
    assertion = source.numeric_assertions[0]
    assert assertion.identity_key is None
    assert NumericAssertion(
        value='10', unit='percent', statistic_type='proportion_percent', numerator='2', denominator='20',
        population='participants', group='event', outcome='event', timepoint='baseline',
        adjustment_status='unadjusted', source_anchor=assertion.source_anchor,
        structural_provenance=assertion.structural_provenance,
    ).identity_key is not None


def test_contract_registry_covers_every_reported_detector():
    registry = {item['detector_id']: item for item in contract_registry()}
    assert len(registry) == 13
    assert registry['table_percentage_recomputation']['implementation_status'] == 'ACTIVE_SOURCE_MAPPED'
    assert registry['explicit_sample_flow_arithmetic']['implementation_status'] == 'IMPLEMENTED_HELPER'
    assert registry['two_by_two_effect_size_recomputation']['implementation_status'] == 'IMPLEMENTED_HELPER'
    assert registry['jats_sample_flow_arithmetic']['implementation_status'] == 'ACTIVE_SOURCE_MAPPED'
    assert registry['prisma_synthesis_flow']['implementation_status'] == 'ACTIVE_SOURCE_MAPPED'
    assert registry['jats_unadjusted_2x2_odds_ratio']['implementation_status'] == 'ACTIVE_SOURCE_MAPPED'
    assert registry['jats_sd_se_n_recomputation']['implementation_status'] == 'EXPERIMENTAL'
    assert 'PDF table layout' in registry[
        'table_percentage_recomputation'
    ]['exclusions']


def test_jats_rejects_dtd_entity_and_malformed_inputs():
    with pytest.raises(Invalid, match='DTD and entity'):
        parse_jats(b'<!DOCTYPE article [<!ENTITY x "unsafe">]><article>&x;</article>')
    with pytest.raises(Invalid, match='malformed'):
        parse_jats(b'<article><body></article>')


def test_jats_ignores_external_dtd_without_fetch_and_decodes_known_entities():
    source = b'''<!DOCTYPE article PUBLIC "-//NLM//DTD JATS 1.4//EN" "https://invalid.example/jats.dtd">
    <article><body><sec><title>Results</title><p>Alpha &alpha; &amp; beta</p></sec></body></article>'''
    document = parse_jats(source)
    assert document.paragraphs[0].text == 'Alpha α & beta'


def test_jats_entity_preparation_leaves_comments_and_cdata_untouched():
    source = b'''<!-- literal <!DOCTYPE article [not markup]> &unknownName; -->
    <article><body><sec><title>Results</title>
    <p>Before <![CDATA[<tag>&publisherSymbol;]]> after</p>
    </sec></body></article>'''
    document = parse_jats(source)
    assert document.paragraphs[0].text == 'Before <tag>&publisherSymbol; after'


def test_jats_rejects_unknown_entities_even_with_external_doctype():
    source = b'''<!DOCTYPE article SYSTEM "https://invalid.example/jats.dtd">
    <article><body><p>&customPublisherSymbol;</p></body></article>'''
    with pytest.raises(Invalid, match='unknown or unsupported named entity'):
        parse_jats(source)


def test_malformed_table_span_is_retained_as_unsupported_not_used_for_arithmetic():
    document = parse_jats(_source(
        '<table-wrap id="bad-span"><table><thead><tr><th>Outcome</th><th>All (N=20)</th></tr></thead>'
        '<tbody><tr><th scope="row">Event</th><td colspan="0">2 (8.0%)</td></tr></tbody>'
        '</table></table-wrap>'
    ))
    from researchwitness.table_arithmetic import check_structured_table_percentages

    assert document.tables[0].structure_status == 'TABLE_STRUCTURE_UNSUPPORTED'
    assert check_structured_table_percentages(document)['findings'] == []


def test_jats_depth_and_source_size_limits_fail_closed(monkeypatch):
    import researchwitness.jats as jats

    monkeypatch.setattr(jats, 'MAX_JATS_DEPTH', 2)
    with pytest.raises(Invalid, match='nesting limit'):
        parse_jats(b'<article><body><sec/></body></article>')
    monkeypatch.setattr(jats, 'MAX_JATS_BYTES', 4)
    with pytest.raises(Invalid, match='32 MiB limit'):
        parse_jats(b'<article/>')


def test_malformed_jats_is_a_bounded_report_with_no_detector_candidates(tmp_path):
    _, report, _ = _run_jats(tmp_path, b'<article><body></article>')
    assert report['extraction']['status'] == 'MALFORMED_OR_UNSUPPORTED'
    assert report['paper_structure']['layout_status'] == 'JATS_STRUCTURE_UNAVAILABLE'
    assert report['paper_structure']['document_model'] is None
    assert report['candidate_anomalies'] == []
    assert report['source_capabilities']['tables'] == 'TABLE_STRUCTURE_UNSUPPORTED'


def test_jats_table_scope_xref_and_table_identity_are_retained():
    document = parse_jats(_source(
        '<table-wrap id="named-table"><label>Table 7</label><caption><title>By follow-up</title>'
        '<p>Primary outcome</p></caption><table><thead><tr><th>Outcome</th><th>Week 12 (N=20)'
        '</th></tr></thead><tbody><tr><th scope="row">Responders</th><td>2 (8.0%)'
        '<xref ref-type="table-fn" rid="f2">a</xref></td></tr></tbody></table>'
        '<table-wrap-foot><fn id="f2"><label>a</label><p>Data from the available cases only.</p></fn>'
        '</table-wrap-foot></table-wrap>'
    ))
    table = document.tables[0]
    assert table.table_id == 'named-table'
    assert table.label == 'Table 7'
    assert 'By follow-up' in table.caption
    cell = table.rows[-1].cells[-1]
    assert cell.footnote_references == ('f2',)
    assert cell.cross_references == ()
    assert cell.effective_headers == ('Week 12 (N=20)',)
    assert document.numeric_assertions == ()


def test_table_xref_resolves_article_level_footnote():
    source = b'''<article><body><sec><title>Results</title>
    <table-wrap id="T6"><table><thead><tr><th>Outcome</th><th>All (N=20)</th></tr></thead>
    <tbody><tr><th scope="row">Event</th><td>2 (8.0%)<xref ref-type="fn" rid="global-fn">a</xref>
    </td></tr></tbody></table></table-wrap></sec></body>
    <back><fn-group><fn id="global-fn"><label>a</label><p>Available cases only.</p></fn>
    </fn-group></back></article>'''
    document = parse_jats(source)
    table = document.tables[0]
    assert table.footnotes[0].identifier == 'global-fn'
    assert table.footnotes[0].text == 'a Available cases only.'
    assert table.rows[-1].cells[-1].footnote_references == ('global-fn',)
