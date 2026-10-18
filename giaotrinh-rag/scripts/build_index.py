import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config
from app.corpus import build_corpus
from app.retrieval import Engine

parser = argparse.ArgumentParser(description='Lập chỉ mục giáo trình và tạo embedding qua Ollama.')
parser.add_argument('--embeddings', action='store_true', help='Tạo dense embedding (cần Ollama + EMBED_MODEL).')
parser.add_argument('--rebuild', action='store_true', help='Trích xuất lại PDF.')
args = parser.parse_args()
if args.rebuild:
    build_corpus(config.PDF_PATH, config.INDEX_DIR)
engine = Engine()
print(json.dumps({k: v for k, v in engine.data['metadata'].items() if k != 'chapters'}, ensure_ascii=False, indent=2))
if args.embeddings:
    engine.create_embeddings()
    print('Đã lưu dense embedding. Khởi động lại FastAPI nếu đang chạy.')
