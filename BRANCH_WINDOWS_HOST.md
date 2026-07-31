# Branch: windows-llm-host

This archive is based on Digital Child v0.3.0 and adds a dedicated Windows LLM host.

Create the branch after replacing files:

```bash
git checkout -b windows-llm-host
git add .
git commit -m "feat: add authenticated Windows LLM host with optional PostgreSQL"
```

The Windows host is isolated under `windows_host/`; the existing Mac client remains usable.
See `docs/WINDOWS_LLM_HOST.md`.
