> Исторический документ. Актуальное устройство проекта: [архитектура](../ARCHITECTURE.md), [инструкции](../README.md).

# Миграция v0.2.5 → v0.3.0

База данных обновляется автоматически: добавляется таблица `conversation_messages`.
Старые эпизоды, убеждения, отношения, цели и событие пробуждения сохраняются.

Перед обновлением:

```bash
cp data/digital_child.db data/digital_child.before-v0.3.db 2>/dev/null || true
```

После замены файлов:

```bash
rm -rf .venv
uv sync --extra dev
uv run pytest
```

Настройте `.env`:

```bash
cp .env.example .env
```

Или запустите автоматический сценарий:

```bash
./scripts/setup_ollama_macos.sh
```
