import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.corpus import load_dataset
from app.generation import generate
from app.main import app
from app.retrieval import Engine


@pytest.fixture(scope='module')
def engine():
    engine = Engine()
    engine.dense = None
    return engine


@pytest.fixture(scope='module')
def client(engine):
    with patch('app.main.Engine', return_value=engine):
        with TestClient(app) as client:
            yield client


def test_dataset_has_traceable_sources_and_typed_relations(engine):
    dataset = load_dataset()
    assert len(dataset['sources']) == 6
    assert len(dataset['records']) == 20
    assert len(dataset['relations']) >= 20
    assert all(source['url'].startswith('https://') for source in dataset['sources'])
    for edge in dataset['relations']:
        for rid in edge['evidence']:
            record = engine.records[engine.by_id[rid]]
            assert {edge['source'], edge['target']}.issubset(record['entities'])
            assert record['source_id'] in engine.sources


@pytest.mark.parametrize('question,expected', [
    ('Quang Trung là ai?', {'len-ngoi'}),
    ('Nguyễn Huệ lên ngôi ở đâu và vào ngày nào?', {'len-ngoi'}),
    ('Vì sao quân Tây Sơn rút về Tam Điệp?', {'ke-sach-tam-diep'}),
    ('vi sao quan Tay Son rut ve Tam Diep', {'ke-sach-tam-diep'}),
    ('Hà Hồi được hạ vào ngày nào?', {'tran-ha-hoi'}),
    ('Quang Trung đánh Ngọc Hồi bằng cách nào?', {'tam-chan', 'tran-ngoc-hoi'}),
    ('Đô đốc Bảo có vai trò gì tại Đầm Mực?', {'dam-muc'}),
    ('Ngô Thì Nhậm làm gì sau chiến thắng?', {'ngoai-giao-sau-thang-loi'}),
    ('Vì sao cho quân ăn Tết sớm?', {'khao-quan'}),
    ('Lễ hội Đống Đa diễn ra khi nào?', {'le-hoi-dong-da'}),
    ('Gò Đống Đa được xếp hạng năm nào?', {'xep-hang-di-tich'}),
])
def test_real_history_questions_find_their_evidence(engine, question, expected):
    for mode in ['baseline', 'graph']:
        result = engine.search(question, mode=mode)
        assert expected.intersection(s['id'] for s in result['sources'][:4]), (mode, question)


@pytest.mark.parametrize('question', ['Thời tiết Hà Nội hôm nay thế nào?', 'Giá bitcoin hôm nay bao nhiêu?', 'Nấu phở như thế nào?', 'SQA là gì?'])
def test_unrelated_questions_do_not_get_history_answers(engine, question):
    assert not engine.search(question)['sources']


def test_category_filter_survives_graph_expansion(engine):
    sources = engine.search('Ngô Thì Nhậm có vai trò gì?', category='nhan-vat')['sources']
    assert sources and all(s['category'] == 'nhan-vat' for s in sources)


def test_different_accounts_are_preserved(engine):
    sources = engine.search('Quân Thanh có bao nhiêu quân?')['sources']
    assert {'dong-da-theo-chinhphu', 'nam-dao-quan'}.issubset({s['id'] for s in sources[:4]})
    assert '20 vạn' in engine.records[engine.by_id['dong-da-theo-chinhphu']]['text']
    assert '29 vạn' in engine.records[engine.by_id['nam-dao-quan']]['text']
    assert 'Đặng Tiến Đông' not in engine.entities['do-doc-long']['aliases']
    graph = engine.graph(entity='khuong-thuong')
    assert {'do-doc-long', 'dang-tien-dong'}.issubset({n['id'] for n in graph['nodes']})


def test_timeline_distinguishes_calendar_types(engine):
    events = engine.data['timeline']
    assert len(events) == 7
    assert events[0]['gregorian'] is None
    assert events[-1]['gregorian'] is None
    assert events[4]['gregorian'] == '1789-01-28' and 'Mồng 3' in events[4]['lunar']
    assert events[5]['gregorian'] == '1789-01-30' and 'Mồng 5' in events[5]['lunar']


def test_project_paths_are_independent():
    assert config.ROOT.name == 'quang-trung-rag'
    assert config.DATASET_PATH.is_relative_to(config.ROOT)
    assert config.INDEX_DIR.is_relative_to(config.ROOT)
    assert config.PORT == 8010
    assert config.OLLAMA_URL.endswith(':11435')
    paths = list((config.ROOT / 'app').rglob('*.py')) + list((config.ROOT / 'scripts').glob('*.py')) + list(config.ROOT.glob('*.sh'))
    assert all('giaotrinh-rag' not in path.read_text() for path in paths)


def test_api_sources_export_and_validation(client):
    assert client.get('/').status_code == 200
    assert client.get('/api/health').json()['project'] == 'quang-trung-rag'
    assert client.get('/api/stats').json()['sources'] == 6
    assert len(client.get('/api/timeline').json()) == 7
    assert client.get('/api/records/tran-ha-hoi').json()['source']['url'].startswith('https://')
    assert client.get('/api/records/missing').status_code == 404
    assert client.get('/api/graph?entity=missing').status_code == 404
    assert client.get('/api/export').json()['title'].startswith('Quang Trung')
    assert client.get('/api/documents/chinhphu-2013/download').status_code == 200
    assert client.get('/api/documents/missing/download').status_code == 404
    assert client.post('/api/search', json={'question': '   '}).status_code == 422
    assert client.post('/api/search', json={'question': 'Quang Trung', 'category': 'unknown'}).status_code == 422
    assert client.post('/api/search', json={'question': 'Quang Trung', 'mode': 'unknown'}).status_code == 422


def test_ollama_failure_returns_explicit_notes(engine):
    sources = engine.search('Hà Hồi được hạ vào ngày nào?')['sources'][:3]
    with patch('app.generation.httpx.Client.post', side_effect=httpx.ConnectError('offline')):
        result = generate('Hà Hồi được hạ vào ngày nào?', sources)
    assert result['answer_mode'] == 'extractive' and result['generation_warning']
    assert '[1]' in result['answer']


def test_invalid_citation_is_not_shown_as_generated_answer(engine):
    sources = engine.search('Hà Hồi')['sources'][:3]
    content = json.dumps({'paragraphs': [{'text': 'Không có nguồn.', 'source_ids': [99]}]})
    response = httpx.Response(200, json={'message': {'content': content}}, request=httpx.Request('POST', 'http://ollama/api/chat'))
    with patch('app.generation.httpx.Client.post', return_value=response):
        result = generate('Hà Hồi', sources)
    assert result['answer_mode'] == 'extractive'


def test_no_sources_does_not_call_generation_model(client):
    with patch('app.generation.httpx.Client.post') as call:
        response = client.request('POST', '/api/ask', json={'question': 'Thời tiết Hà Nội hôm nay thế nào?'})
    assert response.json()['answer_mode'] == 'no_evidence'
    call.assert_not_called()


def test_time_comparison_provides_both_dated_events_to_the_model(client):
    with patch('app.main.generate', return_value={'answer': 'Hà Hồi trước Ngọc Hồi [1].', 'answer_mode': 'generated', 'generation_warning': None}) as call:
        client.post('/api/ask', json={'question': 'Hà Hồi được hạ vào ngày nào, trước hay sau trận Ngọc Hồi?'})
    context = call.call_args.args[1]
    assert {'tran-ha-hoi', 'tran-ngoc-hoi'}.issubset({s['id'] for s in context})
    dates = {event['gregorian'] for s in context for event in s['event_dates']}
    assert {'1789-01-28', '1789-01-30'}.issubset(dates)
