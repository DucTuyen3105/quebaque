import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.retrieval import Engine

parser = argparse.ArgumentParser(description='Lập chỉ mục ghi chép lịch sử và graph có nguồn.')
parser.add_argument('--embeddings', action='store_true')
args = parser.parse_args()
engine = Engine()
print(json.dumps(engine.data['stats'], ensure_ascii=False, indent=2))
if args.embeddings:
    engine.create_embeddings()
    print('Đã lưu embedding. Khởi động lại web để nạp chỉ mục.')
