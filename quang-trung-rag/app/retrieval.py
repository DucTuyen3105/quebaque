import math
from collections import Counter, defaultdict

import httpx
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from . import config
from .concepts import detect, tokens, prepare_query
from .corpus import build_index


def embed(texts, query=False):
    inputs = [f'task: search result | query: {text}' if query else f'title: Chiến dịch Quang Trung 1789 | text: {text}' for text in texts]
    with httpx.Client(timeout=config.OLLAMA_TIMEOUT, trust_env=False) as client:
        response = client.post(f'{config.OLLAMA_URL}/api/embed', json={'model': config.EMBED_MODEL, 'input': inputs, 'truncate': False, 'keep_alive': '10m'})
        response.raise_for_status()
        vectors = np.asarray(response.json()['embeddings'], dtype=np.float32)
    if vectors.ndim != 2 or len(vectors) != len(texts) or not np.isfinite(vectors).all():
        raise ValueError('Embedding không hợp lệ.')
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)


class Engine:
    def __init__(self):
        self.data = build_index()
        self.records = self.data['records']
        self.by_id = {r['id']: i for i, r in enumerate(self.records)}
        self.sources = {s['id']: s for s in self.data['sources']}
        self.entities = {e['id']: e for e in self.data['entities']}
        self.categories = {c['id']: c['title'] for c in self.data['categories']}
        self.entity_records = {n['id']: [self.by_id[rid] for rid in n['record_ids']] for n in self.data['nodes']}
        texts = [r['title'] + ' ' + r['text'] + ' ' + ' '.join(r['keywords']) for r in self.records]
        self.vectorizer = TfidfVectorizer(preprocessor=lambda text: ' '.join(tokens(text)), ngram_range=(1, 2), sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform(texts)
        self.counts = [Counter(tokens(text)) for text in texts]
        self.df = Counter(term for counts in self.counts for term in counts)
        self.lengths = np.array([sum(c.values()) for c in self.counts])
        self.average_length = float(np.mean(self.lengths))
        self.dense = None
        self.load_embeddings()

    @property
    def signature(self):
        return self.data['stats']['sha256'] + ':history-v1:' + config.EMBED_MODEL

    def load_embeddings(self):
        path = config.INDEX_DIR / 'embeddings.npz'
        if path.exists():
            with np.load(path, allow_pickle=False) as saved:
                if str(saved['signature']) == self.signature and list(saved['ids']) == [r['id'] for r in self.records]:
                    self.dense = saved['vectors']

    def create_embeddings(self):
        vectors = []
        for start in range(0, len(self.records), 4):
            batch = self.records[start:start + 4]
            vectors.extend(embed([r['title'] + '\n' + r['text'] for r in batch]))
            print(f'Embedding: {len(vectors)}/{len(self.records)}', flush=True)
        np.savez_compressed(config.INDEX_DIR / 'embeddings.npz', vectors=np.asarray(vectors), ids=[r['id'] for r in self.records], signature=self.signature)
        self.load_embeddings()

    def search(self, question, mode='graph', category=None, limit=6):
        canonical = prepare_query(question)
        concepts = detect(canonical, self.data['entities'])
        query_tokens = set(tokens(canonical))
        lexical = (self.matrix @ self.vectorizer.transform([canonical]).T).toarray().ravel()
        bm25 = np.zeros(len(self.records))
        for term in query_tokens:
            idf = math.log(1 + (len(self.records) - self.df[term] + 0.5) / (self.df[term] + 0.5))
            for i, counts in enumerate(self.counts):
                tf = counts[term]
                if tf:
                    bm25[i] += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * self.lengths[i] / self.average_length))
        if bm25.max() > 0:
            bm25 /= bm25.max()
        scores = lexical * 0.6 + bm25 * 0.4
        warnings, backend, similarity = [], 'TF-IDF + BM25', None
        if self.dense is not None:
            try:
                similarity = (self.dense @ embed([question], query=True)[0]).clip(0, 1)
                scores = scores * 0.55 + similarity * 0.45
                backend = f'{config.EMBED_MODEL} + TF-IDF + BM25'
            except (httpx.HTTPError, ValueError, KeyError):
                warnings.append('Embedding Ollama chưa sẵn sàng; đang tra cứu bằng TF-IDF + BM25.')
        allowed = np.array([category is None or r['category'] == category for r in self.records])
        meaningful = [term for term in query_tokens if 0 < self.df[term] < len(self.records) * 0.8]
        term_weights = {term: math.log(1 + len(self.records) / (1 + self.df[term])) for term in query_tokens}
        total_weight = sum(term_weights.values()) or 1
        coverage = [sum(weight for term, weight in term_weights.items() if term in self.counts[i]) / total_weight for i in range(len(self.records))]
        lexical_evidence = any(allowed[i] and lexical[i] >= 0.12 and coverage[i] >= 0.55 for i in range(len(self.records)))
        semantic_evidence = similarity is not None and any(allowed[i] and similarity[i] >= 0.40 and lexical[i] >= 0.03 for i in np.argsort(-similarity)[:3])
        if not concepts and not lexical_evidence and not semantic_evidence:
            return {'sources': [], 'concepts': [], 'backend': backend, 'warnings': warnings, 'graph_added': 0}
        for i, record in enumerate(self.records):
            if concepts:
                scores[i] += 0.14 * len(set(concepts).intersection(record['entities'])) / len(concepts)
        if any(phrase in canonical for phrase in ['ngay nao', 'khi nao', 'truoc hay sau', 'thoi gian', 'bao gio']):
            query_places = {c for c in concepts if self.entities[c]['kind'] == 'place'}
            for event in self.data['timeline']:
                title_entities = set(detect(event['title'], self.data['entities']))
                if query_places.intersection(title_entities):
                    for rid in event['record_ids']:
                        scores[self.by_id[rid]] += 0.30
        base = scores.copy()
        reasons = defaultdict(list)
        if mode == 'graph':
            links = Counter({c: 1.0 for c in concepts})
            for edge in self.data['relations']:
                if edge['source'] in concepts:
                    links[edge['target']] += 0.45
                if edge['target'] in concepts:
                    links[edge['source']] += 0.30
            bonus = np.zeros(len(self.records))
            for entity, weight in links.items():
                for i in self.entity_records.get(entity, []):
                    if lexical[i] > 0.02 or (similarity is not None and similarity[i] > 0.32):
                        bonus[i] += weight / math.log(2 + len(self.entity_records[entity]))
                        reasons[i].append(self.entities[entity]['label'])
            if bonus.max() > 0:
                scores += 0.15 * bonus / bonus.max()
        scores[~allowed] = 0
        base[~allowed] = 0
        baseline = set(int(i) for i in np.argsort(-base)[:limit] if allowed[i] and base[i] > 0.08)
        selected = [int(i) for i in np.argsort(-scores) if allowed[i] and scores[i] > 0.08][:limit]
        sources = []
        for number, i in enumerate(selected, 1):
            record = self.records[i]
            source = self.sources[record['source_id']]
            sources.append({**record, 'citation': number, 'score': round(float(scores[i]), 4),
                'publisher': source['publisher'], 'source_title': source['title'], 'source_url': source['url'],
                'source_note': source['note'], 'category_title': self.categories[record['category']],
                'event_dates': [{'title': e['title'], 'gregorian': e['gregorian'], 'lunar': e['lunar']} for e in self.data['timeline'] if record['id'] in e['record_ids'] and e['gregorian']],
                'local_url': '/api/records/' + record['id'], 'via': reasons[i][:3],
                'graph_expanded': mode == 'graph' and i not in baseline and bool(reasons[i])})
        return {'sources': sources, 'concepts': concepts, 'backend': backend, 'warnings': warnings,
                'graph_added': sum(s['graph_expanded'] for s in sources)}

    def graph(self, entity=None, category=None):
        allowed = {r['id'] for r in self.records if category is None or r['category'] == category}
        edges = [{**e, 'evidence': [rid for rid in e['evidence'] if rid in allowed]} for e in self.data['edges']]
        edges = [e for e in edges if e['evidence']]
        nodes = [n for n in self.data['nodes'] if set(n['record_ids']).intersection(allowed)]
        if entity:
            edges = [e for e in edges if entity in [e['source'], e['target']]]
            keep = {entity} | {e['source'] for e in edges} | {e['target'] for e in edges}
            nodes = [n for n in nodes if n['id'] in keep]
        nodes.sort(key=lambda n: (n['id'] != entity, -n['mentions']))
        edges.sort(key=lambda e: (e['relation'] == 'co_occurs', -len(e['evidence'])))
        for edge in edges:
            edge['source_urls'] = sorted({self.sources[self.records[self.by_id[rid]]['source_id']]['url'] for rid in edge['evidence']})
        return {'nodes': nodes, 'edges': edges[:65], 'note': 'Nét liền là quan hệ biên soạn có bằng chứng; nét đứt chỉ biểu thị cùng được đề cập.'}
