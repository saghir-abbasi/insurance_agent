> **Historical document.** This plan describes the earlier Hume → OpenAI port of the Maxine (WellGen CCM) agent. The project has since been converted to **Emma, the Final Expense insurance agent**; the package src/max_health_demo/ is now src/insurance_agent/. See README.md for the current architecture.

# Implementation Plan — Porting Maxine-Hume Features to the OpenAI Agents SDK Project

**Date:** 2026-07-06
**Goal:** The folders/files copied from the `maxine_hume` project (`data/`, `transcript_agent/`, `admin_dashboard/`, RAG / knowledge base, `escalate_to_human` tool, `knowledge_base` tool, `callapi.py`) must become fully functional in **this** project, which is built on the **OpenAI Agents SDK Realtime API** (`agents.realtime`, `gpt-realtime-mini`). All Hume AI / EVI code must be removed or replaced. No Hume SDK, no EVI configs, no Hume voices.

---

## 1. Current State Analysis

### 1.1 What already works (native to this project)

| Component | Status |
|---|---|
| `src/max_health_demo/main.py` | FastAPI app + Chainlit mount at `/app`. Working. |
| `src/max_health_demo/api/v1/routes/realtime.py` | WS endpoint `/api/v1/realtime/call-session/{session_id}` using `RealtimeRunner` / `RealtimeAgent`. Emits `media`, `clear`, `user_transcript`, `assistant_transcript` events — the same wire protocol `callapi.py` expects. Working. |
| `src/max_health_demo/agents/realtime_call_agent.py` | Maxine CCM prompt (hardcoded `INSTRUCTIONS` constant) + 2 tools (`check_websocket_connection_tool`, `disconnect_websocket_tool`). Working. |
| `src/max_health_demo/realtime_websocket_manager.py` | Session lifecycle, playback tracker, event pump. Working. |
| `src/max_health_demo/tools/websocket_tools.py` | Working; the pattern for context-based tools to follow. |
| `chat.py` route + `chat_agent` + Chainlit `app.py` | Working. |

### 1.2 What was copied and its current status

| Copied item | Hume-coupled? | Works today? | Problem |
|---|---|---|---|
| `core/knowledge_base/rag.py` (RAG) | **No** — pure chromadb + fastembed + pypdf | Import fails | `chromadb`, `fastembed`, `pypdf` are **not in `pyproject.toml`** |
| `tools/knowledge_base_tools.py` | No | Not wired | Plain function, not a `@function_tool`; never registered on `realtime_call_agent`; prompt never mentions it |
| `tools/all_escalate_to_human_tools.py` | No (protocol only) | **Broken import** | Imports `current_call_websocket` from `realtime_websocket_manager` — that ContextVar **does not exist** in this project. Also plain function, not registered, no prompt rules |
| `admin_dashboard/` (router, settings_store, evi_builder, hume_voices, admin.html) | **Yes, heavily** | **Broken** | Imports `hume.empathic_voice.types`, `hume.tts`, `max_health_demo.core.evi_config_manager`, `max_health_demo.core.prompts` — none exist here; `configuration.ADMIN_API_TOKEN` / `VOICE_ID` / `EVI_CONFIG_NAME` / `EVI_VERSION` missing from `core/config.py`; routers never mounted in `main.py` / `api/v1/main.py` |
| `transcript_agent/` | No — already uses OpenAI Agents SDK (`Agent`, `Runner`, structured output) | Mostly | **Hardcoded OpenAI API key** (`transcript_agent.py:30` — must be revoked & moved to env), hardcoded model name, hardcoded remote-DB credentials; `requests` + `python-dotenv` not in deps |
| `callapi.py` (AGI bridge) | Naming only | Yes (on Asterisk host) | Protocol already matches this backend (`media`/`clear`/`disconnect`/`escalate_to_human`/transcripts). Cosmetic: `base_dir` says `maxine_hume`; `ws_uri` points at port 8003 while this server runs on 8000 |
| `data/` | Partially | — | `welgen_data.pdf` + `chroma/` store are fine; `agent_settings.json` holds **Hume** settings (Hume voice UUID, `HUME_AI` provider) and must be re-seeded |
| `README_Sample.md`, `ESCALATE_HUMAN_LOGIC.md`, `dialplan.md` | Docs | — | Describe the Hume project; rewrite after implementation |

### 1.3 Target architecture (all-OpenAI)

```
PSTN caller
   │
   ▼
Asterisk (EAGI) ──spawns──► callapi.py
   │  WebSocket: {media|clear|disconnect|escalate_to_human|transcripts}
   ▼
FastAPI backend (src/max_health_demo/)
   ├─ RealtimeAgent (OpenAI gpt-realtime-mini)
   │    ├─ tool: disconnect_websocket_tool          (existing)
   │    ├─ tool: check_websocket_connection_tool    (existing)
   │    ├─ tool: search_knowledge_base              (NEW — RAG/Chroma)
   │    └─ tool: escalate_to_human                  (NEW — WS event to AGI)
   ├─ Admin dashboard /admin (NEW — OpenAI voices, language, prompt template)
   └─ Chainlit /app (existing, browser testing)

on hangup: callapi.py ──spawns──► transcript_agent/run_refinement.py
                                   (OpenAI Agents SDK, SOAP notes, do-not-call)
```

Key difference vs. Hume: Hume required pushing a **remote EVI config** (prompt/voice versioning via `EviConfigManager`). OpenAI Realtime has **no server-side config object** — voice, language, and instructions are passed per session at connect time. So the admin dashboard becomes *simpler*: **save settings locally → every new call reads them**. No config-push step, no cache invalidation, and "changes apply on the next call" falls out naturally.

---

## 2. Work Packages

### WP-1: Dependencies & configuration (prerequisite for everything)

**`pyproject.toml` — add:**
```toml
"chromadb>=1.0",       # vector store (RAG)
"fastembed>=0.7",      # BAAI/bge-base-en-v1.5 embeddings (RAG)
"pypdf>=5.0",          # PDF extraction (RAG)
"requests>=2.32",      # transcript_agent remote-DB upload
"python-dotenv>=1.0",  # transcript_agent standalone .env loading
```
No `hume` dependency is added anywhere.

**`core/config.py` — add fields:**
```python
ADMIN_API_TOKEN: Optional[str] = None      # enables /admin (503 when unset)
REALTIME_VOICE: str = "marin"              # default voice (fallback when no settings file)
TRANSCRIPT_MODEL: str = "gpt-5-nano-2025-08-07"  # transcript refiner model
```

**`.env` — add:** `ADMIN_API_TOKEN=<long-random-secret>` (and nothing Hume-related).

### WP-2: Knowledge base (RAG) + `search_knowledge_base` tool

`rag.py` is already Hume-free and stays **unchanged** (chunker, fingerprint-based idempotent `ingest()`, `query()` with cosine scores, singleton).

1. **Wrap the tool** — `tools/knowledge_base_tools.py`: decorate `search_knowledge_base` with `@function_tool(name_override="search_knowledge_base", failure_error_function=None)`. Keep it sync or make it async wrapping `asyncio.to_thread(kb.query, ...)` so embedding never blocks the realtime event loop (**recommended: async + to_thread** — a 50–200 ms embed on the loop would stutter live audio). Keep `MIN_SCORE=0.55`, `MAX_RESULTS=3`, `MAX_SNIPPET_CHARS=600` as calibrated.
2. **Register on the agent** — add to `realtime_call_agent.tools`.
3. **Prompt rules** — add a section to the agent instructions: for any off-script question about WellGen, CCM, eligibility, billing, or services, call `search_knowledge_base`, answer briefly and conversationally from the snippets, then steer back to the assessment; if nothing is found, say so and offer a follow-up.
4. **Startup wiring** — in `main.py` `lifespan`, before `yield`:
   ```python
   await asyncio.to_thread(lambda: get_knowledge_base().ingest())
   ```
   This pre-warms the fastembed model **and** ingests (fingerprint check makes it a no-op when the PDF is unchanged) — fixing the two known Hume-project pain points (5–10 s cold start on the first mid-call query; "swap the PDF, forget to re-ingest"). Updating the KB then collapses to: replace `data/welgen_data.pdf` → restart the server.
5. **Verify existing `data/chroma/`** — the copied store was built with the same embedder/collection name, so it should be reused as-is; the fingerprint check confirms it on first startup.

### WP-3: Escalate-to-human tool

The AGI side (`callapi.py:494–519`) and dialplan already handle the `escalate_to_human` event — only the backend tool is broken.

1. **Rewrite `tools/all_escalate_to_human_tools.py`** to follow the `websocket_tools.py` pattern — get the websocket from the run context instead of the nonexistent ContextVar:
   ```python
   @function_tool(name_override="escalate_to_human", failure_error_function=None)
   async def escalate_to_human_tool(context: RealtimeAgentContextWrapper, reason: str) -> str:
       websocket = context.context.websocket
       # guard: client_state == CONNECTED, else return "could not escalate"
       await websocket.send_json({"event": "escalate_to_human", "reason": sanitized})
   ```
   Sanitize `reason` to a single line (strip newlines/quotes) before sending — `callapi.py` re-sanitizes, but don't rely on it.
2. **Playback-drain decision:** `disconnect_websocket_tool` waits for tracked playback before closing; escalation must **not** close the websocket itself — the AGI script quiesces playback and ends the session (that's its documented job). The tool only sends the event and returns; the model should speak a short handoff line *before* calling the tool (prompt rule below).
3. **Register on the agent** and **add prompt rules**: escalate when the caller explicitly asks for a human, wants to book an appointment, or needs help beyond the script; say a brief "let me transfer you" line first, then call `escalate_to_human`; do not call `disconnect_websocket_tool` afterwards (the transfer path owns the hangup).
4. Update `ESCALATE_HUMAN_LOGIC.md` to reflect the new file/line reality.

### WP-4: Admin dashboard (de-Humed)

Keep: token-auth model, settings JSON store with atomic writes, `{language}` template mechanics, static single-page UI, rate-limited voice test. Replace every Hume surface with an OpenAI equivalent. **Delete `evi_builder.py` and `hume_voices.py`** (nothing to build/push; Hume voice library gone).

| Hume concept | OpenAI replacement |
|---|---|
| Voice library (`hume_voices.list_voices`) | Static list of OpenAI Realtime voices: `alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar` (new module `admin_dashboard/openai_voices.py`) |
| Voice test via Hume TTS | OpenAI TTS (`gpt-4o-mini-tts`, `response_format="mp3"`) via the existing `AsyncOpenAI` client; keep the per-language `SAMPLE_UTTERANCES` dict and the 10/min rate limit. Note: TTS voices approximate but don't perfectly match realtime voices — acceptable for a preview; document it in the UI |
| `EviConfigManager.create_config` push + cache invalidation | **Nothing.** `PUT /settings` just validates + saves. New calls read the store |
| `voice_provider` (`HUME_AI`/`CUSTOM_VOICE`) | Dropped from the API/model (keep field defaulted for file compat or migrate it away) |
| 11 Hume languages | Keep the same list + `Caller Language` option (model-side, works fine on gpt-realtime); constants move from `settings_store.py` unchanged |
| Prompt seeded from `core/prompts.py` | Seed from `INSTRUCTIONS` in `agents/realtime_call_agent.py` (moved — see below) |

**File changes:**

1. **`settings_store.py`** — remove `core.prompts` import (seed from the realtime agent's `INSTRUCTIONS`); default `voice_id="marin"`, drop/ignore `voice_provider`; keep `{language}` targeted-replace resolution and the `Caller Language` whitelist instruction verbatim. **Important compatibility check:** the current `INSTRUCTIONS` uses single-brace placeholders (`{name}`, `{user_info.user_name}`, `{user_info.date_of_birth}`) that today are rendered *literally* (never `.format()`-ed). The template resolution must stay a targeted `str.replace("{language}", ...)` so those braces pass through; separately, WP-5 makes the real patient-info substitution explicit.
2. **`router.py`** — remove Hume imports and the apply-to-Hume block in `PUT /settings`; `GET /voices` returns the static list; `POST /voices/test` calls OpenAI TTS; keep `require_admin_token`, validation, warnings.
3. **`static/admin.html`** — remove the provider toggle; voices come from the new endpoint shape; everything else (token field, language dropdown, prompt editor, test button) stays.
4. **Mount** in `main.py`: `app.include_router(page_router)` for `/admin`, and in `api/v1/main.py`: `api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])`.
5. **Re-seed `data/agent_settings.json`** — delete the copied Hume file; the store re-seeds with OpenAI defaults on first load.

### WP-5: Wire settings into the realtime session

This is the piece that makes the dashboard *do* something:

1. **`agents/realtime_call_agent.py`** — `get_realtime_agent_instructions` loads the settings store (`get_settings_store().load()`), takes `resolved_system_prompt()` (template + language directive), substitutes patient placeholders (`{name}` → agent name "Maxine" stays literal in the template or is normalized; `{user_info.user_name}` / `{user_info.date_of_birth}` → values from `context.context.user_info` via targeted `str.replace`), and appends the existing "# Patient Information" block. Falls back to the hardcoded `INSTRUCTIONS` if the store is unreadable.
2. **`api/v1/routes/realtime.py`** — build `model_settings` **inside** `handle_call_session` (it is module-level today, so a voice change would otherwise require a restart): `voice=settings.voice_id`, everything else unchanged. Settings-file read is a tiny JSON load per call — negligible.
3. Result: **Save in dashboard → next call uses new voice/language/prompt**; in-progress calls are untouched. Same semantics the Hume README promised, with less machinery.

### WP-6: Transcript agent hardening

Functionally it already runs on the OpenAI Agents SDK; the work is cleanup:

1. **Remove the hardcoded API key** (`transcript_agent.py:30`) → `os.getenv("OPENAI_API_KEY")` (loaded via existing `load_dotenv()`). **The exposed key must be revoked in the OpenAI dashboard regardless** — it's committed to git history.
2. Model name from env (`TRANSCRIPT_MODEL`, default `gpt-5-nano-2025-08-07`). Since the default OpenAI client picks up `OPENAI_API_KEY` automatically, the explicit `AsyncOpenAI(api_key=...)`/`OpenAIChatCompletionsModel` wiring can shrink to `Agent(model=os.getenv("TRANSCRIPT_MODEL", ...))`.
3. Move DB endpoint/credentials (`DB_BASE_URL`, `DB_USERNAME`, `DB_PASSWORD`) to env vars with the current values as defaults, so deployment doesn't break but secrets leave the source.
4. Keep: `RefinementResult` structured output, SOAP format, do-not-call detection + blacklist upload, transcript upload, bare-`except` line parser (works on the JSONL `callapi.py` writes).
5. `run_refinement.py` unchanged (arg contract matches `callapi.py`'s spawn at line 675–685).

### WP-7: `callapi.py` alignment (deploy-time, minimal code churn)

`callapi.py` already speaks this backend's exact protocol (verified: `media` base64 payloads both ways, `clear` on `audio_interrupted`, `disconnect`, `user_transcript`/`assistant_transcript` JSONL logging, `escalate_to_human` → AGI vars, refinement spawn). Changes:

1. `ws_uri` (line 844): point at this backend's actual port — `ws://localhost:8000/...` in dev, or keep 8003 if production runs uvicorn on 8003 (decide at deploy; leave both as comments like today).
2. `base_dir` (line 77): rename `maxine_hume` → this project's name (log-path cosmetics only).
3. Audio format sanity check: the backend uses `g711_alaw` only when `ENVIRONMENT=production`; `callapi.py` sends 8 kHz PCM16 from EAGI. Confirm which format the deployed pair actually exchanges and document it (the Hume resampler is gone; this must match or audio is garbage). **This is the one integration risk to test with a real call.**
4. No other changes — escalation and refinement paths are already correct relative to this repo's layout (`./transcript_agent/run_refinement.py`).

### WP-8: Docs & cleanup

1. Rewrite `README.md` to cover: architecture diagram (OpenAI edition), RAG usage + update procedure (now just "replace PDF, restart"), escalation flow, admin dashboard, transcript agent, Asterisk deployment, `.env` cheatsheet. `README_Sample.md` is then deleted (its Hume-specific content is superseded).
2. Update `ESCALATE_HUMAN_LOGIC.md` file/line references.
3. Delete dead files: `admin_dashboard/evi_builder.py`, `admin_dashboard/hume_voices.py`, stale `__pycache__` dirs.
4. Add `data/chroma/` and `data/agent_settings.json` to `.gitignore` consideration (runtime artifacts).

---

## 3. Execution Order & Dependencies

```
WP-1 (deps/config)
  ├─► WP-2 (RAG tool)          ─┐
  ├─► WP-3 (escalate tool)      ├─► WP-8 (docs)
  ├─► WP-4 (admin dashboard) ─► WP-5 (settings→session)
  └─► WP-6 (transcript agent)  ─┘
WP-7 (callapi.py) — independent, deploy-time
```

Suggested implementation sequence: **WP-1 → WP-2 → WP-3 → WP-6 → WP-4 → WP-5 → WP-7 → WP-8.** (Tools first: they're small, self-contained, and immediately testable via Chainlit; dashboard last because WP-5 touches the live call path.)

---

## 4. Testing Plan

| Test | How |
|---|---|
| RAG ingest & query | `uv run python -c "from max_health_demo.core.knowledge_base import get_knowledge_base as g; kb=g(); kb.ingest(); print(kb.query('What is CCM?', k=3))"` — expect scores ≥ 0.7 for in-domain |
| KB tool via agent | Chainlit `/app`: ask "What services does WellGen provide?" mid-call → agent answers from PDF, returns to script |
| Escalate tool | Chainlit: say "I want to speak to a human" → WS client receives `{"event":"escalate_to_human","reason":...}` (observe in a scripted WS client, since Chainlit UI won't render it); on Asterisk: `ESCALATE=true` in `debug.log`, dialplan branches |
| Admin API | `curl -H "X-Admin-Token: ..." /api/v1/admin/settings` (200), wrong token (401), unset token (503); `PUT` with empty prompt (422), bad language (422); voice test returns playable MP3; 11th test in a minute → 429 |
| Settings → next call | Change voice to `cedar` + language `Spanish` in dashboard → new Chainlit session speaks Spanish in the new voice; a session already open keeps old settings |
| Transcript refinement | `uv run python transcript_agent/run_refinement.py <sample transcript.json> <outdir> test_123 John 1990-01-01 051-1234567` → `refined_transcript.txt` with SOAP sections; do-not-call phrase triggers blacklist call (or its logged failure) |
| Startup ingest | Delete `data/chroma/`, start server → log shows `Indexed N chunks`; restart → `already up to date` |
| End-to-end (deploy) | Real Asterisk call: audio both ways, barge-in (`clear`), hangup → refinement spawned, escalation path, audio-format check from WP-7.3 |

---

## 5. Risks & Notes

1. **Leaked OpenAI API key** in `transcript_agent/transcript_agent.py:30` (already in git history) — revoke it now, independent of this work.
2. **Audio format mismatch** (WP-7.3) is the only true unknown; everything else is verified against the code. Must be validated with one real call before production.
3. **Realtime tool latency:** `search_knowledge_base` runs during a live call; `asyncio.to_thread` keeps the loop free, but the caller still waits ~0.5–1 s — the prompt should have Maxine say a natural filler ("Let me check that for you…") before tool calls.
4. **Voice-test fidelity:** OpenAI TTS voices are close to but not identical to realtime voices; label the button "preview (approximate)".
5. **`MIN_SCORE=0.55` calibration** was done on `bge-base-en-v1.5` — unchanged here, so it carries over. Recalibrate only if the embedding model changes.
6. **Windows dev vs. Linux deploy:** `callapi.py` and the refinement spawn (`/var/lib/asterisk/...` paths, `start_new_session=True`) are Asterisk-host-only; nothing in the backend depends on them, so local dev on Windows stays fully functional through Chainlit.
7. **Remote-DB dependency** (`23.158.200.139:5002`) in the transcript agent is best-effort by design (failures are logged, refinement still saved locally) — keep that behavior.
