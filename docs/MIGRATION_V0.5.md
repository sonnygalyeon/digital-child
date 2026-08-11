# Миграция v0.4.1 → v0.5.0

## 1. Резервная копия

```bash
cd ~/digital-child
cp data/digital_child.db data/digital_child.before-v0.5.db 2>/dev/null || true
cp .env /tmp/digital-child-v050.env 2>/dev/null || true
```

## 2. Создание ветки

```bash
git add .
git commit -m "chore: save v0.4.1 before cognitive loop"
git checkout -b autonomous-cognitive-loop-v0.5.0
```

## 3. Замена файлов

```bash
rsync -av --delete \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.env' \
  --exclude='data/*.db' \
  --exclude='data/*.db-shm' \
  --exclude='data/*.db-wal' \
  ~/Downloads/digital-child-v0.5.0/ ./
```

Если `.env` был утрачен:

```bash
test -f /tmp/digital-child-v050.env && cp /tmp/digital-child-v050.env .env
```

## 4. Окружение и тесты

```bash
uv sync --extra dev --extra desktop
uv run pytest
```

Ожидается:

```text
44 passed
```

## 5. Первый запуск

```bash
uv run digital-child chat
```

Проверь:

```text
/diagnostics
/background
/needs
/goals
```

Новые таблицы создаются автоматически. Ручная конвертация SQLite не требуется.
