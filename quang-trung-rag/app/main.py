import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import config
from .generation import generate, model_status
from .retrieval import Engine
from .concepts import prepare_query

Category = Literal['boi-canh', 'chuan-bi', 'dien-bien', 'nghe-thuat', 'nhan-vat', 'di-san']


@asynccontextmanager
async def lifespan(app):
    app.state.engine = Engine()
    yield


app = FastAPI(title='Kỷ Dậu 1789 · Tra cứu lịch sử', version='1.0.0', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=config.ROOT / 'app' / 'static'), name='static')


class SearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1200)
    mode: Literal['graph', 'baseline'] = 'graph'
    category: Category | None = None
    limit: int = Field(default=6, ge=1, le=10)

    @field_validator('question')
    @classmethod
    def question_not_blank(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('Nhập câu hỏi có ít nhất 3 ký tự.')
        return value.strip()


@app.get('/', include_in_schema=False)
def home():
    return FileResponse(config.ROOT / 'app' / 'static' / 'index.html')


@app.get('/api/health')
def health(request: Request):
    return {'status': 'ok', 'project': 'quang-trung-rag', 'dense_ready': request.app.state.engine.dense is not None}


@app.get('/api/stats')
def stats(request: Request):
    engine = request.app.state.engine
    return {**engine.data['stats'], 'dense_ready': engine.dense is not None,
            'chat_model': config.CHAT_MODEL, 'embedding_model': config.EMBED_MODEL}


@app.get('/api/models')
def models():
    return model_status()


@app.post('/api/search')
def search(payload: SearchRequest, request: Request):
    start = time.perf_counter()
    result = request.app.state.engine.search(**payload.model_dump())
    return {**result, 'mode': payload.mode, 'elapsed_ms': round((time.perf_counter() - start) * 1000)}


@app.post('/api/ask')
def ask(payload: SearchRequest, request: Request):
    start = time.perf_counter()
    result = request.app.state.engine.search(**payload.model_dump())
    sources = result['sources']
    context = [s for s in sources if s['score'] >= sources[0]['score'] * 0.60][:config.CONTEXT_CHUNKS] if sources else []
    canonical = prepare_query(payload.question)
    if any(word in canonical for word in ['ngay', 'khi nao', 'truoc', 'sau', 'thoi gian', 'bao gio']):
        dated, seen = [], set()
        for source in sources:
            event_keys = {(e['title'], e['gregorian']) for e in source.get('event_dates', [])}
            if event_keys - seen:
                dated.append(source)
                seen.update(event_keys)
        if dated:
            context = dated[:config.CONTEXT_CHUNKS]
    # Source comparison questions must retain both distinct accounts.
    if any(word in payload.question.lower() for word in ['quân số', 'bao nhiêu quân', 'đối chiếu', 'đô đốc long', 'đặng tiến đông']):
        context = sources[:config.CONTEXT_CHUNKS]
    answer = generate(payload.question, context)
    return {**result, **answer, 'mode': payload.mode, 'model': config.CHAT_MODEL,
            'context_citations': [s['citation'] for s in context], 'elapsed_ms': round((time.perf_counter() - start) * 1000)}


@app.get('/api/entities')
def entities(request: Request):
    return request.app.state.engine.data['nodes']


@app.get('/api/graph')
def graph(request: Request, entity: str | None = None, category: Category | None = None):
    engine = request.app.state.engine
    if entity and entity not in engine.entities:
        raise HTTPException(404, 'Không tìm thấy thực thể.')
    return engine.graph(entity=entity, category=category)


@app.get('/api/documents')
def documents(request: Request):
    return request.app.state.engine.data['sources']


@app.get('/api/records')
def records(request: Request, category: Category | None = None):
    engine = request.app.state.engine
    return [{**r, 'publisher': engine.sources[r['source_id']]['publisher'],
             'source_url': engine.sources[r['source_id']]['url']} for r in engine.records if category is None or r['category'] == category]


@app.get('/api/records/{record_id}')
def record(record_id: str, request: Request):
    engine = request.app.state.engine
    if record_id not in engine.by_id:
        raise HTTPException(404, 'Không tìm thấy ghi chép.')
    item = engine.records[engine.by_id[record_id]]
    return {**item, 'source': engine.sources[item['source_id']]}


@app.get('/api/documents/{source_id}/download')
def download_document(source_id: str, request: Request):
    if source_id not in request.app.state.engine.sources:
        raise HTTPException(404, 'Không tìm thấy tài liệu.')
    return FileResponse(config.ROOT / 'data' / 'documents' / f'{source_id}.md', filename=f'{source_id}.md', media_type='text/markdown; charset=utf-8')


@app.get('/api/timeline')
def timeline(request: Request):
    return request.app.state.engine.data['timeline']


@app.get('/api/export')
def export():
    return FileResponse(config.DATASET_PATH, media_type='application/json', filename='quang-trung-1789.json')
