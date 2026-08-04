# Digital Child v0.4.0

Долгоживущий цифровой агент с автономной личностью, доказательной памятью,
фоновым поиском, потоковой LLM и отдельным анимированным окном лица.

## Главное в этой версии

- русский ввод через `prompt_toolkit` вместо посимвольного `curses`;
- отдельное окно лица на PySide6;
- лицо не является картинкой: оно рисуется векторно и постоянно анимируется;
- моргание, взгляд, дыхание, движения головы и рта работают даже в состоянии idle;
- терминал теперь содержит только чат, статусную строку, автодополнение команд и историю;
- проверка фактических утверждений по умолчанию выполняется в фоне;
- компактный LLM-контекст уменьшает время обработки prompt;
- для Windows-хоста добавлен быстрый профиль `digital-child-fast`;
- reasoning у Qwen/Ollama по умолчанию отключён;
- модель прогревается при запуске сервера;
- PostgreSQL-аудит сохраняет время до первого токена.

## Установка клиента

```bash
uv python pin 3.12
uv sync --extra dev --extra desktop
uv run pytest
```

`desktop` устанавливает PySide6. Без него ядро и терминальный чат продолжат работать,
но отдельное окно лица не запустится.

## Запуск

```bash
uv run digital-child chat
```

Проверка только лица:

```bash
uv run digital-child face
```

Без окна лица:

```bash
uv run digital-child chat --no-face-window
```

Минимальный строковый режим:

```bash
uv run digital-child chat --plain
```

Проверка LLM:

```bash
uv run digital-child llm
```

## Быстрый Windows-host

На Windows-компьютере с Ryzen 7 5700X и 32 ГБ:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\setup_windows_host.ps1
.\scripts\windows\start_windows_host.ps1
```

Сценарий обновления сохраняет существующий API-ключ, если не передан `-RegenerateApiKey`.

По умолчанию сценарий:

1. загружает `qwen3:4b-instruct`;
2. создаёт локальную модель `digital-child-fast`;
3. задаёт контекст 4096;
4. ограничивает ответ 512 токенами на уровне модели;
5. отключает reasoning на уровне шлюза;
6. прогревает модель;
7. оставляет Ollama доступным только на localhost;
8. публикует защищённый API на порту 8787.

Проверка скорости:

```powershell
.\scripts\windows\benchmark_windows_host.ps1
```

## Конфигурация клиента для Windows-хоста

```env
DIGITAL_CHILD_LLM_PROVIDER=openai-compatible
DIGITAL_CHILD_LLM_BASE_URL=http://192.168.1.50:8787/v1
DIGITAL_CHILD_LLM_MODEL=digital-child-fast
DIGITAL_CHILD_LLM_API_KEY=ключ-из-windows_host-.env

DIGITAL_CHILD_LLM_REASONING_EFFORT=none
DIGITAL_CHILD_LLM_MAX_TOKENS=512
DIGITAL_CHILD_LLM_HISTORY_MESSAGES=6
DIGITAL_CHILD_LLM_MEMORY_ITEMS=4
DIGITAL_CHILD_LLM_BELIEF_ITEMS=4
DIGITAL_CHILD_LLM_PROMPT_MAX_CHARS=7000

DIGITAL_CHILD_RESEARCH_MODE=background
```

## Режимы проверки информации

```env
DIGITAL_CHILD_RESEARCH_MODE=background
```

- `background` — сначала дать ответ, затем проверить утверждение в фоне;
- `blocking` — дождаться проверки перед ответом;
- `manual` — проверять только через `/research`.

Фоновый режим не превращает утверждение в истину: оно сразу сохраняется как
непроверенное свидетельство, а убеждение обновляется после завершения проверки.

## Архитектура интерфейса

```text
Prompt Toolkit terminal
  ├─ русский ввод
  ├─ история команд
  ├─ потоковый ответ
  └─ статус и уведомления
           │
           │ local multiprocessing Pipe
           ▼
PySide6 face process
  ├─ 60 FPS
  ├─ idle-анимация
  ├─ эмоции
  ├─ speaking-анимация
  └─ полностью отдельное окно
```

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

## Документация

- [`docs/MIGRATION_V0.4.md`](docs/MIGRATION_V0.4.md)
- [`docs/DESKTOP_FACE.md`](docs/DESKTOP_FACE.md)
- [`docs/PERFORMANCE_WINDOWS.md`](docs/PERFORMANCE_WINDOWS.md)
- [`docs/WINDOWS_LLM_HOST.md`](docs/WINDOWS_LLM_HOST.md)
