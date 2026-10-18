"""Small retrieval smoke benchmark; not an academic effectiveness claim."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config
from app.retrieval import Engine

parser = argparse.ArgumentParser()
parser.add_argument('--lexical-only', action='store_true', help='Không gọi Ollama embedding.')
args = parser.parse_args()
engine = Engine()
if args.lexical_only:
    engine.dense = None
cases = json.loads((config.ROOT / 'data' / 'evaluation.json').read_text(encoding='utf-8'))
report = {'note': 'Bộ kiểm tra nhỏ do dự án biên soạn; trang bằng chứng chưa phải nhãn đầy đủ. Không đo chất lượng câu trả lời LLM.', 'dense_enabled': engine.dense is not None, 'cases': len(cases), 'results': {}}
for mode in ['baseline', 'graph']:
    rows = []
    for case in cases:
        start = time.perf_counter()
        result = engine.search(case['question'], mode=mode, limit=5)
        pages = [s['pdf_page'] for s in result['sources']]
        expected = set(case['evidence_pages'])
        rows.append({**case, 'retrieved_pages': pages, 'hit_at_5': bool(expected.intersection(pages)) if expected else None,
                     'reference_page_coverage': len(expected.intersection(pages)) / len(expected) if expected else None,
                     'correct_abstention': not pages if not expected else None,
                     'elapsed_ms': round((time.perf_counter() - start) * 1000), 'backend': result['backend'], 'warnings': result['warnings']})
    in_scope = [r for r in rows if r['evidence_pages']]
    out_scope = [r for r in rows if not r['evidence_pages']]
    report['results'][mode] = {
        'hit_at_5': round(sum(r['hit_at_5'] for r in in_scope) / len(in_scope), 3),
        'reference_page_coverage': round(sum(r['reference_page_coverage'] for r in in_scope) / len(in_scope), 3),
        'correct_abstention': round(sum(r['correct_abstention'] for r in out_scope) / len(out_scope), 3),
        'mean_latency_ms': round(sum(r['elapsed_ms'] for r in rows) / len(rows)), 'details': rows,
    }
name = 'evaluation-lexical.json' if args.lexical_only else 'evaluation-report.json'
(config.ROOT / 'data' / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({mode: {k: v for k, v in metrics.items() if k != 'details'} for mode, metrics in report['results'].items()}, ensure_ascii=False, indent=2))
