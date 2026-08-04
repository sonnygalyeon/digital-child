# Changelog

## 0.4.0

- Replaced curses input with Prompt Toolkit and UTF-8 console setup.
- Added Russian keyboard input support on macOS, Linux and Windows terminals.
- Moved the face into a separate PySide6 process.
- Added a vector human-like animated face with blinking, gaze, breathing and speech motion.
- Added compact visual terminal header, toolbar, spinner, command completion and history.
- Added background epistemic research mode.
- Reduced default prompt history, beliefs and memory payload.
- Added `reasoning_effort=none`, smaller output limits and compact prompts.
- Added Windows `digital-child-fast` model profile based on Qwen3 4B Instruct.
- Added Windows-host model warmup and first-token audit latency.
- Added Windows-host benchmark command and script.
- Fixed recursive audit-save bug in the Windows gateway.
- Added UTF-8 BOM-safe `.env` parsing.

## 0.3.0

- Full OpenAI-compatible LLM integration.
- Streaming terminal responses.
- Persistent conversation history.
- Personality-aware prompt context.

## 0.2.5

- Epistemic autonomy, identity, trust, research and animated terminal face.
