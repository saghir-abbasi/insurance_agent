# Admin Dashboard — voice, language & system prompt

Runtime control of Emma, the Final Expense insurance realtime agent, without code changes or restarts.
Everything runs against the **OpenAI** stack — there is no Hume dependency.

## What's in this folder

| File | Purpose |
|---|---|
| `settings_store.py` | `AgentSettings` model + JSON file store (`data/agent_settings.json`), atomic writes, seeded from `core/prompts.py` defaults on first run. Holds the prompt as a **template** with the `{language}` placeholder; resolution is a targeted `.replace()` so the script's other single-brace placeholders (`{name}`, `{company}`, `{user_info.user_name}`, `{user_info.date_of_birth}`, `{user_info.state}` — resolved per call by the realtime agent) are untouched. `{language}` resolves to a full language instruction: for a fixed language, "converse exclusively in X"; for the special **Caller Language** option, "start in English, switch to the caller's language if it's one of the 16 supported ones, otherwise say you don't understand and stay in English". A leftover Hume settings file (unknown voice id) is detected on load and re-seeded. |
| `openai_voices.py` | Static catalog of the OpenAI realtime voices + TTS sample synthesis (`gpt-4o-mini-tts`) for the ▶ preview button. Marin/Cedar are realtime-only and preview with a stand-in TTS voice. |
| `router.py` | `/api/v1/admin/*` endpoints (token-authenticated) + the `/admin` page route. |
| `static/admin.html` | The single-page dashboard. |

## How changes are applied

There is **no push/apply step**. The realtime session reads the settings store
at connect time: `agents/realtime_call_agent.py` loads the resolved prompt
template per call, and `api/v1/routes/realtime.py` reads the voice per call.
Saving in the dashboard is therefore the entire "apply" — changes take effect
on the **next call**; in-progress calls are unaffected, and a dashboard outage
can never break live calls (call handling falls back to built-in defaults).

## Enabling

Add to the backend `.env`:

```ini
ADMIN_API_TOKEN="<pick-a-long-random-secret>"
```

Without it, every admin API call returns `503` and the dashboard is effectively disabled.

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/admin` | GET | Dashboard page (HTML shell; data calls need the token). |
| `/api/v1/admin/settings` | GET | Current settings + supported languages. |
| `/api/v1/admin/settings` | PUT | Validate → persist. Next call picks it up. |
| `/api/v1/admin/voices` | GET | Static OpenAI realtime voice catalog. |
| `/api/v1/admin/voices/test` | POST | Synthesize a short MP3 sample (OpenAI TTS) in the selected voice + language. Nothing saved; rate-limited to 10/min; approximate preview. |

All API endpoints require the `X-Admin-Token` header.

## Accessing the dashboard on the Asterisk host

The dashboard is a route on the same FastAPI service — no extra process or
port. On the same LAN/VPN, browse `http://<host-ip>:<port>/admin` (open the
port to the LAN subnet only). For occasional remote access, SSH-tunnel:
`ssh -L 8000:localhost:8000 user@host`. For regular remote access, front it
with nginx (TLS + basic auth) — never expose the bare port to the internet.
