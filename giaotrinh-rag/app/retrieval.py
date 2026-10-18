import hashlib
import json
import math
from collections import Counter, defaultdict

import httpx
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from . import config
from .concepts import VOCABULARY, prepare_query, tokens
from .corpus import SCHEMA_VERSION, build_corpus


def embed(texts: list[str], *, query: bool = False) -> np.ndarray:
    inputs = texts
    if 'embeddinggemma' in config.EMBED_MODEL:
        inputs = [f'task: search result | query: {t}' if query else f'title: Nhập môn công nghệ phần mềm | text: {t}' for t in texts]
    with httpx.Client(timeout=config.OLLAMA_TIMEOUT, trust_env=False) as client:
        response = client.post(f'{config.OLLAMA_URL}/api/embed', json={
            'model': config.EMBED_MODEL, 'input': inputs, 'truncate': False, 'keep_alive': '10m',
        })
        response.raise_for_status()
        vectors = np.asarray(response.json()['embeddings'], dtype=np.float32)
    if vectors.ndim != 2 or len(vectors) != len(texts) or not np.isfinite(vectors).all():
        raise ValueError('Ollama trả về embedding không hợp lệ.')
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)


class Engine:
    def __init__(self, *, pdf=None, directory=None):
        self.pdf = pdf or config.PDF_PATH
        self.directory = directory or config.INDEX_DIR
        if not self.pdf.is_file():
            raise FileNotFoundError(f'Không tìm thấy PDF: {self.pdf}. Kiểm tra PDF_PATH trong .env.')
        cache = self.directory / 'corpus.json'
        digest = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.data = json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else None
        if not self.data or self.data['metadata'].get('schema_version') != SCHEMA_VERSION or self.data['metadata']['sha256'] != digest:
            self.data = build_corpus(self.pdf, self.directory)
        self.chunks = self.data['chunks']
        self.by_id = {c['id']: i for i, c in enumerate(self.chunks)}
        self.concept_chunks = {n['id']: [self.by_id[c] for c in n['chunk_ids']] for n in self.data['nodes']}
        texts = [c['text'] for c in self.chunks]
        self.vectorizer = TfidfVectorizer(preprocessor=lambda text: ' '.join(tokens(text)), ngram_range=(1, 2), sublinear_tf=True, max_df=0.98)
        self.matrix = self.vectorizer.fit_transform(texts)
        self.counts = [Counter(tokens(t)) for t in texts]
        self.lengths = np.array([sum(c.values()) for c in self.counts])
        self.avg_length = float(np.mean(self.lengths)) or 1
        self.df = Counter(t for c in self.counts for t in c)
        self.dense = None
        self.load_embeddings()

    @property
    def signature(self):
        return self.data['metadata']['sha256'] + ':' + str(SCHEMA_VERSION) + ':' + config.EMBED_MODEL

    def load_embeddings(self):
        path = self.directory / 'embeddings.npz'
        if path.exists():
            with np.load(path, allow_pickle=False) as cache:
                if str(cache['signature']) == self.signature and list(cache['ids']) == [c['id'] for c in self.chunks]:
                    self.dense = cache['vectors']

    def create_embeddings(self, batch_size=8):
        partial = self.directory / 'embeddings.partial.npz'
        vectors = []
        if partial.exists():
            with np.load(partial, allow_pickle=False) as cache:
                if str(cache['signature']) == self.signature:
                    vectors = list(cache['vectors'])
        for start in range(len(vectors), len(self.chunks), batch_size):
            batch = self.chunks[start:start + batch_size]
            vectors.extend(embed([c['text'] for c in batch]))
            np.savez_compressed(partial, vectors=np.array(vectors), signature=self.signature)
            print(f'Embedding: {len(vectors)}/{len(self.chunks)}', flush=True)
        target = self.directory / 'embeddings.npz'
        np.savez_compressed(target, vectors=np.array(vectors), ids=[c['id'] for c in self.chunks], signature=self.signature)
        self.load_embeddings()
        partial.unlink(missing_ok=True)

    def source_text(self, index: int) -> tuple[str, list[str]]:
        """Keep a paragraph's continuation when a word window splits it.

        Evidence stays on the cited PDF page, and the original vector index
        remains valid because stored chunks themselves are not modified.
        """
        chunk = self.chunks[index]
        words = chunk['text'].split()
        ids = [chunk['id']]
        if index + 1 < len(self.chunks):
            following = self.chunks[index + 1]
            if following['pdf_page'] == chunk['pdf_page']:
                more = following['text'].split()
                overlap = next((n for n in range(min(len(words), len(more)), 0, -1) if words[-n:] == more[:n]), 0)
                words.extend(more[overlap:])
                ids.append(following['id'])
        return ' '.join(words), ids

    def search(self, question: str, mode='graph', chapter: int | None = None, limit=6) -> dict:
        canonical_question, concepts = prepare_query(question)
        query_tokens = tokens(canonical_question)
        warnings = []
        expanded = canonical_question + ' ' + ' '.join(VOCABULARY[c][0] for c in concepts)
        lexical = (self.matrix @ self.vectorizer.transform([expanded]).T).toarray().ravel()
        bm25 = np.zeros(len(self.chunks))
        for term in set(query_tokens):
            idf = math.log(1 + (len(self.chunks) - self.df[term] + 0.5) / (self.df[term] + 0.5))
            for i, counts in enumerate(self.counts):
                tf = counts[term]
                if tf:
                    bm25[i] += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * self.lengths[i] / self.avg_length))
        if bm25.max() > 0:
            bm25 /= bm25.max()
        base = 0.55 * lexical + 0.45 * bm25
        if concepts:
            weights = {key: math.log(1 + len(self.chunks) / (1 + len(self.concept_chunks.get(key, [])))) for key in concepts}
            total = sum(weights.values())
            base += np.array([0.35 * sum(weights[key] for key in concepts if key in c['concepts']) / total for c in self.chunks])
        backend = 'TF-IDF + BM25'
        similarity = None
        if self.dense is not None:
            try:
                similarity = (self.dense @ embed([question], query=True)[0]).clip(0, 1)
                base = 0.45 * base + 0.55 * similarity
                backend = f'{config.EMBED_MODEL} + BM25 + TF-IDF'
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                warnings.append('Không kết nối được embedding Ollama; đang dùng TF-IDF + BM25.')
        scope_allowed = np.array([chapter is None or c['chapter'] == chapter for c in self.chunks])
        allowed = scope_allowed.copy()
        if concepts:
            concept_set = set(concepts)
            allowed &= np.array([bool(concept_set.intersection(c['concepts'])) for c in self.chunks])
        base[~scope_allowed] = 0
        # Entity linking is a retrieval aid, not a prerequisite for answering.
        # Permit strong semantic evidence for paraphrases with little lexical
        # overlap, while still requiring overlap on multiple content terms.
        meaningful_matches = [t for t in set(query_tokens) if self.df[t] and self.df[t] < len(self.chunks) * 0.6]
        lexical_evidence = meaningful_matches and float(lexical[scope_allowed].max(initial=0)) >= 0.20
        semantic_evidence = False
        if similarity is not None:
            semantic_evidence = any(
                scope_allowed[i] and similarity[i] >= 0.38 and lexical[i] >= 0.04
                and len(set(meaningful_matches).intersection(self.counts[i])) >= 2
                for i in np.argsort(-similarity)[:5]
            )
        if not concepts and not lexical_evidence and not semantic_evidence:
            return {'sources': [], 'concepts': [], 'backend': backend, 'warnings': warnings, 'graph_added': 0}
        order = [int(i) for i in np.argsort(-base) if allowed[i] and base[i] > 0.025]
        if not order:
            return {'sources': [], 'concepts': concepts, 'backend': backend, 'warnings': warnings, 'graph_added': 0}
        seeds = order[:max(3, limit // 2)]
        scores = base.copy()
        reasons = {}
        if mode == 'graph':
            # Query entities first; then rare entities from seed chunks. Generic
            # concepts such as testing must not connect the entire textbook.
            links = Counter({c: 2.0 for c in concepts})
            for edge in self.data['edges']:
                if edge['relation'] != 'co_occurs':
                    if edge['source'] in concepts:
                        links[edge['target']] += 0.8
                    if edge['target'] in concepts:
                        links[edge['source']] += 0.6
            for seed in seeds:
                for concept in self.chunks[seed]['concepts']:
                    freq = len(self.concept_chunks.get(concept, []))
                    if freq / len(self.chunks) < 0.18:
                        links[concept] += 0.6 / math.log2(freq + 2)
            bonus = defaultdict(float)
            for concept, weight in links.most_common(8):
                for i in self.concept_chunks.get(concept, []):
                    if scope_allowed[i]:
                        bonus[i] += weight
                        reasons.setdefault(i, []).append(concept)
            maximum = max(bonus.values(), default=1)
            for i, value in bonus.items():
                # Keep graph expansion tied to some lexical relevance.
                if base[i] > 0.04:
                    scores[i] += 0.18 * value / maximum
                    allowed[i] = True
            order = [int(i) for i in np.argsort(-scores) if allowed[i] and scores[i] > 0.025]
        selected = []
        pages = Counter()
        baseline_allowed = scope_allowed.copy()
        if concepts:
            baseline_allowed &= np.array([bool(set(concepts).intersection(c['concepts'])) for c in self.chunks])
        baseline_top = set()
        baseline_pages = set()
        for i in np.argsort(-base):
            if baseline_allowed[i] and base[i] > 0.025 and self.chunks[i]['pdf_page'] not in baseline_pages:
                baseline_top.add(int(i))
                baseline_pages.add(self.chunks[i]['pdf_page'])
                if len(baseline_top) >= limit:
                    break
        for i in order:
            chunk = self.chunks[i]
            if pages[chunk['pdf_page']] >= 1:
                continue
            selected.append(i)
            pages[chunk['pdf_page']] += 1
            if len(selected) >= limit:
                break
        sources = []
        for rank, i in enumerate(selected, 1):
            chunk = self.chunks[i]
            via = reasons.get(i, []) if mode == 'graph' else []
            text, context_chunk_ids = self.source_text(i)
            sources.append({
                **chunk, 'text': text, 'context_chunk_ids': context_chunk_ids,
                'citation': rank, 'score': round(float(scores[i]), 4),
                'via': [VOCABULARY[c][0] for c in via[:3]],
                'graph_expanded': mode == 'graph' and i not in baseline_top and bool(via),
                'url': f'/api/document#page={chunk["pdf_page"]}',
            })
        return {'sources': sources, 'concepts': concepts, 'backend': backend, 'warnings': warnings,
                'graph_added': sum(s['graph_expanded'] for s in sources)}

    def graph(self, concept=None, chapter=None, limit=28):
        allowed_ids = {c['id'] for c in self.chunks if chapter is None or c['chapter'] == chapter}
        nodes = []
        for n in self.data['nodes']:
            ids = [cid for cid in n['chunk_ids'] if cid in allowed_ids]
            if ids:
                nodes.append({**n, 'chunk_ids': ids, 'mentions': len(ids)})
        edges = [{**e, 'evidence': [cid for cid in e['evidence'] if cid in allowed_ids]} for e in self.data['edges']]
        edges = [e for e in edges if e['evidence']]
        if concept:
            edges = [e for e in edges if concept in (e['source'], e['target'])]
            neighbors = {concept} | {e['source'] for e in edges} | {e['target'] for e in edges}
            nodes = [n for n in nodes if n['id'] in neighbors]
        nodes.sort(key=lambda n: (n['id'] != concept, -n['mentions']))
        nodes = nodes[:limit]
        keep = {n['id'] for n in nodes}
        edges = [e for e in edges if e['source'] in keep and e['target'] in keep]
        edges.sort(key=lambda e: (e['relation'] == 'co_occurs', -len(e['evidence'])))
        for e in edges:
            e['weight'] = len(e['evidence'])
            e['pages'] = sorted({self.chunks[self.by_id[cid]]['pdf_page'] for cid in e['evidence']})[:8]
        for n in nodes:
            n['pages'] = sorted({self.chunks[self.by_id[cid]]['pdf_page'] for cid in n.pop('chunk_ids')})[:12]
        return {'nodes': nodes, 'edges': edges[:65], 'note': self.data['metadata']['graph_note']}
