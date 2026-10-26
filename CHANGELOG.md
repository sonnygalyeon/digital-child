# Changelog

## Unreleased — Windows packaging and goal-linked projects

- Add a Windows PyInstaller folder bundle, archive/hash script and manual build workflow.
- Keep frozen-app settings, SQLite and logs in a separate persistent user directory.
- Dispatch spawned workers before Qt imports; log startup failures in parent and worker.
- Link selected self-generated goals to explicit proposed memory-dossier plans.
- Add bounded local memory search, immutable note creation and hash-verified readback.
- Persist prepared step arguments, observed outcomes, forecasts and explicit bounded retries.
- Add per-project background opt-in, daily budgets, pause/resume, revisions and milestones.
- Expose project commands, operator-only project API, compact Qt progress and timeline links.
- No automatic general-goal completion or causal personality reward for file operations.
- Static validation only; Windows binaries, runtime tests and live LLM measurements not run.

## Unreleased — offline emotion dynamics and action plans

- Time-based emotional decay, persistent transition causes and dominant-state hysteresis.
- Remove conversation-driven pride; reinforce it from bounded observed action outcomes.
- Persistent route/switchback plans with per-step prediction, feedback, replanning and restart recovery.
- Controlled causal attribution against no-op/opposite actions, including matched-noise controls.
- Separate prediction/control/planning competence; condition habit and character changes on outcomes.
- Indexed archive-wide episodic retrieval with person filtering and incremental legacy backfill.
- CLI/API plan, action-attribution and memory-index controls; Qt plan progress and timeline links.
- Static validation only; tests and LLM execution omitted as requested.

## Unreleased — response latency and inference routing

- Reuse interpretation concepts in memory; remove separate memory inference from the reply path.
- Adaptive social-message analysis and balanced task-specific model/token/context budgets.
- Explicit reasoning-model routing, compatibility controls and fast repair generation.
- Foreground precedence over new background inference; skip review of cancelled initiatives.
- Bounded connection-failure cooldown, cached model health and role fallback by known availability.
- Preserve all context sections within the prompt budget and filter legacy thinking prefixes.
- Per-stage reply timings, actual model metadata and content-free request diagnostics.
- Add `/inference`, `GET /v1/inference` and documented environment settings.
- Static checks only; configured model host unavailable for live measurements.

## Unreleased — associative memory and learning

- Concept-based episodic retrieval with optional budgeted LLM labels and outcome links.
- Persistent skill estimates, recent performance, uncertainty and prediction calibration.
- Per-person self-reported knowledge, expressed views, explanation history and corrections.
- Curiosity curriculum with noisy, conditional and changing-rule closed environments.
- Human demonstrations as hypotheses, independently checked by subsequent simulated actions.
- Learned regulation choices, next-turn observations, explicit feedback and bounded idle recovery.
- Qt development timeline with expandable changes, original episodes and source links.
- CLI/API controls and additive storage using the existing feature records.
- Static verification only; no tests added or run, as requested.

## Unreleased — behavior, experiments and communication

- Closed causal experiments with prediction error, persistent learned direction and scale transfer.
- Daily budgets, idle-only autonomous trials and stopping after stable transfer success.
- Structured contextual message interpretation with offline rules, quotation and irony cues.
- Persistent value conflicts and bounded biases toward explicit behavioral compromises.
- Evidence-linked autobiographical chapters, original episode inspection and revision history.
- Reply review before delivery, one bounded rewrite and deterministic fallback.
- Per-person communication preferences, quiet hours, topic snoozes and Qt settings controls.
- CLI and HTTP controls for experiments, biography, preferences and value conflicts.
- Existing databases gain feature storage automatically; identity reset clears those records.
- No tests added or run, as previously requested; static validation only.

## Unreleased — initiative, time awareness and offline verification

- Completed spontaneous discussion, developmental interests and per-person contact cooldowns.
- Longing and absence boredom after 24 hours, restored across application launches.
- Separate cancellable generation worker, persistent daily message budget and contact opt-out.
- HTTPS Date clock refresh with saved UTC correction and monotonic in-session timing.
- Durable factual verification queue with bounded retry, startup recovery and legacy claim import.
- Atomic evidence/trust/outcome updates using nested SQLite savepoints.
- Evidence-linked discussion of contradicted earlier claims without assuming deliberate deception.
- Interests and connection status in Qt, CLI controls and time/verification HTTP diagnostics.
- Fixed missing FastAPI dependency import and desktop process typing.
- Static checks only; no tests added or run, preserving the user's earlier instruction.

## Unreleased — developmental psychology and desktop sphere

- Persistent subject-specific temperament, slowly adapting character and personal values.
- Seven experience-driven developmental stages with smooth behavioral transitions.
- Situation appraisal, contextual emotional memories, interests and per-person relationship repair.
- Motivational decision scoring, commitment inertia, coping strategies and stable response styles.
- Habit biases and reinforcement from attributed research outcomes and actual rest relief.
- Individual goal weights, need sensitivity and goal switching thresholds.
- Mood and self-model dynamics; frustration, anxiety, sadness, affection, pride and boredom.
- Psychological context in LLM replies and relevant autobiographical memory selection.
- Personality panel, expanded emotional sphere dynamics, CLI commands and psychology API.
- Serialized interactions and background outcome attribution across resets and shutdown.
- No tests added or executed for the developmental psychology work at the user's request.
- Clean-Windows bootstrap with interactive application and model directories, verified portable
  uv/Ollama downloads, managed Python, Qt, model setup and a server-aware desktop shortcut.
- Local model launcher restores the selected model directory after reboot and uses an isolated port.

- Native PySide6 chat with the emotional visualization in the same window.
- Seven translucent sphere shells with smooth, state-driven movement and light.
- Separate spawned agent process, streaming tokens and persistent conversation history.
- Emotion and need meters, goal display, cognitive loop controls and rest.
- Windows GUI entry point, setup script and desktop shortcut without a console.
- Existing terminal companion window now uses the same sphere renderer.
- Architecture review and Windows migration instructions.

## 0.5.0

- Added event-driven need states independent of wall-clock age.
- Added persistent cognitive events and crash recovery of unprocessed events.
- Added deterministic internal drives and self-generated goal candidates.
- Added user-suggested goals that do not imply authority.
- Added goal arbitration by need pressure, urgency, value alignment, utility, cost and risk.
- Added bounded background cognitive loop with pause, resume and manual tick.
- Added persistent resource budgets and diagnostics.
- Added CLI and HTTP endpoints for needs, drives, events, budgets and loop state.
- Preserved v0.4.1 LLM, Russian terminal input, memory and desktop face behavior.
- Added automatic SQLite migration and 44 passing tests.

## 0.4.1

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
