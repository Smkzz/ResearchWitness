"""Adversarial source-mapped PRISMA flows on the installed ORIGINAL-byte JATS parser."""
from __future__ import annotations

from researchwitness.jats_table_projection import project_jats_tables
from researchwitness.paper_prisma_flow import map_jats_prisma_relations


def _document(paragraph: str):
    source = (
        '<article><front><article-meta><title-group><article-title>Review</article-title>'
        '</title-group></article-meta></front><body><sec><title>Methods</title><p>'
        + paragraph
        + '</p></sec></body></article>'
    ).encode('utf-8')
    return project_jats_tables(source, include_body_paragraphs=True)


def test_explicit_prisma_labels_map_counts_and_transition_anchors():
    document = _document(
        'PRISMA systematic review: records identified: 1,200; duplicates removed: 200; '
        'records screened: 1,000.'
    )

    relation = map_jats_prisma_relations(document)[0]
    assert relation.status == 'PRISMA_FLOW_BALANCED'
    assert (relation.records_identified, relation.duplicates_removed, relation.records_screened) == (
        1200, 200, 1000,
    )
    assert len(relation.source_anchors) == 4
    assert all(anchor.source_sha256 == document.source_sha256 for _, anchor in relation.source_anchors)
    assert all(anchor.start_byte == document.paragraphs[0].source_anchor.start_byte
               for _, anchor in relation.source_anchors)
    assert all(anchor.end_byte == document.paragraphs[0].source_anchor.end_byte
               for _, anchor in relation.source_anchors)
    assert {role for role, _ in relation.source_anchors} == {
        'records_identified', 'duplicates_removed', 'records_screened', 'transition',
    }


def test_explicit_prisma_arithmetic_mismatch_is_candidate_only():
    relation = map_jats_prisma_relations(_document(
        'PRISMA review: records identified: 100; duplicates removed: 20; records screened: 79.'
    ))[0]

    assert relation.status == 'PRISMA_FLOW_ARITHMETIC_CANDIDATE'
    assert relation.expected_screened == 80
    assert relation.difference == -1
    assert relation.to_dict()['source_anchors'][0]['source_anchor']['quote']


def test_multiple_database_or_later_synthesis_scopes_are_unsupported():
    multiple_databases = map_jats_prisma_relations(_document(
        'PRISMA review searched multiple databases: records identified: 100; '
        'duplicates removed: 20; records screened: 80.'
    ))[0]
    later_stage = map_jats_prisma_relations(_document(
        'PRISMA systematic review: records identified: 100; duplicates removed: 20; '
        'records screened: 80; full-text reports assessed: 30.'
    ))[0]

    assert multiple_databases.status == 'UNSUPPORTED'
    assert multiple_databases.reason == 'PRISMA_SCOPE_OR_STAGE_AMBIGUOUS'
    assert later_stage.status == 'UNSUPPORTED'
    assert later_stage.reason == 'PRISMA_SCOPE_OR_STAGE_AMBIGUOUS'


def test_unlabelled_narrative_or_non_review_counts_do_not_become_arithmetic():
    unlabelled = map_jats_prisma_relations(_document(
        'PRISMA systematic review: records identified 100; duplicates removed 20; records screened 80.'
    ))[0]
    non_review = map_jats_prisma_relations(_document(
        'The hospital records identified 100 cases and the records screened were 80.'
    ))

    assert unlabelled.status == 'UNSUPPORTED'
    assert unlabelled.reason == 'PRISMA_LABELLED_TRANSITION_NOT_RECOGNIZED'
    assert non_review == ()


def test_mapper_rejects_malformed_grouping_and_oversize_count():
    malformed = map_jats_prisma_relations(_document(
        'PRISMA review: records identified: 12,00; duplicates removed: 2; records screened: 10.'
    ))[0]
    too_large = map_jats_prisma_relations(_document(
        'PRISMA review: records identified: 9,999,999,999,999; duplicates removed: 1; '
        'records screened: 9,999,999,999,998.'
    ))[0]

    assert malformed.status == 'UNSUPPORTED'
    assert too_large.status == 'UNSUPPORTED'
    assert too_large.reason == 'PRISMA_COUNT_OUT_OF_BOUNDS'


def test_legacy_projection_is_not_used_for_jats_prose():
    paragraph = ('PRISMA review: records identified: 100; duplicates removed: 20; '
                 'records screened: 80.')
    doc = _document(paragraph)
    source = doc.paragraphs[0].source_anchor
    assert source.source_format == "jats_xml"
    assert source.start_byte is not None and source.end_byte is not None
    assert source.start_byte < source.end_byte
    assert source.element_path.endswith("/p[1]")


def test_prisma_stages_separated_across_paragraphs_are_not_joined():
    source = (
        b"<article><body><sec><p>PRISMA review: records identified: 100;</p>"
        b"<p>duplicates removed: 20; records screened: 79.</p>"
        b"</sec></body></article>"
    )
    doc = project_jats_tables(source, include_body_paragraphs=True)
    relations = map_jats_prisma_relations(doc)
    assert all(item.status != "PRISMA_FLOW_ARITHMETIC_CANDIDATE" for item in relations)


def test_table_caption_and_complex_inline_text_not_promoted_to_source_prose():
    source = (
        b"<article><body><table-wrap id='diagram'><caption><p>"
        b"PRISMA systematic review: records identified: 100; duplicates removed: 20; "
        b"records screened: 79.</p></caption></table-wrap>"
        b"<p>PRISMA review: records identified: <xref rid='missing'>100</xref>; "
        b"duplicates removed: 20; records screened: 79.</p></body></article>"
    )
    doc = project_jats_tables(source, include_body_paragraphs=True)
    assert map_jats_prisma_relations(doc) == ()
    assert any(note.startswith("body_paragraphs_excluded:") for note in doc.extraction_warnings)


def test_nonreview_record_count_and_scope_conflict_abstain():
    unsupported = map_jats_prisma_relations(_document(
        "PRISMA review: records identified: 100; duplicates removed: 20; "
        "records screened: 79; full-text reports assessed: 15."
    ))
    assert len(unsupported) == 1
    assert unsupported[0].status == "UNSUPPORTED"
    assert unsupported[0].difference is None


def test_stable_installed_optional_review_and_bundle_replay(tmp_path):
    from researchwitness import jats_product
    source = (
        b"<article><body><sec><p>PRISMA review: records identified: 100; "
        b"duplicates removed: 20; records screened: 79.</p></sec></body></article>"
    )
    plain = jats_product.make_report(source, "source-only", False)
    assert "prisma_flow_review" not in plain
    report = jats_product.make_report(
        source, "source-only", True, include_prisma_flows=True,
    )
    view = report["prisma_flow_review"]
    assert view["relations_mapped"] == 1
    assert view["candidate_count"] == 1
    assert view["whole_article_coverage_established"] is False
    case = view["cases"][0]
    assert case["review_state"] == "unreviewed"
    assert case["scientific_error_status"] == "not_established"
    assert case["relation"]["difference_exact"] == "-1"
    assert case["relation"]["source_anchors"][0]["source_anchor"]["start_byte"] is not None
    assert report["paper_error_established"] is False
    html = jats_product.render_html(report)
    assert b"PRISMA record-flow review" in html
    assert b"Whole-article PRISMA coverage" in html
    assert b"unreviewed candidates, not confirmed paper errors" in html
    file = tmp_path / "example.xml"
    file.write_bytes(source)
    bundle = tmp_path / "report-bundle"
    receipt = jats_product.audit_source(
        file, bundle, "source-only", include_prisma_flows=True,
    )
    assert jats_product.replay_bundle(
        bundle, receipt["manifest_sha256"]
    )["status"] == "verified"


def test_installed_cli_opt_in_flag_and_canonical_replay(tmp_path):
    import json
    from pathlib import Path
    import subprocess
    import sys
    import researchwitness
    source = tmp_path / "s.xml"
    source.write_text(
        "<article><body><p>PRISMA review: records identified: 100; "
        "duplicates removed: 20; records screened: 79.</p></body></article>",
        encoding="utf-8",
    )
    bundle = tmp_path / "review"
    project_root = Path(researchwitness.__file__).resolve().parents[1]
    args = [
        sys.executable, "-m", "researchwitness", "audit-jats", str(source),
        "--output-dir", str(bundle), "--document-id", "sample",
        "--include-prisma-flows",
    ]
    completed = subprocess.run(args, cwd=project_root, capture_output=True, timeout=40)
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    payload = json.loads((bundle / "report.json").read_bytes())
    assert payload["prisma_flow_review"]["candidate_count"] == 1
    receipt = json.loads(completed.stdout)
    assert receipt["paper_error_established"] is False
    replay = subprocess.run([
        sys.executable, "-m", "researchwitness", "replay-jats",
        str(bundle), "--expected-manifest-sha256", receipt["manifest_sha256"],
    ], cwd=project_root, capture_output=True, timeout=40)
    assert replay.returncode == 0, replay.stderr.decode(errors="replace")
    assert json.loads(replay.stdout)["status"] == "verified"
