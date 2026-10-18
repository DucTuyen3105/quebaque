import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
PDF_PATH = (ROOT / os.getenv('PDF_PATH', '../Nhập môn công nghệ phần mềm.pdf')).resolve()
INDEX_DIR = ROOT / 'data' / 'index'
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
CHAT_MODEL = os.getenv('CHAT_MODEL', 'qwen3:1.7b')
EMBED_MODEL = os.getenv('EMBED_MODEL', 'embeddinggemma')
OLLAMA_TIMEOUT = float(os.getenv('OLLAMA_TIMEOUT', '180'))
CONTEXT_CHUNKS = max(1, min(8, int(os.getenv('CONTEXT_CHUNKS', '5'))))
