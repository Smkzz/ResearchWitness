"""Adversarial cases for source-mapped, labelled PRISMA record flow."""
from __future__ import annotations

from researchwitness.jats import parse_jats
from researchwitness.paper_prisma_flow import map_jats_prisma_relations


def _document(paragraph: str):
    source = (
        '<article><front><article-meta><title-group><article-title>Review</article-title>'
        '</title-group></article-meta></front><body><sec><title>Methods</title><p>'
        + paragraph
        + '</p></sec></body></article>'
    ).encode('utf-8')
    return parse_jats(source, 'review.xml')


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
