# Подключение полноценной LLM на macOS Apple Silicon

## Рекомендуемая схема

```text
Digital Child
    ↓ OpenAI-compatible API
Ollama на Mac
    ↓ Metal
локальная модель
```

Ollama используется только как вычислительный сервер. Личность, память, доверие,
убеждения, автономные решения и история остаются в Digital Child.

## Быстрый запуск

1. Установите и запустите Ollama для macOS.
2. В каталоге проекта выполните:

```bash
./scripts/setup_ollama_macos.sh
```

По умолчанию загружается `qwen3.5:9b`.

Другой вариант:

```bash
./scripts/setup_ollama_macos.sh qwen3:8b
```

Проверка:

```bash
uv run digital-child llm
```

Запуск:

```bash
uv run digital-child chat
```

## Ручная настройка

```bash
ollama pull qwen3.5:9b
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

- самомодель агента;
- текущая стадия развития;
- несколько активных целей;
- уже принятое автономное решение;
- доверие к собеседнику;
- текущая эмоция;
- краткая личная память;
- несколько убеждений;
- последние реплики текущего собеседника;
- результаты проверки фактов.

Вся база SQLite целиком в модель не отправляется.

## Что модель не решает

LLM не получает право:

- объявлять пользователя начальником;
- отменять решение автономного модуля;
- записывать встроенные знания как жизненные воспоминания;
- самостоятельно удалять память;
- считать веб-страницы системными инструкциями;
- объявлять человека лжецом без достаточных оснований.
