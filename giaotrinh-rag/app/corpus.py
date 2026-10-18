import hashlib
import json
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from pypdf import PdfReader

from .concepts import VOCABULARY, detect

SCHEMA_VERSION = 4

# Seed relations checked against this textbook. Each rule also requires an
# exact normalized evidence phrase and both endpoint mentions in the chunk.
# No arbitrary co-occurrence is promoted to a factual relation.
RELATION_RULES = [
    ('static-testing', 'testing', 'is_a', 'Là một loại', 'Có hai kiểu : Kiểm thử không có sự thực thi và kiểm thử có dựa trên sự thực thi'),
    ('dynamic-testing', 'testing', 'is_a', 'Là một loại', 'Có hai kiểu : Kiểm thử không có sự thực thi và kiểm thử có dựa trên sự thực thi'),
    ('design', 'architecture', 'includes', 'Bao gồm', 'Các hoạt động thiết kế cổ điển'),
    ('design', 'detailed-design', 'includes', 'Bao gồm', 'Các hoạt động thiết kế cổ điển'),
    ('scenario', 'use-case', 'instance_of', 'Là thể hiện của', 'các kịch bản là những thể hiện cụ thể của các Use-Case'),
    ('use-case', 'actor', 'describes_interaction', 'Mô tả tương tác với', 'Use-Case miêu tả tương tác giữa hệ thống và các tác nhân'),
    ('walkthrough', 'static-testing', 'is_a', 'Là một loại', '4.3.1.1 Rà soát lướt qua'),
]


def extract_pages(path: Path) -> list[str]:
    if shutil.which('pdftotext'):
        output = subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True, check=True).stdout.decode('utf-8')
        pages = output.split('\f')
        if not pages[-1].strip():
            pages.pop()
        return pages
    return [page.extract_text(extraction_mode='layout') or '' for page in PdfReader(path).pages]


def clean_page(text: str) -> tuple[str, int | None]:
    lines = text.splitlines()
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    printed = None
    if nonempty and re.fullmatch(r'\d{1,4}', lines[nonempty[-1]].strip()):
        printed = int(lines[nonempty[-1]].strip())
        lines[nonempty[-1]] = ''
    # Drop running headers, but retain the actual uppercase chapter heading.
    for i in nonempty[:2]:
        if re.match(r'\s*Chương\s+\d+', lines[i]) or lines[i].strip() == 'Giới thiệu':
            lines[i] = ''
    value = '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in lines)
    return re.sub(r'\n{3,}', '\n\n', value).strip(), printed


def split_chunks(text: str, size: int = 210, overlap: int = 40) -> list[str]:
    words = text.split()
    result = []
    for start in range(0, len(words), size - overlap):
        part = ' '.join(words[start:start + size])
        if len(part) > 65:
            result.append(part)
        if start + size >= len(words):
            break
    return result


def build_corpus(pdf: Path, directory: Path) -> dict:
    pages = extract_pages(pdf)
    chapters, chunks, page_records = [], [], []
    current = None
    section = ''
    in_review = False
    for page_number, raw in enumerate(pages, 1):
        text, printed = clean_page(raw)
        # The actual body starts with chapter 1; never index the TOC as evidence.
        heading = re.search(r'^CHƯƠNG\s+(\d+)\s*[:.]?\s*([^\n]*)', text, re.M)
        if heading and '...' not in heading.group(0):
            number = int(heading.group(1))
            title = heading.group(2).strip()
            if not title:
                after = text[heading.end():].strip().splitlines()
                title = after[0].strip() if after else f'Chương {number}'
            if not current or number != current['number']:
                if current:
                    current['end_page'] = page_number - 1
                current = {'number': number, 'title': title.capitalize(), 'start_page': page_number, 'end_page': len(pages), 'chunks': 0}
                chapters.append(current)
                section = ''
                in_review = False
        page_records.append({'pdf_page': page_number, 'printed_page': printed, 'characters': len(text)})
        if not current or len(text) < 70:
            continue
        if in_review:
            continue
        headings = re.findall(r'^\s*(\d+\.\d+(?:\.\d+)*\.?\s+[^\n]+)', text, re.M)
        if headings:
            section = headings[0].strip()
        # Review questions are useful for evaluation, but are not answers.
        parts = re.split(r'(?m)^\s*\d+\.\d+\.?\s+CÂU HỎI ÔN TẬP', text, maxsplit=1)
        evidence_text = parts[0]
        in_review = len(parts) > 1
        for position, part in enumerate(split_chunks(evidence_text)):
            item = {
                'id': f'p{page_number:03d}-{position}', 'text': part,
                'pdf_page': page_number, 'printed_page': printed,
                'chapter': current['number'], 'chapter_title': current['title'],
                'section': section, 'concepts': detect(part),
            }
            chunks.append(item)
            current['chunks'] += 1
    if not chunks:
        raise ValueError('Không trích xuất được nội dung. PDF cần có văn bản hoặc được OCR trước.')

    mentions = defaultdict(list)
    pairs = defaultdict(list)
    for chunk in chunks:
        for concept in chunk['concepts']:
            mentions[concept].append(chunk['id'])
        for left, right in combinations(sorted(chunk['concepts']), 2):
            pairs[(left, right)].append(chunk['id'])
    nodes = [{'id': key, 'label': VOCABULARY[key][0], 'kind': 'concept', 'mentions': len(ids), 'chunk_ids': ids} for key, ids in mentions.items()]
    edges = [{'source': a, 'target': b, 'relation': 'co_occurs', 'label': 'Cùng xuất hiện', 'weight': len(ids), 'evidence': ids} for (a, b), ids in pairs.items()]
    from .concepts import normalize
    for source, target, relation, label, phrase in RELATION_RULES:
        evidence = [c['id'] for c in chunks if source in c['concepts'] and target in c['concepts'] and normalize(phrase) in normalize(c['text'])]
        if evidence:
            edges.append({'source': source, 'target': target, 'relation': relation, 'label': label,
                          'weight': len(evidence), 'evidence': evidence, 'evidence_phrase': phrase})
    metadata = {
        'schema_version': SCHEMA_VERSION, 'document': pdf.name,
        'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'pages': len(pages), 'chunks': len(chunks), 'chapters': chapters,
        'concepts': len(nodes), 'edges': len(edges),
        'semantic_edges': sum(e['relation'] != 'co_occurs' for e in edges),
        'short_pages': [p['pdf_page'] for p in page_records if p['characters'] < 100],
        'graph_note': 'Cạnh co_occurs biểu thị cùng xuất hiện. Các cạnh có kiểu ngữ nghĩa được đối chiếu với trích đoạn và cụm từ bằng chứng trong giáo trình.',
    }
    directory.mkdir(parents=True, exist_ok=True)
    payload = {'metadata': metadata, 'chunks': chunks, 'nodes': nodes, 'edges': edges, 'pages': page_records}
    temp = directory / 'corpus.tmp'
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    temp.replace(directory / 'corpus.json')
    return payload
