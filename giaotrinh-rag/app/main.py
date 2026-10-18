import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import config
from .context import select_context
from .generation import generate, model_status
from .retrieval import Engine

@asynccontextmanager
async def lifespan(app):
    app.state.engine = Engine()
    yield


app = FastAPI(title='Giáo trình · RAG + Knowledge Graph', version='1.0.0', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=config.ROOT / 'app' / 'static'), name='static')


class SearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1200)
    mode: Literal['graph', 'baseline'] = 'graph'
    chapter: int | None = Field(default=None, ge=1, le=11)
    limit: int = Field(default=6, ge=1, le=10)

    @field_validator('question')
    @classmethod
    def valid_question(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError('Nhập ít nhất 3 ký tự.')
        return value


@app.get('/', include_in_schema=False)
def home():
    return FileResponse(config.ROOT / 'app' / 'static' / 'index.html')


@app.get('/api/health')
def health(request: Request):
    engine = request.app.state.engine
    return {'status': 'ok', 'indexed': True, 'dense_ready': engine.dense is not None}


@app.get('/api/stats')
def stats(request: Request):
    engine = request.app.state.engine
    return {**engine.data['metadata'], 'dense_ready': engine.dense is not None,
            'embedding_model': config.EMBED_MODEL, 'chat_model': config.CHAT_MODEL}


@app.get('/api/models')
def models():
    return model_status()


@app.get('/api/document')
def document():
    return FileResponse(config.PDF_PATH, media_type='application/pdf', filename=config.PDF_PATH.name, content_disposition_type='inline')


@app.post('/api/search')
def search(payload: SearchRequest, request: Request):
    start = time.perf_counter()
    result = request.app.state.engine.search(**payload.model_dump())
    return {**result, 'mode': payload.mode, 'elapsed_ms': round((time.perf_counter() - start) * 1000)}


@app.post('/api/ask')
def ask(payload: SearchRequest, request: Request):
    start = time.perf_counter()
    result = request.app.state.engine.search(**payload.model_dump())
    retrieval_ms = round((time.perf_counter() - start) * 1000)
    sources = result['sources']
    # Weak graph neighbors remain inspectable in search results, but should not
    # distract a small local model from a much stronger piece of evidence.
    context = select_context(payload.question, sources, config.CONTEXT_CHUNKS)
    answer = generate(payload.question, context)
    return {**result, **answer, 'mode': payload.mode, 'model': config.CHAT_MODEL,
            'retrieval_ms': retrieval_ms, 'elapsed_ms': round((time.perf_counter() - start) * 1000),
            'context_citations': [s['citation'] for s in context]}


@app.get('/api/graph')
def graph(request: Request, concept: str | None = None, chapter: int | None = Query(default=None, ge=1, le=11)):
    engine = request.app.state.engine
    if concept and concept not in engine.concept_chunks:
        raise HTTPException(status_code=404, detail='Không tìm thấy khái niệm.')
    return engine.graph(concept=concept, chapter=chapter)


@app.get('/api/concepts')
def concepts(request: Request):
    return [{'id': n['id'], 'label': n['label'], 'mentions': n['mentions']} for n in sorted(request.app.state.engine.data['nodes'], key=lambda n: n['label'])]
