import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations
from urllib.parse import urlparse

from . import config


def load_dataset():
    data = json.loads(config.DATASET_PATH.read_text(encoding='utf-8'))
    sources = {s['id']: s for s in data['sources']}
    entities = {e['id']: e for e in data['entities']}
    records = {r['id']: r for r in data['records']}
    categories = {c['id']: c['title'] for c in data['categories']}
    if len(sources) != len(data['sources']) or len(records) != len(data['records']) or len(entities) != len(data['entities']):
        raise ValueError('ID tài liệu, ghi chép và thực thể phải duy nhất.')
    for source in sources.values():
        if urlparse(source['url']).scheme != 'https':
            raise ValueError('Nguồn tài liệu cần có URL HTTPS.')
    for record in records.values():
        if record['source_id'] not in sources or record['category'] not in categories or not record['text'].strip():
            raise ValueError(f'Ghi chép không hợp lệ: {record["id"]}')
        if not set(record['entities']).issubset(entities):
            raise ValueError(f'Thực thể chưa định nghĩa: {record["id"]}')
    for edge in data['relations']:
        if edge['source'] not in entities or edge['target'] not in entities or not edge['evidence']:
            raise ValueError('Quan hệ cần có hai thực thể và bằng chứng.')
        for rid in edge['evidence']:
            if rid not in records or not {edge['source'], edge['target']}.issubset(records[rid]['entities']):
                raise ValueError(f'Bằng chứng quan hệ không hợp lệ: {rid}')
    for event in data['timeline']:
        if not set(event['record_ids']).issubset(records):
            raise ValueError('Mốc thời gian thiếu ghi chép chứng minh.')
    return data


def build_index():
    data = load_dataset()
    mentions, pairs = defaultdict(list), defaultdict(list)
    for record in data['records']:
        for entity in record['entities']:
            mentions[entity].append(record['id'])
        for pair in combinations(sorted(record['entities']), 2):
            pairs[pair].append(record['id'])
    nodes = [{**entity, 'mentions': len(mentions[entity['id']]), 'record_ids': mentions[entity['id']]} for entity in data['entities'] if mentions[entity['id']]]
    edges = [{**edge, 'weight': len(edge['evidence'])} for edge in data['relations']]
    related = {(e['source'], e['target']) for e in edges} | {(e['target'], e['source']) for e in edges}
    edges.extend({'source': a, 'target': b, 'relation': 'co_occurs', 'label': 'Cùng được đề cập', 'evidence': ids, 'weight': len(ids)} for (a, b), ids in pairs.items() if (a, b) not in related)
    signature = hashlib.sha256(config.DATASET_PATH.read_bytes()).hexdigest()
    stats = {'title': data['title'], 'compiled_at': data['compiled_at'], 'records': len(data['records']),
             'sources': len(data['sources']), 'entities': len(nodes), 'relations': len(data['relations']),
             'timeline_events': len(data['timeline']), 'categories': data['categories'], 'sha256': signature,
             'dataset_note': data['description']}
    result = {**data, 'nodes': nodes, 'edges': edges, 'stats': stats}
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    temp = config.INDEX_DIR / 'corpus.tmp'
    temp.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    temp.replace(config.INDEX_DIR / 'corpus.json')
    # These readable documents belong entirely to this project.
    for source in data['sources']:
        notes = [r for r in data['records'] if r['source_id'] == source['id']]
        text = f'# {source["title"]}\n\nĐơn vị: {source["publisher"]}\n\nNguồn: {source["url"]}\n\nGhi chép diễn giải, không phải bản sao toàn văn.\n'
        for note in notes:
            text += f'\n## {note["title"]}\n\n{note["text"]}\n'
        (config.ROOT / 'data' / 'documents' / f'{source["id"]}.md').write_text(text, encoding='utf-8')
    return result
