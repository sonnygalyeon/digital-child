> Исторический документ. Актуальное устройство проекта: [архитектура](../ARCHITECTURE.md), [инструкции](../README.md).

# Миграция v0.2 → v0.2.5

## 1. Резервная копия

```bash
cd ~/digital-child
cp data/digital_child.db data/digital_child.before-v0.2.5.db
```

## 2. Замена файлов

Распакуй архив и скопируй его содержимое, не удаляя `.git`, `.venv` и `data/*.db`:

```bash
rsync -av --delete \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='data/*.db' \
  --exclude='data/*.db-shm' \
  --exclude='data/*.db-wal' \
  ~/Downloads/digital-child-v0.2.5/ ./
```

## 3. Окружение

```bash
rm -rf .venv
uv python pin 3.12
uv sync --extra dev
```

## 4. Проверка

```bash
uv run pytest
uv run python -m compileall -q src
```

Ожидается `29 passed`.

## 5. Первый запуск

```bash
uv run digital-child chat
```

Старая память сохраняется. Если в базе ещё нет личности, создаётся одно событие
первого пробуждения. Повторный запуск восстанавливает ту же личность.

## Откат

```bash
cp data/digital_child.before-v0.2.5.db data/digital_child.db
```
