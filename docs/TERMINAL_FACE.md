# Терминальное лицо — устаревший режим

Файлы старого Unicode/curses-лица сохранены только для совместимости тестов и
истории проекта. В v0.4.0 оно не запускается обычной командой `chat`.

Основной интерфейс:

```bash
uv sync --extra desktop
uv run digital-child chat
```

Отдельное лицо работает в PySide6-окне. Для запуска без него:

```bash
uv run digital-child chat --no-face-window
```
