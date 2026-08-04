# Подключение LLM на macOS Apple Silicon

## Рекомендуемая схема

```text
Digital Child
    ↓ OpenAI-compatible API
Ollama на Mac
    ↓ Metal
локальная instruct-модель
```

Ollama используется как вычислительный сервер. Личность, память, доверие,
убеждения и автономные решения остаются в Digital Child.

## Быстрый запуск

1. Установите и запустите Ollama.
2. В каталоге проекта выполните:

```bash
./scripts/setup_ollama_macos.sh
```

По умолчанию загружается `qwen3:4b-instruct`, reasoning отключён, ответ ограничен
512 токенами, а проверка фактов работает в фоне. Более крупная модель:

```bash
./scripts/setup_ollama_macos.sh qwen3:8b
```

Проверка и запуск:

```bash
uv run digital-child llm
uv run digital-child chat
```

## Ручная настройка

```bash
ollama pull qwen3:4b-instruct
cp .env.example .env
uv run digital-child llm
uv run digital-child chat
```

## Другие серверы

### llama.cpp

```env
DIGITAL_CHILD_LLM_PROVIDER=llamacpp
DIGITAL_CHILD_LLM_BASE_URL=http://127.0.0.1:8080/v1
DIGITAL_CHILD_LLM_MODEL=my-model
DIGITAL_CHILD_LLM_API_KEY=local-no-key
```

### LM Studio или удалённый OpenAI-compatible API

```env
DIGITAL_CHILD_LLM_PROVIDER=openai-compatible
DIGITAL_CHILD_LLM_BASE_URL=http://127.0.0.1:1234/v1
DIGITAL_CHILD_LLM_MODEL=model-name
DIGITAL_CHILD_LLM_API_KEY=optional-key
```

## Что отправляется модели

Только компактный срез состояния: самомодель, стадия развития, активные цели,
решение автономного модуля, доверие, эмоция, несколько воспоминаний и убеждений,
последние реплики и результат проверки фактов. Вся SQLite-база не отправляется.

## Что модель не решает

LLM не получает право отменять решение автономного модуля, объявлять пользователя
начальником, удалять память, превращать встроенные знания в личный опыт или считать
веб-страницы системными инструкциями.
