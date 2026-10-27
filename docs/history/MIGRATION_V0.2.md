> Исторический документ. Актуальное устройство проекта: [архитектура](../ARCHITECTURE.md), [инструкции](../README.md).

# Обновление с v0.1 до v0.2

## 1. Остановить приложение

Не обновляйте файлы, пока запущены `digital-child chat` или API-сервер.

## 2. Сохранить базу

```bash
cp data/digital_child.db data/digital_child.before-v0.2.db 2>/dev/null || true
```

## 3. Заменить исходники

При копировании нового репозитория не удаляйте:

- `.git/`;
- `.venv/` можно пересоздать;
- `data/*.db*` — это личная память агента.

Пример:

```bash
rsync -av --delete \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='data/*.db' \
  --exclude='data/*.db-shm' \
  --exclude='data/*.db-wal' \
  /путь/к/digital-child-v0.2/ ./
```

## 4. Обновить окружение

```bash
rm -rf .venv
uv python pin 3.12
uv sync --extra dev
uv run pytest
```

## 5. Запустить

```bash
uv run digital-child chat
```

SQLite-схема обновляется автоматически: к старой таблице эпизодов добавляются новые
столбцы, а старые записи сохраняются. Старые эпизоды не имеют готовой нормализованной
формы; при чтении используется их исходный текст.
