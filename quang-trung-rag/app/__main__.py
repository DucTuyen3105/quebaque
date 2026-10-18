import uvicorn
from .config import PORT

print(f'Mở http://127.0.0.1:{PORT} · Tài liệu API: /docs', flush=True)
uvicorn.run('app.main:app', host='127.0.0.1', port=PORT)
