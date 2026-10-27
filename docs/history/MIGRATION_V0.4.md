> Исторический документ. Актуальное устройство проекта: [архитектура](../ARCHITECTURE.md), [инструкции](../README.md).

# Миграция на v0.4.0

## 1. Резервная копия

```bash
cp data/digital_child.db data/digital_child.before-v0.4.db
```

## 2. Замена файлов

Не удаляй `.git`, `.venv` и файлы `data/*.db` при копировании новой версии.

## 3. Окружение

```bash
rm -rf .venv
uv python pin 3.12
uv sync --extra dev --extra desktop
```

## 4. Конфигурация

Сравни текущий `.env` с `.env.example`. Минимально добавь:

```env
DIGITAL_CHILD_LLM_REASONING_EFFORT=none
DIGITAL_CHILD_LLM_MAX_TOKENS=512
DIGITAL_CHILD_LLM_HISTORY_MESSAGES=6
DIGITAL_CHILD_LLM_MEMORY_ITEMS=4
DIGITAL_CHILD_LLM_BELIEF_ITEMS=4
DIGITAL_CHILD_LLM_PROMPT_MAX_CHARS=7000
DIGITAL_CHILD_RESEARCH_MODE=background
```

Для Windows-хоста рекомендуется заново запустить:

```powershell
.\scripts\windows\setup_windows_host.ps1
```

Сценарий создаст новую модель `digital-child-fast` и обновит `windows_host\.env`.
Существующий API-ключ сохраняется. Новый ключ создаётся только с `-RegenerateApiKey`.

## 5. Проверка

```bash
uv run pytest
uv run digital-child llm
uv run digital-child face
uv run digital-child chat
```

Схема основной SQLite-базы не требует разрушительной миграции.
