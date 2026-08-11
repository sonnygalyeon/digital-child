# Windows LLM Host

Отдельный Windows-компьютер выполняет только тяжёлый LLM-инференс. Личность,
память, доверие, убеждения и интерфейс могут оставаться на Mac или Raspberry Pi.

## Схема

```text
Digital Child client
        │ OpenAI-compatible API + Bearer key
        ▼
Windows gateway :8787
        │ localhost only
        ▼
Ollama :11434
        │
        └─ digital-child-fast
```

PostgreSQL опционально хранит технический аудит. Тексты запросов не сохраняются,
пока `WINDOWS_HOST_STORE_CONTENT=false`.

## Установка

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\setup_windows_host.ps1
```

Опционально:

```powershell
.\scripts\windows\setup_windows_host.ps1 -WithPostgres -OpenFirewall
```

`-OpenFirewall` требует PowerShell от администратора и открывает порт только для
`LocalSubnet`.

## Запуск

```powershell
.\scripts\windows\start_windows_host.ps1
```

Проверка:

```powershell
.\scripts\windows\test_windows_host.ps1
```

Тест производительности:

```powershell
.\scripts\windows\benchmark_windows_host.ps1 -Runs 5
```

## Клиентский `.env`

```env
DIGITAL_CHILD_LLM_PROVIDER=openai-compatible
DIGITAL_CHILD_LLM_BASE_URL=http://WINDOWS_IP:8787/v1
DIGITAL_CHILD_LLM_MODEL=digital-child-fast
DIGITAL_CHILD_LLM_API_KEY=WINDOWS_HOST_API_KEY
DIGITAL_CHILD_LLM_REASONING_EFFORT=none
DIGITAL_CHILD_LLM_MAX_TOKENS=512
```

## Безопасность

- Ollama не публикуется в LAN;
- шлюз требует Bearer API key;
- разрешён только список моделей;
- размер входного JSON ограничен;
- длина ответа ограничена на стороне шлюза;
- PostgreSQL слушает только localhost;
- содержимое запроса не журналируется по умолчанию.

## Маршруты

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions
POST /v1/host/warmup
GET  /v1/host/audit/recent
```


Сценарий обновления сохраняет существующий API-ключ, если не передан `-RegenerateApiKey`.
