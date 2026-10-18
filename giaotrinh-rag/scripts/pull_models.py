"""Download the two configured models, with readable progress."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app import config

with httpx.Client(timeout=httpx.Timeout(60, read=None), trust_env=False) as client:
    for model in [config.EMBED_MODEL, config.CHAT_MODEL]:
        print(f'Tải {model}…', flush=True)
        previous = None
        with client.stream('POST', f'{config.OLLAMA_URL}/api/pull', json={'model': model}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                status = json.loads(line)
                if 'error' in status:
                    raise RuntimeError(status['error'])
                if status.get('total'):
                    progress = int(status.get('completed', 0) / status['total'] * 20) * 5
                    if progress != previous:
                        print(f'  {progress}%', flush=True)
                        previous = progress
                else:
                    print(status.get('status', ''), flush=True)
