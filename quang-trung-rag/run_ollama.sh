#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -x .runtime/bin/ollama ]]; then
  history_ollama_binary="$PWD/.runtime/bin/ollama"
elif command -v ollama >/dev/null 2>&1; then
  history_ollama_binary="$(command -v ollama)"
else
  printf 'Chưa có Ollama. Xem README.md để cài đặt.\n' >&2
  exit 1
fi
export OLLAMA_MODELS="${OLLAMA_MODELS:-$PWD/.runtime/models}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11435}"
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_CONTEXT_LENGTH=8192
export OLLAMA_NO_CLOUD=true
exec "$history_ollama_binary" serve
