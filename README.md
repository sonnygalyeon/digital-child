# Digital Child v0.3.0

Долгоживущий цифровой агент с развивающейся личностью, доказательной памятью,
автономными решениями и полноценной локальной LLM.

## Что нового

- потоковая генерация ответа через OpenAI-compatible API;
- Ollama, llama.cpp, LM Studio и удалённые совместимые endpoints;
- постоянная история диалога в SQLite;
- контекст личности, целей, доверия, убеждений и памяти;
- автономное решение принимается до обращения к LLM;
- LLM не может превратить пользователя в начальника;
- ответы модели не становятся автоматически доказанными знаниями;
- терминальное лицо говорит во время поступления токенов и продолжает idle-анимацию;
- `/llm` и отдельная команда `digital-child llm` для диагностики;
- автоматическая миграция базы v0.2.5.

## Установка

```bash
uv python pin 3.12
uv sync --extra dev
uv run pytest
```

## Подключение Ollama на Mac

После установки приложения Ollama:

```bash
./scripts/setup_ollama_macos.sh
```

Или вручную:

```bash
ollama pull qwen3.5:9b
cp .env.example .env
uv run digital-child llm
```

## Запуск

```bash
uv run digital-child chat
```

Без динамического лица:

```bash
uv run digital-child chat --no-face
```

Проверка LLM:

```bash
uv run digital-child llm
```

## Архитектурная граница

```text
пользовательское сообщение
        ↓
классификация намерения
        ↓
доверие + цели + конституция
        ↓
автономное решение
        ↓
проверка факта при необходимости
        ↓
контекст личной истории
        ↓
LLM формулирует ответ
        ↓
ответ и метаданные сохраняются
```

LLM является языковым и рассуждающим процессором. Она не является всей личностью.

## Команды

```text
/help
/state
/llm
/history [N]
/identity
/goals [N]
/trust
/beliefs [N]
/research <утверждение>
/reports [N]
/decisions [N]
/memory [N]
/summaries [N]
/consolidate
/rest [0..1]
/operator reset
/quit
```

Подробная настройка: [`docs/LLM_SETUP_MACOS.md`](docs/LLM_SETUP_MACOS.md).
