#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-qwen3.5:9b}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v ollama >/dev/null 2>&1; then
  cat <<'EOF'
Команда ollama не найдена.
Установите актуальное приложение Ollama для macOS, запустите его и повторите команду.
После установки CLI должен быть доступен как `ollama`.
EOF
  exit 1
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Локальный сервер Ollama не отвечает. Запускаю ollama serve..."
  nohup ollama serve > /tmp/digital-child-ollama.log 2>&1 &
  for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama не запустилась. Проверьте /tmp/digital-child-ollama.log"
  exit 1
fi

echo "Загружаю модель: $MODEL"
ollama pull "$MODEL"

cat > .env <<EOF
DIGITAL_CHILD_LLM_PROVIDER=ollama
DIGITAL_CHILD_LLM_BASE_URL=http://127.0.0.1:11434/v1
DIGITAL_CHILD_LLM_MODEL=$MODEL
DIGITAL_CHILD_LLM_API_KEY=local-no-key
DIGITAL_CHILD_LLM_TIMEOUT=180
DIGITAL_CHILD_LLM_TEMPERATURE=0.55
DIGITAL_CHILD_LLM_MAX_TOKENS=1200

DIGITAL_CHILD_RESEARCH_PROVIDER=wikipedia
DIGITAL_CHILD_AUTO_RESEARCH=1
DIGITAL_CHILD_WIKIPEDIA_LANGUAGE=ru
DIGITAL_CHILD_OPERATOR_TOKEN=change-me
DIGITAL_CHILD_DB=data/digital_child.db
EOF

echo
uv run digital-child llm
cat <<'EOF'

Настройка завершена.
Запуск: uv run digital-child chat
EOF
