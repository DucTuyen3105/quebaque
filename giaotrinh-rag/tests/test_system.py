from unittest.mock import patch
from copy import copy

import json
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.concepts import normalize, prepare_query, tokens
from app.context import select_context
from app.generation import generate
from app.main import app
from app.retrieval import Engine


@pytest.fixture(scope='module')
def engine():
    value = Engine()
    value.dense = None  # Unit/integration suite is deterministic and offline.
    return value


@pytest.fixture(scope='module')
def client(engine):
    with patch('app.main.Engine', return_value=engine):
        with TestClient(app) as instance:
            yield instance


def test_pdf_provenance_and_actual_chapters(engine):
    metadata = engine.data['metadata']
    assert metadata['pages'] == 276
    assert [c['number'] for c in metadata['chapters']] == list(range(1, 12))
    assert metadata['chapters'][6]['title'] == 'Phương pháp phân tích hướng đối tượng'
    assert next(c for c in engine.chunks if c['pdf_page'] == 67)['printed_page'] == 66
    assert next(c for c in engine.chunks if c['pdf_page'] == 225)['printed_page'] == 224
    assert not any(c['pdf_page'] < 10 for c in engine.chunks)
    assert not any(c['pdf_page'] == 41 for c in engine.chunks)  # Review continuation.


@pytest.mark.parametrize('question,pages', [
    ('Xác minh và thẩm định khác nhau thế nào?', {43}),
    ('xac minh va tham dinh khac nhau the nao?', {43}),
    ('Mô hình xoắn ốc là gì?', {37, 38}),
    ('COCOMO là gì?', {57, 58, 59, 60, 61}),
    ('SQA là gì?', {18, 42}),
    ('Có những loại lớp nào trong phân tích hướng đối tượng?', {92}),
])
def test_retrieves_known_evidence(engine, question, pages):
    for mode in ['baseline', 'graph']:
        result = engine.search(question, mode=mode)
        assert pages.intersection(s['pdf_page'] for s in result['sources'][:3])


@pytest.mark.parametrize('question', ['Thời tiết Hà Nội ngày mai thế nào?', 'Giá bitcoin hôm nay bao nhiêu?', 'Nấu phở như thế nào?'])
def test_out_of_scope_has_no_evidence(engine, question):
    assert not engine.search(question)['sources']


def test_chapter_filter_is_respected_during_graph_expansion(engine):
    result = engine.search('Use case và yêu cầu', chapter=6, mode='graph')
    assert result['sources']
    assert all(s['chapter'] == 6 for s in result['sources'])


def test_graph_is_grounded_and_semantic_relations_have_evidence(engine):
    nodes = {n['id'] for n in engine.data['nodes']}
    semantic = []
    for edge in engine.data['edges']:
        assert edge['source'] in nodes and edge['target'] in nodes
        for cid in edge['evidence']:
            chunk = engine.chunks[engine.by_id[cid]]
            assert edge['source'] in chunk['concepts'] and edge['target'] in chunk['concepts']
            if edge['relation'] != 'co_occurs':
                assert normalize(edge['evidence_phrase']) in normalize(chunk['text'])
        if edge['relation'] != 'co_occurs':
            semantic.append(edge)
    assert len(semantic) >= 5
    graph = engine.graph(concept='use-case', chapter=6)
    ids = {n['id'] for n in graph['nodes']}
    assert all(e['source'] in ids and e['target'] in ids for e in graph['edges'])
    assert all(engine.chunks[engine.by_id[cid]]['chapter'] == 6 for e in graph['edges'] for cid in e['evidence'])


def test_ollama_failure_is_explicit_not_fake_generation(engine):
    sources = engine.search('SQA là gì?')['sources']
    with patch('app.generation.httpx.Client.post', side_effect=httpx.ConnectError('offline')):
        result = generate('SQA là gì?', sources)
    assert result['answer_mode'] == 'extractive'
    assert result['generation_warning']
    assert '[1]' in result['answer']


def test_invalid_model_citations_are_rejected(engine):
    sources = engine.search('SQA là gì?')['sources']
    content = json.dumps({'paragraphs': [{'text': 'Câu trả lời không có căn cứ.', 'source_ids': [99]}]})
    response = httpx.Response(200, json={'message': {'content': content}}, request=httpx.Request('POST', 'http://ollama/api/chat'))
    with patch('app.generation.httpx.Client.post', return_value=response):
        result = generate('SQA là gì?', sources)
    assert result['answer_mode'] == 'extractive'
    assert '[99]' not in result['answer']


def test_valid_model_response_is_returned(engine):
    sources = engine.search('SQA là gì?')['sources']
    content = json.dumps({'paragraphs': [{'text': 'SQA là đảm bảo chất lượng phần mềm.', 'source_ids': [1]}]})
    response = httpx.Response(200, json={'message': {'content': content}}, request=httpx.Request('POST', 'http://ollama/api/chat'))
    with patch('app.generation.httpx.Client.post', return_value=response) as call:
        result = generate('SQA là gì?', sources)
    assert result['answer_mode'] == 'generated'
    payload = call.call_args.kwargs['json']
    assert payload['model']
    assert payload['think'] is False
    assert payload['format']['properties']['paragraphs']['items']['properties']['source_ids']['items']['enum'] == [s['citation'] for s in sources]


def test_api_validation_pdf_and_graph(client):
    assert client.get('/').status_code == 200
    assert client.get('/api/health').json()['status'] == 'ok'
    assert client.get('/api/stats').json()['pages'] == 276
    assert client.post('/api/search', json={'question': '   '}).status_code == 422
    assert client.post('/api/search', json={'question': 'SQA', 'mode': 'invented'}).status_code == 422
    assert client.post('/api/search', json={'question': 'SQA', 'chapter': 12}).status_code == 422
    assert client.get('/api/graph?concept=missing').status_code == 404
    result = client.post('/api/search', json={'question': 'SQA là gì?'}).json()
    assert result['sources'] and result['sources'][0]['url'].startswith('/api/document#page=')
    pdf = client.get('/api/document', headers={'Range': 'bytes=0-99'})
    assert pdf.status_code == 206 and pdf.content.startswith(b'%PDF')
    assert 'inline' in pdf.headers['content-disposition']
    assert len(pdf.content) == 100


def test_no_evidence_never_calls_the_llm(client):
    with patch('app.generation.httpx.Client.post') as call:
        response = client.request('POST', '/api/ask', json={'question': 'Thời tiết Hà Nội ngày mai thế nào?'})
    assert response.json()['answer_mode'] == 'no_evidence'
    call.assert_not_called()


def test_weak_neighbors_do_not_distract_answer_context(client):
    with patch('app.main.generate', return_value={'answer': 'Có nguồn [1].', 'answer_mode': 'generated', 'generation_warning': None}) as call:
        response = client.post('/api/ask', json={'question': 'Xác minh và thẩm định khác nhau thế nào?', 'chapter': 4})
    context = call.call_args.args[1]
    assert context[0]['pdf_page'] == 43
    assert not any(s['pdf_page'] in [47, 49] for s in context)
    assert response.json()['context_citations'] == [s['citation'] for s in context]


@pytest.mark.parametrize('question', [
    'Ở trong pha phân tích, để trích xuất được các lớp thì bước đầu tiên là gì?',
    'Trong pha phân tích, bước đầu để trích rút các lớp là gì?',
    'o trong pha phan tich de trich xuat duoc cac lop thi buoc dau tien la gi',
    'Đầu tiên cần làm gì để rút ra các lớp?',
])
def test_class_extraction_paraphrases_include_the_complete_first_step(engine, question):
    for mode in ['baseline', 'graph']:
        sources = engine.search(question, mode=mode)['sources']
        relevant = [s for s in sources[:3] if s['pdf_page'] == 92]
        assert relevant, question
        assert 'mô hình hóa chức năng' in relevant[0]['text'].lower()
        assert relevant[0]['printed_page'] == 91
        # The overlapping window must not duplicate the sentence at the join.
        assert relevant[0]['text'].count('lớp Estimate Funds for Week') == 1


def test_analysis_keeps_its_meaning_after_accent_folding():
    assert tokens('phân tích') == ['phan', 'tich']


def test_semantic_evidence_is_allowed_without_a_dictionary_entity(engine):
    semantic = copy(engine)
    question = 'Quá trình rút các kiểu đối tượng diễn ra qua những bước nào?'
    assert not prepare_query(question)[1]
    assert not engine.search(question)['sources']
    # A strong semantic match is enough even when lexical similarity is low.
    semantic.dense = np.zeros((len(engine.chunks), 2), dtype=np.float32)
    gold = engine.by_id['p092-1']
    semantic.dense[gold] = [0.5, np.sqrt(0.75)]
    with patch('app.retrieval.embed', return_value=np.array([[1.0, 0.0]], dtype=np.float32)):
        sources = semantic.search(question)['sources']
    assert sources and sources[0]['pdf_page'] == 92


def test_corrected_question_reaches_answer_generation(client):
    question = 'Ở trong pha phân tích, để trích xuất được các lớp thì bước đầu tiên là gì?'
    with patch('app.main.generate', return_value={'answer': 'Mô hình hóa chức năng (Use-Case) [1].', 'answer_mode': 'generated', 'generation_warning': None}) as call:
        response = client.post('/api/ask', json={'question': question})
    assert response.status_code == 200
    assert response.json()['answer_mode'] == 'generated'
    assert any(s['pdf_page'] == 92 and 'mô hình hóa chức năng' in s['text'].lower() for s in call.call_args.args[1])


def test_first_step_uses_the_matching_procedure_instead_of_a_neighboring_method(engine):
    question = 'Ở trong pha phân tích, để trích xuất được các lớp thì bước đầu tiên là gì?'
    sources = engine.search(question)['sources']
    context = select_context(question, sources, 5)
    assert context and all(s['pdf_page'] == 92 for s in context)
    assert context[0]['context_text'].startswith('7.2 VIỆC TRÍCH RÚT CÁC LỚP THỰC THỂ')
    assert 'mô hình hóa chức năng' in context[0]['context_text'].lower()
    assert 'trích rút danh từ' not in context[0]['context_text'].lower()
