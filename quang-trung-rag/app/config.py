import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DATASET_PATH = ROOT / 'data' / 'history.json'
INDEX_DIR = ROOT / 'data' / 'index'
PORT = int(os.getenv('PORT', '8010'))
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11435').rstrip('/')
CHAT_MODEL = os.getenv('CHAT_MODEL', 'qwen3:1.7b')
EMBED_MODEL = os.getenv('EMBED_MODEL', 'embeddinggemma')
OLLAMA_TIMEOUT = float(os.getenv('OLLAMA_TIMEOUT', '180'))
CONTEXT_CHUNKS = max(1, min(6, int(os.getenv('CONTEXT_CHUNKS', '4'))))
