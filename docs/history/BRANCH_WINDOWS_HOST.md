> Исторический документ. Актуальное устройство проекта: [архитектура](../ARCHITECTURE.md), [инструкции](../README.md).

# Windows host branch

Версия v0.4.0 объединяет клиент и Windows-host в одном архиве. Для Git по-прежнему
можно держать отдельную ветку:

```bash
git checkout -b windows-llm-host-v0.4
```

Главные изменения хоста:

- `digital-child-fast` на основе Qwen3 4B Instruct;
- контекст 4096;
- reasoning `none`;
- прогрев модели;
- ограничение output tokens;
- измерение времени до первого токена;
- исправлен безопасный PostgreSQL-аудит;
- добавлен benchmark PowerShell.
