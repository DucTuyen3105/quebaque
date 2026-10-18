#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
if [[ ! -f .env ]]; then cp .env.example .env; fi
if [[ ! -f data/index/corpus.json ]]; then .venv/bin/python scripts/build_index.py; fi
exec .venv/bin/python -m app
