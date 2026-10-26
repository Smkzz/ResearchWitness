"""Adversarial tests for source-mapped JATS SD/SE/n arithmetic."""
from __future__ import annotations

import pytest
from researchwitness import jats_product
from decimal import DefaultContext, Inexact, InvalidOperation
from pathlib import Path
import json
import subprocess
import sys


from researchwitness.jats_table_projection import project_jats_tables
from researchwitness.paper_statistics_source import check_jats_sd_se_n_tables


def _document(
    *,
    headers: tuple[str, ...] = ('n', 'SD', 'SE'),
    values: tuple[str, ...] = ('4', '6', '3'),
    title: str = 'Invented independent observations; SE = SD/sqrt(n)',
    grouped_headers: tuple[str, ...] | None = None,
    row_label: str = 'Score',
    extra: str = '',
):
    assert len(headers) == len(values)
    header_rows = ''
    if grouped_headers is not None:
        assert len(grouped_headers) == len(headers)
        first = ''.join(f'<th>{item}</th>' for item in grouped_headers)
        second = ''.join(f'<th>{item}</th>' for item in headers)
        header_rows = f'<tr><th>Measure</th>{first}</tr><tr><th></th>{second}</tr>'
    else:
        header_rows = '<tr><th>Measure</th>' + ''.join(f'<th>{item}</th>' for item in headers) + '</tr>'
    source_cells = ''.join(f'<td>{value}</td>' for value in values)
    source = (
        '<article><front><article-meta><title-group><article-title>SD SE example</article-title>'
        '</title-group></article-meta></front><body><sec><title>Results</title>'
        f'<table-wrap id="T1"><label>Table 1</label><caption><title>{title}</title></caption>'
        f'<table><thead>{header_rows}</thead><tbody><tr><th scope="row">{row_label}</th>'
        f'{source_cells}</tr></tbody></table>{extra}</table-wrap>'
        '</sec></body></article>'
    ).encode('utf-8')
    return project_jats_tables(source)


def _table_result(document):
    return check_jats_sd_se_n_tables(document)['tables'][0]


def test_valid_row_returns_consistent_source_mapped_check_for_all_three_operands():
    document = _document(values=('4', '6', '3'))
    report = check_jats_sd_se_n_tables(document)

    table = report['tables'][0]
    assert table['applicability'] == 'APPLICABLE'
    assert table['eligibility'] == 'ELIGIBLE'
    assert table['checked_rows'] == 1
    assert table['candidate_count'] == 0
    assert table['skip_reasons'] == []
    check = table['checks'][0]
    assert check['status'] == 'CONSISTENT_WITH_ROUNDING'
    assert check['recomputed_se_at_display_precision'] == '3'
    assert [(item['role'], item['source_anchor']['quote']) for item in check['source_anchors']] == [
        ('n', '4'), ('sd', '6'), ('se', '3'),
    ]
    assert all(item['source_anchor']['source_sha256'] == document.source_sha256
               for item in check['source_anchors'])
    assert all(item['source_anchor']['source_file'] == 'source.xml'
               for item in check['source_anchors'])
    assert report['findings'] == []


def test_mismatch_is_candidate_and_preserves_three_operand_anchors():
    report = check_jats_sd_se_n_tables(_document(values=('4', '6.0', '2.9')))

    assert len(report['findings']) == 1
    candidate = report['findings'][0]
    assert candidate['status'] == 'ARITHMETIC_CANDIDATE'
    assert candidate['type'] == 'JATS_SD_SE_N_ARITHMETIC_MISMATCH'
    assert candidate['recomputed_se_at_display_precision'] == '3.0'
    assert candidate['n_exact'] == '4'
    assert candidate['sd_exact'] == '6.0'
    assert candidate['reported_se'] == '2.9'
    assert {item['role'] for item in candidate['source_anchors']} == {'n', 'sd', 'se'}
    assert len({item['source_anchor']['element_path'] for item in candidate['source_anchors']}) == 3


def test_reported_precision_controls_se_rounding():
    report = check_jats_sd_se_n_tables(_document(values=('3', '1', '0.58')))
    check = report['tables'][0]['checks'][0]
    assert check['status'] == 'CONSISTENT_WITH_ROUNDING'
    assert check['recomputed_se_at_display_precision'] == '0.58'
    assert check['display_precision'] == 2


def test_sem_is_not_silently_treated_as_se_or_as_an_sd_label():
    table = _table_result(_document(headers=('n', 'SD', 'SEM'), values=('4', '6', '3')))

    assert table['applicability'] == 'APPLICABLE'
    assert table['eligibility'] == 'INCOMPLETE'
    assert table['checked_rows'] == 0
    assert table['candidate_count'] == 0
    assert table['skip_reasons'] == [{
        'reason': 'SEM_HEADER_NOT_ACCEPTED_AS_SE', 'row_index': 0,
    }]


@pytest.mark.parametrize('title', [
    'Weighted descriptive statistics',
    'Adjusted mean and standard error',
    'Repeated-measures summary',
    'Log-transformed values',
])
def test_weighted_adjusted_repeated_measure_and_transform_context_is_unsupported(title):
    table = _table_result(_document(title=title))

    assert table['applicability'] == 'APPLICABLE'
    assert table['eligibility'] == 'UNSUPPORTED'
    assert table['checked_rows'] == 0
    assert table['candidate_count'] == 0
    assert table['skip_reasons'] == [{'reason': 'TABLE_HAS_SCOPE_OR_TRANSFORM_AMBIGUITY'}]


def test_cell_footnote_or_cross_reference_makes_row_incomplete():
    extra = (
        '<table-wrap-foot><fn id="fn1"><label>a</label><p>Values are weighted.</p></fn>'
        '</table-wrap-foot>'
    )
    source = (
        '<article><body><table-wrap id="T1"><table><thead><tr><th>Measure</th>'
        '<th>n</th><th>SD</th><th>SE</th></tr></thead><tbody><tr><th scope="row">Score</th>'
        '<td>4</td><td>6</td><td>3<xref ref-type="table-fn" rid="fn1">a</xref></td>'
        '</tr></tbody></table>' + extra + '</table-wrap></body></article>'
    ).encode('utf-8')
    table = _table_result(project_jats_tables(source))

    assert table['eligibility'] == 'UNSUPPORTED'
    assert table['skip_reasons'] == [{'reason': 'TABLE_HAS_SCOPE_OR_TRANSFORM_AMBIGUITY'}]
    assert table['candidate_count'] == 0


def test_unresolved_operand_footnote_suppresses_check_even_without_unsafe_note_text():
    source = (
        '<article><body><table-wrap id="T1"><table><thead><tr><th>Measure</th>'
        '<th>n</th><th>SD</th><th>SE</th></tr></thead><tbody><tr><th scope="row">Score</th>'
        '<td>4<xref ref-type="table-fn" rid="fn1">a</xref></td><td>6</td><td>3</td>'
        '</tr></tbody></table><table-wrap-foot><fn id="fn1"><label>a</label><p>See note.</p>'
        '</fn></table-wrap-foot></table-wrap></body></article>'
    ).encode('utf-8')
    table = _table_result(project_jats_tables(source))

    assert table['eligibility'] == 'UNSUPPORTED'
    assert table['skip_reasons'] == [{
        'reason': 'FOOTNOTE_SEMANTICS_NOT_RESOLVED',
    }]
    assert table['candidate_count'] == 0


def test_missing_and_duplicate_operand_columns_are_skipped():
    missing = _table_result(_document(headers=('n', 'SD'), values=('4', '6')))
    duplicate = _table_result(_document(
        headers=('n', 'n', 'SD', 'SE'), values=('4', '4', '6', '3'),
    ))

    assert missing['checked_rows'] == 0
    assert missing['skip_reasons'][0]['reason'] == 'MISSING_REQUIRED_OPERAND_COLUMN'
    assert duplicate['checked_rows'] == 0
    assert duplicate['skip_reasons'][0]['reason'] == 'DUPLICATE_OPERAND_COLUMNS'


def test_different_timepoint_or_unit_header_scope_is_not_compared():
    timepoints = _table_result(_document(
        grouped_headers=('Week 1', 'Week 1', 'Week 2'),
    ))
    units = _table_result(_document(
        grouped_headers=('Score (mm)', 'Score (mm)', 'Score (cm)'),
    ))

    assert timepoints['checked_rows'] == 0
    assert timepoints['skip_reasons'][0]['reason'] == 'OPERAND_SCOPE_OR_UNIT_HEADER_MISMATCH'
    assert units['checked_rows'] == 0
    assert units['skip_reasons'][0]['reason'] == 'OPERAND_SCOPE_OR_UNIT_HEADER_MISMATCH'


@pytest.mark.parametrize(
    ('values', 'reason'),
    [
        (('100000000000000000000000', '6', '3'), 'NUMERIC_TOKEN_TOO_LONG'),
        (('4', '1e100', '3'), 'SD_OR_SE_NOT_A_BOUNDED_DECIMAL'),
        (('4', '6', '0.123456789'), 'SD_OR_SE_NOT_A_BOUNDED_DECIMAL'),
        (('1000000001', '6', '3'), 'N_OUTSIDE_SUPPORTED_RANGE'),
    ],
)
def test_huge_and_pathological_numeric_cells_fail_closed(values, reason):
    table = _table_result(_document(values=values))

    assert table['checked_rows'] == 0
    assert table['candidate_count'] == 0
    assert table['skip_reasons'][0]['reason'] == reason


def test_unreliable_table_structure_is_not_checked():
    document = _document(extra='')
    table = document.tables[0]
    from dataclasses import replace

    document = replace(document, tables=(replace(table, structure_status='TABLE_STRUCTURE_UNSUPPORTED'),))
    result = _table_result(document)

    assert result['applicability'] == 'APPLICABLE'
    assert result['eligibility'] == 'UNSUPPORTED'
    assert result['checked_rows'] == 0
    assert result['skip_reasons'] == [{'reason': 'TABLE_STRUCTURE_NOT_RELIABLE'}]


def test_non_jats_document_is_not_treated_as_source_mapped_input():
    document = _document()
    from dataclasses import replace

    result = _table_result(replace(document, source_format='markdown'))

    assert result['eligibility'] == 'UNSUPPORTED'
    assert result['skip_reasons'] == [{'reason': 'SOURCE_FORMAT_NOT_JATS_XML'}]


def test_explicit_formula_and_independence_both_required_even_when_numbers_disagree():
    without_formula = _table_result(_document(title='Independent observations'))
    assert without_formula['checked_rows'] == 0
    assert without_formula['skip_reasons'][0]['reason'] == 'EXPLICIT_INDEPENDENT_SE_FORMULA_REQUIRED'

    without_independence = _table_result(_document(title='SE = SD/sqrt(n)'))
    assert without_independence['checked_rows'] == 0
    assert without_independence['skip_reasons'][0]['reason'] == 'EXPLICIT_INDEPENDENT_SE_FORMULA_REQUIRED'


@pytest.mark.parametrize("caption", [
    "Weighted independent observations; SE = SD/sqrt(n)",
    "Independent observations; SE = SD/sqrt(n) in paired samples",
    "Independent observations; SE = SD/sqrt(n) with clustering",
    "Independent observations; SE = SD/sqrt(n) in cluster randomized sampling",
    "Independent observations; SE = SD/sqrt(n) but values were adjusted",
    "Independent observations; SE = SD/sqrt(n) for repeated measures",
])
def test_adjusted_clustered_or_paired_scopes_cannot_generate_candidate(caption):
    result = _table_result(_document(title=caption, values=('4', '6.0', '2.9')))
    assert result['candidate_count'] == 0
    assert result['status'] == 'UNSUPPORTED'
    assert result['skip_reasons'][0]['reason'] == 'TABLE_HAS_SCOPE_OR_TRANSFORM_AMBIGUITY'


def test_reported_arithmetic_is_only_a_candidate_not_scientific_error():
    source = Path(__file__).resolve().parents[1] / "examples/synthetic-jats/se-statistics.xml"
    report = jats_product.make_report(source.read_bytes(), "invented", False, include_sd_se_n=True)
    review = report["statistical_se_review"]
    assert review["scope"] == "explicit_caption_simple_standard_error_of_independent_observations_only"
    assert review["scan_complete"] is True
    assert len(review["findings"]) == 1
    assert review["findings"][0]["recomputed_se_at_display_precision"] == "3.0"
    assert review["findings"][0]["reported_se"] == "2.9"
    assert report["paper_error_established"] is False
    assert report["external_actions"] == "OUT_OF_SCOPE"
    assert "statistical_se_review" not in jats_product.make_report(source.read_bytes(), "invented", False)


def test_original_xml_byte_anchors_and_row_context_are_present():
    source = (Path(__file__).resolve().parents[1] / "examples/synthetic-jats/se-statistics.xml").read_bytes()
    review = jats_product.make_report(source, "invented", False, include_sd_se_n=True)["statistical_se_review"]
    item = review["findings"][0]
    anchors = [v["source_anchor"] for v in item["source_anchors"]] + [item["row_context_anchor"]]
    assert len(anchors) == 4
    for a in anchors:
        assert a["source_sha256"] == __import__("hashlib").sha256(source).hexdigest()
        assert a["source_format"] == "jats_xml"
        assert a["start_byte"] < a["end_byte"]
        assert source[a["start_byte"]:a["end_byte"]].startswith((b"<th", b"<td"))


def test_context_and_report_output_are_deterministic_with_strict_decimal_traps():
    saved = DefaultContext.copy()
    try:
        DefaultContext.prec = 3
        DefaultContext.traps[Inexact] = True
        DefaultContext.traps[InvalidOperation] = True
        report = check_jats_sd_se_n_tables(_document(values=("3", "1", "0.58")))
        assert report["tables"][0]["checks"][0]["status"] == "CONSISTENT_WITH_ROUNDING"
    finally:
        DefaultContext.prec = saved.prec
        DefaultContext.traps = saved.traps.copy()


def test_opt_in_bundle_and_replay_and_tamper_rejection(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/synthetic-jats/se-statistics.xml"
    folder = tmp_path / "result"
    audit = jats_product.audit_source(source, folder, "synthetic", include_sd_se_n=True)
    report = json.loads((folder / "report.json").read_bytes())
    assert "statistical_se_review" in report
    assert len(report["statistical_se_review"]["findings"]) == 1
    assert "Opt-in SD/SE/n" in (folder / "report.html").read_text(encoding="utf-8")
    assert jats_product.replay_bundle(folder, audit["manifest_sha256"])["status"] == "verified"
    report["statistical_se_review"]["findings"][0]["reported_se"] = "99"
    modified = jats_product.canonical_json(report)
    (folder / "report.json").write_bytes(modified)
    manifest = json.loads((folder / "manifest.json").read_bytes())
    manifest["files"]["report.json"] = {
        "sha256": jats_product.digest(modified), "bytes": len(modified),
    }
    (folder / "manifest.json").write_bytes(jats_product.canonical_json(manifest))
    with pytest.raises(ValueError, match="replay disagrees"):
        jats_product.replay_bundle(folder)


def test_cli_opt_in_sd_se_n_and_default_separation(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = root / "examples/synthetic-jats/se-statistics.xml"
    output = tmp_path / "review"
    result = subprocess.run(
        [sys.executable, "-m", "researchwitness", "audit-jats", str(source),
         "--document-id", "synthetic", "--output-dir", str(output),
         "--include-sd-se-n"], cwd=root, capture_output=True, text=True, timeout=35,
    )
    assert result.returncode == 0, result.stderr
    reread = subprocess.run(
        [sys.executable, "-m", "researchwitness", "replay-jats", str(output)],
        cwd=root, capture_output=True, text=True, timeout=35,
    )
    assert reread.returncode == 0, reread.stderr


def test_optional_stats_and_structure_are_replayable_together(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / "examples/synthetic-jats/se-statistics.xml"
    output = tmp_path / "both"
    report = jats_product.audit_source(fixture, output, "synthetic", include_sd_se_n=True, include_structure=True)
    saved = json.loads((output / "report.json").read_bytes())
    assert "table_projection" in saved and "statistical_se_review" in saved
    assert jats_product.replay_bundle(output, report["manifest_sha256"])["status"] == "verified"


def test_unrelated_report_label_injection_remains_html_escaped(tmp_path):
    fixture = (Path(__file__).resolve().parents[1] / "examples/synthetic-jats/se-statistics.xml").read_bytes()
    manipulated = fixture.replace(b'Score</th>', b'&lt;script&gt;Score&lt;/script&gt;</th>')
    source = tmp_path / "malicious.xml"
    source.write_bytes(manipulated)
    out = tmp_path / "out"
    jats_product.audit_source(source, out, "synthetic", include_sd_se_n=True)
    html = (out / "report.html").read_text("utf-8")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_statistic_candidate_cap_preserves_incomplete_coverage(monkeypatch):
    import researchwitness.paper_statistics_source as stats
    monkeypatch.setattr(stats, "MAX_STATISTICS_FINDINGS", 0)
    result = check_jats_sd_se_n_tables(_document(values=("4", "6.0", "2.9")))
    assert result["findings"] == []
    assert result["scan_complete"] is False
    assert "STATISTICS_CANDIDATE_LIMIT" in result["limitations"]


def test_rounded_sd_cannot_produce_false_discrepancy():
    # Underlying SD=1.04 displays 1.0 and yields SE=0.52 for n=4.
    report = check_jats_sd_se_n_tables(_document(values=('4', '1.0', '0.52')))
    assert report['findings'] == []
    check = report['tables'][0]['checks'][0]
    assert check['status'] == 'ROUNDING_COMPATIBLE'
    assert check['printed_value_compatibility'] == 'SOME_UNDERLYING_VALUES_COMPATIBLE'


def test_sd_and_se_display_intervals_genuinely_incompatible():
    report = check_jats_sd_se_n_tables(_document(values=('4', '6.0', '2.9')))
    assert len(report['findings']) == 1
    assert report['findings'][0]['printed_value_compatibility'] == 'INCOMPATIBLE_WITH_DECLARED_FORMULA'
    assert report['findings'][0]['sd_display_precision'] == 1


@pytest.mark.parametrize("title", [
    "Not independent observations; SE = SD/sqrt(n)",
    "Independent observations; SE = SD/sqrt(n) only applies to panel B",
    "Independent observations; SE = SD/sqrt(n), missing observations were excluded",
    "Independent observations; SE = SD/sqrt(n), complete-case subsets differ",
    "Independent observations; SE = SD/sqrt(n) with correlations",
    "Independent observations; SE = SD/sqrt(n) is not the formula used",
])
def test_negated_formula_panel_and_missingness_fail_closed(title):
    table = _table_result(_document(title=title, values=('4', '6.0', '2.9')))
    assert table['status'] == 'UNSUPPORTED'
    assert table['checked_objects'] == 0
    assert table['skip_reasons'][0]['reason'] == 'TABLE_HAS_SCOPE_OR_TRANSFORM_AMBIGUITY'
