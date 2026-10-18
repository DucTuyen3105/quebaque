import os

import uvicorn

from . import config

port = int(os.getenv('PORT', '8000'))
print(f'Mở http://127.0.0.1:{port} · Tài liệu API: /docs', flush=True)
uvicorn.run('app.main:app', host='127.0.0.1', port=port)
