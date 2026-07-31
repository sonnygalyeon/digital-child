# Windows LLM host branch

Branch name: `windows-llm-host`

This branch adds a dedicated Windows host without moving the Digital Child personality or
its cognitive database away from the client machine.

## Architecture

```text
Mac / Raspberry Pi
Digital Child personality, memory and terminal face
                 |
       OpenAI-compatible HTTPS/HTTP request
                 |
Windows gateway :8787
API key, model allowlist, size limit, audit
                 |
Ollama localhost :11434
                 |
Qwen3 8B Q4_K_M on Ryzen 7 5700X
                 |
Optional PostgreSQL localhost :5432
request metadata only by default
```

Ollama itself remains bound to `127.0.0.1`. Only the authenticated gateway is exposed to
the local network.

## Hardware profile

The Ryzen 7 5700X has 8 cores, 16 threads and AVX2. With 32 GB RAM:

- `qwen3:4b`: fast fallback and testing profile;
- `qwen3:8b`: recommended default;
- 14B Q4 models: fit in memory but are slower and leave less context headroom;
- 30B models: not recommended for interactive CPU-only use on this machine.

Keep one model loaded and one request at a time. The setup script configures an 8K context,
`OLLAMA_NUM_PARALLEL=1`, and `OLLAMA_MAX_LOADED_MODELS=1`. Large advertised context
windows are not free: the KV cache grows with context and parallel requests multiply memory
usage.

## Windows setup

Open PowerShell in the repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\setup_windows_host.ps1 -Model qwen3:8b
```

With PostgreSQL in Docker Desktop:

```powershell
.\scripts\windows\setup_windows_host.ps1 -Model qwen3:8b -WithPostgres
```

To add a firewall rule limited to the local subnet, run elevated PowerShell:

```powershell
.\scripts\windows\setup_windows_host.ps1 -Model qwen3:8b -OpenFirewall
```

Start:

```powershell
.\scripts\windows\start_windows_host.ps1
```

Test:

```powershell
.\scripts\windows\test_windows_host.ps1
```

Optional autostart at user logon:

```powershell
.\scripts\windows\create_scheduled_task.ps1
```

## Mac client configuration

Find the Windows IPv4 address:

```powershell
ipconfig
```

Then set the Digital Child `.env` on the Mac:

```env
DIGITAL_CHILD_LLM_PROVIDER=openai-compatible
DIGITAL_CHILD_LLM_BASE_URL=http://WINDOWS_IPV4:8787/v1
DIGITAL_CHILD_LLM_MODEL=qwen3:8b
DIGITAL_CHILD_LLM_API_KEY=THE_KEY_FROM_WINDOWS_HOST_ENV
DIGITAL_CHILD_LLM_TIMEOUT=300
DIGITAL_CHILD_LLM_TEMPERATURE=0.55
DIGITAL_CHILD_LLM_MAX_TOKENS=1200
```

Test from the Mac:

```bash
uv run digital-child llm
uv run digital-child chat
```

## PostgreSQL policy

PostgreSQL is optional and initially stores operational metadata only:

- request time;
- model;
- streaming flag;
- duration;
- byte counts;
- status code;
- SHA-256 hash of the request;
- error type.

Prompt and answer content are **not stored** unless `WINDOWS_HOST_STORE_CONTENT=true` is set.
The cognitive memory remains in the Digital Child database. Migrating identity, beliefs and
memory to PostgreSQL should be a separate schema migration with rollback tests.

## Security boundaries

- Do not forward port 8787 on the internet router.
- Keep the firewall rule limited to `LocalSubnet`.
- Use a long API key.
- Do not expose Ollama port 11434 directly.
- Use a VPN such as WireGuard/Tailscale for remote access instead of public port forwarding.
- Keep content logging disabled unless it is specifically required.
