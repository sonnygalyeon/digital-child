# Оптимизация Windows-host: Ryzen 7 5700X / 32 ГБ

## Профиль по умолчанию

```text
base model: qwen3:4b-instruct
Ollama model: digital-child-fast
context: 4096
reasoning: none
parallel requests: 1
loaded models: 1
keep alive: 60 minutes
client max tokens: 512
host maximum: 768
```

## Почему ответы были медленными

Основные источники задержки в предыдущей версии:

1. 8B/9B-модель работала только на CPU;
2. reasoning был включён у thinking-модели;
3. в prompt передавалось слишком много истории и памяти;
4. интернет-проверка выполнялась до первого ответа;
5. модель могла выгружаться из памяти между запросами;
6. максимальный ответ был задан на 1200 токенов.

## Быстрый и сбалансированный режимы

### Fast

```powershell
.\scripts\windows\setup_windows_host.ps1
```

Использует 4B Instruct и подходит для постоянного диалога.

### Balanced

```powershell
.\scripts\windows\setup_windows_host.ps1 `
  -BaseModel qwen3:8b `
  -ModelName digital-child-balanced
```

Качество выше, но CPU-генерация заметно медленнее.

## Измерение

Запусти сервер, затем во втором PowerShell:

```powershell
.\scripts\windows\benchmark_windows_host.ps1 -Runs 5
```

Метрики:

- время до первого токена;
- полное время ответа;
- количество символов;
- PostgreSQL-аудит, если он включён.

## Интерпретация

Если время до первого токена велико только при первом запросе — это загрузка модели.
Если велико всегда — уменьшай prompt/context или используй 4B. Если первый токен
приходит быстро, но ответ долго заканчивается — уменьши `MAX_TOKENS` либо требуй
более короткий стиль ответа.


Сценарий обновления сохраняет существующий API-ключ, если не передан `-RegenerateApiKey`.
