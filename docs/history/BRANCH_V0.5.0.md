> Исторический документ. Актуальное устройство проекта: [архитектура](../ARCHITECTURE.md), [инструкции](../README.md).

# Ветка v0.5.0

Рекомендуемое имя:

```text
autonomous-cognitive-loop-v0.5.0
```

Создание ветки из текущей рабочей версии:

```bash
cd ~/digital-child
git checkout interface-performance-v0.4
git pull
git checkout -b autonomous-cognitive-loop-v0.5.0
```

После переноса файлов и тестов:

```bash
git add .
git commit -m "feat: add event-driven needs and bounded autonomous cognitive loop"
git push -u origin autonomous-cognitive-loop-v0.5.0
```

Полный архив содержит весь проект. Файл `digital-child-v0.5.0.patch` содержит разницу относительно v0.4.1 и может быть применён командой:

```bash
git apply --check digital-child-v0.5.0.patch
git apply digital-child-v0.5.0.patch
```
