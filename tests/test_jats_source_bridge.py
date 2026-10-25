"""Canonical source bridge: preserve ambiguity and actual original-byte anchors."""
from dataclasses import replace
from decimal import Inexact, localcontext
from fractions import Fraction
from hashlib import sha256
import json
import pytest

from researchwitness.paper_document import NumericAssertion, PaperDocument, Paragraph, Section, SourceAnchor
from tools import jats_source_adapter as adapter


def article(value='4 (8.10%)', denominator=True):
    heading = 'n (%) N=50' if denominator else 'n (%)'
    return (f'<article><body><p>Ä &amp; β before table.</p><table-wrap id="T1"><table>'
            f'<thead><tr><th>Outcome</th><th>{heading}</th></tr></thead>'
            f'<tbody><tr><td>Response</td><td>{value}</td></tr></tbody>'
            '</table></table-wrap></body></article>').encode('utf-8')


@pytest.mark.parametrize(('n','d','p','reported','expected','matches'), [
    (4,50,2,'8.10','8.00',False), (4,50,2,'8.00','8.00',True),
    (1,32,2,'3.12','3.13',False), (1,32,2,'3.13','3.13',True),
    (0,3,6,'0.000000','0.000000',True), (3,3,0,'100','100',True),
])
def test_replay_exact_half_up(n,d,p,reported,expected,matches):
    with localcontext() as ctx:
        ctx.prec = 1
        ctx.traps[Inexact] = True
        result = adapter.replay_percentage(n,d,reported,p)
    assert result['rounded_percent'] == expected
    assert result['arithmetic_matches'] is matches
    assert Fraction(int(result['exact_numerator']),int(result['exact_denominator'])) == Fraction(100*n,d)


@pytest.mark.parametrize('args', [(True,2,'50',0),(1,False,'50',0),(1,0,'0',0),
                                  (3,2,'150',0),(1,2,'NaN',0),(1,2,'50.00',1),
                                  (1,2,'50',True),(1,2,'50.0',7),(1,2,'-50',0),
                                  (1,2,'101',0),(1,10**12+1,'0',0)])
def test_invalid_replay_inputs(args):
    with pytest.raises(adapter.SourceAdapterError):
        adapter.replay_percentage(*args)


def test_legacy_model_reused_without_fabricated_context():
    anchor = SourceAnchor('source.xml','a'*64,'jats_xml','/article[1]','text',0,10)
    assertion = NumericAssertion('8.10','percent','count_percentage','4','50',None,None,None,None,None,anchor,())
    assert assertion.identity_key is None
    explicit = replace(assertion,population=' PEOPLE ',group='All',outcome='Response',
                       timepoint='Baseline',adjustment_status='unadjusted')
    assert explicit.identity_key == ('people','all','response','count_percentage','baseline','percent','unadjusted')
    paragraph = Paragraph('narrative',anchor)
    section = Section('Methods',('Methods',),(paragraph,),(),(),anchor)
    document = PaperDocument('v1','source.xml','a'*64,'jats_xml','Title',(section,),(),(),(assertion,),())
    assert document.text_projection() == b'Title\n\nMethods\n\nnarrative\n'
    assert document.to_dict()['numeric_assertions'][0]['population'] is None


def test_component_ids_bind_bytes_and_normalized_character_span():
    one = adapter.component_id('a'*64,1,20,0,8)
    assert one == adapter.component_id('a'*64,1,20,0,8)
    assert one != adapter.component_id('a'*64,1,20,1,8)
    assert one != adapter.component_id('b'*64,1,20,0,8)


def test_output_is_bounded_and_uses_lf(monkeypatch):
    assert adapter.bounded_report_bytes({'value':'Ä'}) == b'{"value":"\\u00c4"}\n'
    monkeypatch.setattr(adapter,'MAX_REPORT_BYTES',40)
    with pytest.raises(adapter.SourceAdapterError,match='ADAPTER_OUTPUT_LIMIT'):
        adapter.bounded_report_bytes({'value':'x'*100})


def test_real_detector_bridge_and_exact_source_spans():
    source = article()
    report = adapter.audit_jats_source(source)
    item = report['relations'][0]
    assert len(report['relations']) == 1
    assert item['alarm_emitted'] is True
    assert item['certificate_status'] == 'accepted'
    anchor = item['assertion']['source_anchor']
    assert source[anchor['start_byte']:anchor['end_byte']] == b'<td>4 (8.10%)</td>'
    assert anchor['quote'] == '4 (8.10%)'
    assert anchor['element_path'].endswith('/tbody[1]/tr[1]/td[2]')
    assert anchor['source_sha256'] == sha256(source).hexdigest()
    assert item['assertion']['population'] is None
    assert item['assertion']['adjustment_status'] is None
    assert item['certificate']['arithmetic']['rounded_percent'] == '8.00'
    assert report['anchor_semantics'] == 'original_xml_element_span_not_literal_quote_byte_offset'
    assert adapter.bounded_report_bytes(report) == adapter.bounded_report_bytes(adapter.audit_jats_source(source))


@pytest.mark.parametrize(('value','denominator','status'), [('4 (8.00%)',True,'arithmetic_match'),
                                                          ('4 (8.10%)',False,'scope_ambiguous')])
def test_match_and_abstention_are_not_promoted(value,denominator,status):
    report = adapter.audit_jats_source(article(value,denominator))
    item = report['relations'][0]
    assert item['detector_status'] == status and item['alarm_emitted'] is False
    if status == 'scope_ambiguous':
        assert item['assertion']['denominator'] is None
        assert item['certificate'] is None
        assert item['certificate_status'] == 'not_checked'


def test_existing_fixture_preserves_all_detector_results():
    from pathlib import Path
    from tools.jats_percentage_audit import audit_jats_percentage_tables
    source = (Path(__file__).resolve().parents[1]/'examples/synthetic-jats/article.xml').read_bytes()
    raw = audit_jats_percentage_tables(source)
    adapted = adapter.audit_jats_source(source)
    assert adapted['detector_report'] == raw
    assert [r['detector_status'] for r in adapted['relations']] == [r['status'] for r in raw['results']]
    assert len(adapted['relations']) == 3


def test_arithmetic_disagreement_does_not_erase_alarm(monkeypatch):
    original = adapter.replay_percentage
    def broken(*args):
        result = original(*args)
        result['rounded_percent'] = '9.99'
        return result
    monkeypatch.setattr(adapter,'replay_percentage',broken)
    relation = adapter.audit_jats_source(article())['relations'][0]
    assert relation['alarm_emitted'] is True
    assert relation['certificate_status'] == 'rejected'


def test_changed_detector_operand_cannot_detach_from_source(monkeypatch):
    from tools import jats_percentage_audit as detector
    original = detector.audit_jats_percentage_tables
    def corrupted(source):
        result = original(source)
        result['results'][0]['numerator'] = 5
        return result
    monkeypatch.setattr(detector,'audit_jats_percentage_tables',corrupted)
    with pytest.raises(adapter.SourceAdapterError,match='CELL_OPERAND_MISMATCH'):
        adapter.audit_jats_source(article())


def test_denominator_role_changes_relation_but_not_component(monkeypatch):
    from tools import jats_percentage_audit as detector
    original = detector.audit_jats_percentage_tables
    before = adapter.audit_jats_source(article())['relations'][0]
    def modified(source):
        report = original(source)
        report['results'][0]['denominator_scope'] += '-changed'
        return report
    monkeypatch.setattr(detector,'audit_jats_percentage_tables',modified)
    after = adapter.audit_jats_source(article())['relations'][0]
    assert before['target_id'] == after['target_id']
    assert before['relation_id'] != after['relation_id']


@pytest.mark.parametrize('source', [b'<!DOCTYPE article SYSTEM "file:///no-access"><article/>',
                                    b'<article><!ENTITY x "x"></article>', b'<not-article/>',
                                    b'\xff\xfe<article/>'])
def test_existing_source_refusals_are_preserved(source):
    with pytest.raises(ValueError):
        adapter.audit_jats_source(source)


def test_report_is_json_data_not_executable():
    assert json.loads(adapter.bounded_report_bytes({'text':'__import__("os").system("anything")'}))['text'].startswith('__import__')
