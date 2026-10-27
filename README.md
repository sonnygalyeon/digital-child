# Digital Child

Долгоживущий цифровой агент с постоянной личностью, памятью SQLite,
событийным когнитивным циклом и необязательной LLM. Психология и развитие
моделируются алгоритмами; веса языковой модели не обучаются.

## Запуск

Нужны Python 3.12–3.13 и uv.

```bash
uv sync --extra desktop --extra dev
cp .env.example .env
uv run digital-child desktop
```

Чтобы работать без LLM, задайте в `.env`:

```dotenv
DIGITAL_CHILD_LLM_PROVIDER=disabled
DIGITAL_CHILD_RESEARCH_PROVIDER=disabled
DIGITAL_CHILD_AUTO_RESEARCH=0
```

Другие интерфейсы:

```bash
uv run digital-child chat
uv run digital-child serve --host 127.0.0.1 --port 8000
```

Доступны прежние команды `python -m digital_child` и `digital-child-desktop`.
При выключенной или недоступной LLM используется ограниченный алгоритмический backend.

Desktop-extra устанавливает `PySide6-Essentials`: используемые компоненты Qt входят
в этот набор, а импорты `PySide6` сохраняются. Полный комплект Addons с WebEngine
приложению не требуется. Состав пакетов описан в
[документации Qt](https://doc.qt.io/qtforpython-6/package_details.html).
После обновления зависимостей выполните `uv sync --locked --extra desktop --extra dev`.

## Windows

Для установки из исходников скачайте [архив основной ветки](https://github.com/sonnygalyeon/digital-child/archive/refs/heads/developmental-psychology-windows.zip),
распакуйте его и запустите `install_windows.cmd`. Установщик готовит окружение,
Qt, Ollama и модель. Настройка описана в [инструкции для чистой Windows](docs/guides/WINDOWS_CLEAN_INSTALL.md).

Отдельный [скрипт сборки](scripts/windows/build_desktop.ps1) и ручной GitHub workflow
упаковывают Python и Qt в папку с `DigitalChild.exe`. Пользовательские данные такой
версии находятся отдельно, в `%LOCALAPPDATA%\DigitalChild`.
Фактическая сборка и запуск Windows-комплекта пока не проверены.
Подробности: [Windows-сборка](docs/guides/WINDOWS_BUILD.md).

## Возможности

- Сохраняемые личность, биография, отношения, эмоции и привычки.
- Потребности, собственные цели, арбитраж, пауза и дневные бюджеты активности.
- Проверка утверждений со свидетельствами и постоянной очередью повторов.
- Ассоциативный поиск опыта, оценки компетентности и журнал развития.
- Закрытые эксперименты, многошаговые планы и обучение по результатам действий.
- Личные проекты: поиск в памяти, запись заметки и проверка чтением.
- Контекстная маршрутизация LLM и проверка ответа перед показом.
- Qt-интерфейс, терминал и HTTP API; необязательный Windows LLM-host.

Самостоятельные шаги личного проекта включаются отдельно. Завершение заметки
не означает достижения широкой цели. Произвольные внешние действия не поддерживаются.
Описание механизмов и ограничений: [каталог документации](docs/README.md).

## Структура

```text
src/digital_child/
  domain/          общие модели, конституция и текстовые функции
  application/     агент, создание сервисов, команды и фоновые процессы
  cognition/       потребности, цели, автономия и инициатива
  psychology/      эмоции, характер, оценка ситуации и развитие
  memory/          эпизоды, убеждения, биография и поиск
  learning/        эксперименты, компетентность и саморегуляция
  planning/        числовые планы, личные проекты и локальные инструменты
  inference/       backend LLM, контекст, маршрутизация и проверка ответа
  infrastructure/  SQLite, конфигурация, время, поиск и бюджеты
  interfaces/      CLI, HTTP, Qt и терминальные компоненты
windows_host/      отдельный необязательный сервер инференса
scripts/           обслуживание проекта и платформенные операции
packaging/         спецификация и точка входа Windows-комплекта
docs/             инструкции, описание механизмов и история
tests/             существующие проверки, сгруппированные по подсистемам
```

Правила зависимостей, границы транзакций и карта модулей:
[ARCHITECTURE.md](docs/ARCHITECTURE.md). Основные прежние импорты
`digital_child.agent`, `models`, `storage`, `emotions`, `llm`, `service`,
`cli`, `api`, `desktop_app` сохранены через явные фасады. Рабочие реализации
находятся в соответствующих подпакетах; внутренний код использует только их.

## Команды и данные

В чате `/help` показывает полный список команд. Основные группы:

| Задача | Команды |
| --- | --- |
| Состояние и личность | `/state`, `/personality`, `/development`, `/timeline` |
| Цели и цикл | `/goals`, `/needs`, `/background`, `/pause`, `/resume` |
| Память | `/memory`, `/recall ТЕМА`, `/memory-index`, `/biography` |
| Обучение и планы | `/experiment balance`, `/competence`, `/plan` |
| Личные проекты | `/project`, `/project create ТЕМА`, `/project step ID` |
| Диагностика | `/diagnostics`, `/llm`, `/inference`, `/time` |

Настройки перечислены в [.env.example](.env.example). База по умолчанию:
`data/digital_child.db`; путь переопределяется через `DIGITAL_CHILD_DB`.
Заметки проектов сохраняются рядом с базой. `.env`, базы, заметки и модели
не включаются в Git и сборку. Для переноса памяти сначала закройте приложение.

## Обслуживание разработки

```bash
# Только структура и импорты, без запуска агента или LLM
python scripts/dev/check_architecture.py

# Статические проверки
uv run ruff check src/digital_child --ignore UP042
uv run mypy src/digital_child

# Размеры каталогов и удаление только воспроизводимых кэшей
python scripts/dev/workspace.py inspect
python scripts/dev/workspace.py clean
```

Кэши инструментов собраны в `.cache/`. Очистка сохраняет `.venv`, `.git`,
настройки, базы, проекты и модели. `UP042` временно исключён для существующих
Enum-моделей. Тесты и LLM при реорганизации не запускались.

[Документация](docs/README.md) · [План развития](docs/ROADMAP.md) · [Изменения](CHANGELOG.md)
