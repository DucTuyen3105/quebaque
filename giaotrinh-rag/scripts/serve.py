"""Start local Ollama if needed, then FastAPI; stop only owned children."""
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app import config

children = []
log = None


def ollama_ready():
    try:
        with httpx.Client(timeout=1, trust_env=False) as client:
            response = client.get(f'{config.OLLAMA_URL}/api/tags')
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def stop(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
try:
    if not ollama_ready():
        print('Đang khởi động Ollama cục bộ…', flush=True)
        (config.ROOT / 'data').mkdir(exist_ok=True)
        log = (config.ROOT / 'data' / 'ollama.log').open('a', encoding='utf-8')
        process = subprocess.Popen([str(config.ROOT / 'run_ollama.sh')], cwd=config.ROOT, stdout=log, stderr=log, start_new_session=True)
        children.append(process)
        deadline = time.monotonic() + 30
        while not ollama_ready():
            if process.poll() is not None or time.monotonic() > deadline:
                print('Ollama chưa khởi động được. Xem data/ollama.log; web vẫn cho phép tra cứu nguồn.', flush=True)
                break
            time.sleep(0.3)
    else:
        print('Đang sử dụng Ollama đã chạy.', flush=True)
    web = subprocess.Popen([sys.executable, '-m', 'app'], cwd=config.ROOT, start_new_session=True)
    children.append(web)
    code = web.wait()
except KeyboardInterrupt:
    code = 0
    print('\nĐang dừng các dịch vụ do dự án khởi động…', flush=True)
finally:
    for process in reversed(children):
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    if log:
        log.close()
sys.exit(code)
