# Emma — Final Expense Insurance Voice Agent (OpenAI Realtime + Asterisk)

End-to-end outbound voice AI agent for **Final Expense whole life insurance**
lead qualification, built on the **OpenAI Agents SDK Realtime API**. Emma is
the *first agent* on the call: she confirms the customer's details, asks the
qualification questions, explains the Final Expense product, and then
**warm-transfers the qualified customer to a licensed agent (LA)**. Her script
ends at the transfer.

A phone call lands on **Asterisk**, the AGI bridge (`callapi.py`) streams the
call's audio over a WebSocket to this **FastAPI backend**, which runs a
`RealtimeAgent` (`gpt-realtime`) for speech-to-speech conversation, tool
calling, and RAG-grounded answers.

```
PSTN customer
   │
   ▼
Asterisk (EAGI)  ──spawns──►  callapi.py  (repo root)
                                      │
                                      │  WebSocket: base64 audio frames
                                      ▼
                           FastAPI backend  (src/insurance_agent/)
                                      │
                                      │  OpenAI Realtime session
                                      ▼
                     RealtimeAgent "Emma" (gpt-realtime) ──tools──►  Chroma RAG (product FAQ),
                                                                     escalate_to_human (LA transfer),
                                                                     disconnect
on hangup: callapi.py ──spawns──► transcript_agent/run_refinement.py
                                  (cleanup + lead qualification summary + do-not-call detection)
```

## Source material

The agent's behavior is derived from the two files in `docs/`:

| File | Used for |
|---|---|
| `docs/script.md` | The first-agent call script (Sections 1–7). It is turned into Emma's system prompt in `core/prompts.py`. |
| `docs/sample_questions.md` | Sample product Q&A. Copied to `data/final_expense_faq.md`, which is the RAG knowledge-base source. |

## Call flow (from `docs/script.md`)

| Phase | What Emma does |
|---|---|
| 1. Opening & call reason | Confirms she is speaking with the customer, introduces herself as a product specialist, explains the call is about Final Expense coverage, asks permission, confirms state and ZIP code. |
| 2. Explanation & rapport | Explains the independent brokerage; asks the incentive questions: smoker / non-smoker, checking or savings account, same state for the past 12 months. |
| 3. Privacy & basic qualification | Gives the confidentiality notice; confirms date of birth; asks height and weight. |
| 4. Coverage goal | Burial, cremation, or leaving money behind; first policy or an additional one. |
| 5. Health qualification | Yes/No questions: hospitalized / nursing facility / bed / wheelchair; heart attack, stroke, cancer, dialysis; oxygen, nebulizer, CHF, dementia, AIDS/HIV; number of daily medications and what they are for. Answers are recorded and never used by Emma to approve or decline. |
| 6. Product explanation | Final Expense whole life: stays in force per policy terms, level benefits and premiums per policy terms, no medical exam or blood test, cash value. |
| 7. LA transfer | Speaks the transfer line, then calls `escalate_to_human` with a one-line qualification summary. Never promises approval, a carrier, or a price; never hangs up after transferring. |

Customers who are not interested get a polite two-turn close. A customer
who asks not to be called again is flagged by the post-call refinement and
blacklisted (see below).

## Layout

| Path | What it is |
|---|---|
| `callapi.py` | Asterisk AGI script. One process per call. Bridges EAGI (FD 3) audio to the backend WebSocket; saves per-call audio + transcript; sets `ESCALATE` dialplan vars on LA transfer; spawns transcript refinement on hangup. |
| `src/insurance_agent/` | FastAPI service: realtime session manager, agent + tools, browser call page (`static/call.html`), ChromaDB knowledge base, admin dashboard. |
| `src/insurance_agent/core/prompts.py` | Emma's default system prompt (template), `AGENT_NAME`, `COMPANY_DESCRIPTION`. |
| `src/insurance_agent/admin_dashboard/` | `/admin` dashboard: runtime control of voice, language, and system prompt. |
| `data/` | Runtime data: `final_expense_faq.md` (RAG source), `chroma/` (vector store, rebuilt automatically), `agent_settings.json` (admin settings). |
| `docs/` | Source material: call script + sample Q&A. |
| `transcript_agent/` | Post-call transcript refinement, spawned by `callapi.py` on hangup. |
| `dialplan.md` | Example Asterisk dialplan incl. the LA-transfer branch. |

## Running the system

```bash
pip install uv          # if you don't have it
uv sync
# create/edit .env — needs at least OPENAI_API_KEY; ADMIN_API_TOKEN enables /admin
uv run server           # → http://localhost:8000
```

- **Browser testing (no Asterisk):** open `http://localhost:8000/app` and click **Start Call** to talk to Emma. A random mock customer (name, DOB, state) is used for each session.
- **Admin dashboard:** `http://localhost:8000/admin` (requires `ADMIN_API_TOKEN`).
- **API docs:** `http://localhost:8000/api/v1/docs`.

### `.env` cheatsheet

```ini
OPENAI_API_KEY="sk-..."                       # required
ENVIRONMENT="development"                     # "production" switches audio to g711_alaw
REALTIME_MODEL="openai/gpt-realtime-2"
REALTIME_TRANSCRIBE_MODEL="gpt-4o-transcribe"
ADMIN_API_TOKEN="<long-random-secret>"        # enables the /admin dashboard
TRANSCRIPT_MODEL="gpt-5-nano-2025-08-07"      # post-call refinement agent
LA_TRANSFER_ENABLED="false"                   # false: end the call after the transfer line (no live agent yet)
# DB_BASE_URL / DB_USERNAME / DB_PASSWORD     # transcript upload target (optional)
```

## Call context (per-call customer data)

The WebSocket endpoint `/api/v1/realtime/call-session/{session_id}` accepts
query parameters that are substituted into the prompt template:

| Query param | Prompt placeholder | Notes |
|---|---|---|
| `user_name` | `{user_info.user_name}` | Customer's first name. |
| `date_of_birth` | `{user_info.date_of_birth}` | Emma asks the customer to confirm it. |
| `state` | `{user_info.state}` | Optional. If known, Emma confirms it; otherwise she asks. |
| `user_id` | — | Tracking only. |

Other placeholders: `{name}` → `AGENT_NAME` ("Emma"), `{company}` →
`COMPANY_DESCRIPTION` ("an independent insurance brokerage"), `{language}` →
the admin dashboard language directive. All are resolved with targeted
`str.replace` (never `str.format`).

## RAG / Knowledge base

Emma answers off-script product questions (whole life vs. term, cash value,
eligibility after a prior decline, the review period, etc.) by retrieving
from a Chroma vector store built from `data/final_expense_faq.md`
(`core/knowledge_base/rag.py`; agent tool in `tools/knowledge_base_tools.py`).

- Supported source formats: **Markdown / text** (split per Q&A block or heading) and **PDF** (split per page).
- Embeddings: `fastembed` `BAAI/bge-base-en-v1.5`, cosine distance, collection `final_expense_kb` under `data/chroma/`.
- The tool returns up to 3 snippets with score ≥ 0.55; below that it tells the agent to say the detail isn't available and that the licensed agent can cover it.
- **Ingestion runs automatically at server startup** and is fingerprint-checked (SHA-256 of the source file), so it's a no-op unless the file changed.
- The prompt forbids Emma from quoting exact premiums or naming a carrier as a promise, even when the FAQ contains them; pricing and carrier questions are left to the licensed agent.

**Updating the knowledge base:** edit or replace `data/final_expense_faq.md`
(add more `Q<n>:` blocks) → restart the server. If you change chunking
constants or the embedding model in `rag.py` (fingerprint unchanged), force a
rebuild once:

```bash
uv run python -c "from insurance_agent.core.knowledge_base import get_knowledge_base; print(get_knowledge_base().ingest(force=True))"
```

## Transfer to licensed agent (escalate to human)

```
LLM calls escalate_to_human tool (backend)
   ▼  WebSocket {"event": "escalate_to_human", "reason": "..."}
callapi.py: quiesce playback → SET VARIABLE ESCALATE=true, ESCALATE_REASON=<reason>
   ▼  AGI exits
dialplan: GotoIf ${ESCALATE} == "true" → transfer to licensed agent (see dialplan.md)
```

The tool lives in `tools/all_escalate_to_human_tools.py`. Emma transfers:

- after Section 6, when the customer is still interested (the normal path; the reason carries a one-line qualification summary, e.g. `qualified lead: non-smoker, burial, 3 meds (BP, diabetes)`), and
- at any point if the customer asks for a licensed agent / real person, or asks for an exact quote or a carrier-specific answer.

She speaks a short handoff line first. The tool prefixes the summary with
the customer's name (`Customer: John Doe | qualified lead: ...`).

**No live agent yet (`LA_TRANSFER_ENABLED=false`, the default):** the tool
waits for the transfer line to finish playing, sends the summary
(`escalate_to_human` event → `ESCALATE_REASON`), and then **ends the call**.
Once a licensed-agent queue exists, set `LA_TRANSFER_ENABLED=true` in `.env`
and add the `Queue`/`Dial` step in the dialplan; the tool then keeps the
line open for the transfer. The WebSocket event name and AGI variables are
unchanged from the original project.

**Browser UI (`/app`):** no live transcript is shown. When the call ends,
a **Lead summary** card appears (customer name + qualification answers) for
the licensed agent, or a "not transferred" note if the customer was not
transferred. See `ESCALATE_HUMAN_LOGIC.md`
for the file-by-file map.

## Admin dashboard

Single page at **`/admin`** for changing the agent's **voice** (OpenAI realtime
voices: Marin, Cedar, Alloy, Ash, Ballad, Coral, Echo, Sage, Shimmer, Verse),
**language** (16 fixed languages or *Caller Language* = follow the caller within
the supported set), and **system prompt** (template with a `{language}`
placeholder), with no code changes and no restart.

Settings persist in `data/agent_settings.json` (atomic writes, seeded from the
defaults on first run). There is no remote "apply" step: every new call reads
the store, so **changes take effect on the next call**; in-progress calls are
unaffected. A ▶ preview button synthesizes Emma's opening line via OpenAI TTS
(approximate; Marin/Cedar preview with a stand-in voice; rate-limited 10/min).

> The stored prompt overrides `core/prompts.py`. After editing `SYSTEM_PROMPT`
> in code, delete `data/agent_settings.json` (it re-seeds on the next call) or
> paste the new prompt in the dashboard.

Auth: set `ADMIN_API_TOKEN` in `.env`; all admin API calls require the
`X-Admin-Token` header. Without the env var the admin API returns `503`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/admin` | GET | Dashboard page (HTML shell). |
| `/api/v1/admin/settings` | GET | Current settings + supported languages. |
| `/api/v1/admin/settings` | PUT | Validate → persist. Next call picks it up. |
| `/api/v1/admin/voices` | GET | Static OpenAI realtime voice catalog. |
| `/api/v1/admin/voices/test` | POST | Short TTS sample in the selected voice + language. |

## Transcript refinement

On hangup, `callapi.py` spawns `transcript_agent/run_refinement.py` as a
detached process. It parses the raw JSONL transcript, uses an Agents-SDK agent
(`TRANSCRIPT_MODEL`) with structured output to produce a cleaned
`Agent:`/`Customer:` transcript plus a **lead qualification summary**
(contact & eligibility answers, coverage goal, health answers, medications,
product questions, call outcome: transferred / not interested / callback /
do-not-call / voicemail) in `refined_transcript.txt`, uploads it to the
dashboard DB, and, if the customer asked not to be called again, adds the
caller's number to the remote blacklist. Credentials and endpoints come from env
(`OPENAI_API_KEY`, `DB_BASE_URL`, `DB_USERNAME`, `DB_PASSWORD`); DB failures
are logged and never block the local save.

## AGI bridge on Asterisk

1. Place the repo (or at least `callapi.py` + `transcript_agent/`) under
   `/var/lib/asterisk/agi-bin/insurance_agent/` and make `callapi.py` executable.
2. Ensure the venv in the `callapi.py` shebang has `websockets` and `pyst2`;
   the refinement spawn uses the same venv python.
3. Point `ws_uri` in `callapi.py:main()` at the backend (default
   `ws://localhost:8002/...`).
4. Wire it into the dialplan with **EAGI** (not AGI, since audio needs FD 3) and the
   LA-transfer branch; see `dialplan.md`. Arguments:
   `EAGI(callapi.py,${CLEAN_UNIQUEID},${first_name},${dob},${BNUM},${state})`.
   `BNUM` (caller number) and `state` are optional.
5. Call logs land in `/var/lib/asterisk/agi-bin/insurance_agent/calls/<call_id>/`
   (`input.wav`, `output.wav`, `transcript.json`, `debug.log`,
   `refined_transcript.txt`, `refinement.log`).

**Audio format note:** the backend uses `pcm16` in development and `g711_alaw`
when `ENVIRONMENT=production`. Verify the format pair against what `callapi.py`
sends from EAGI with one real test call before going live.

## Compliance notes

- Emma identifies as a product specialist, not a licensed agent, and never promises approval, a specific carrier, or a price.
- She does not volunteer technical details, but if a customer sincerely asks whether they are talking to an AI, she does not claim to be human.
- Health answers are collected only to pass to the licensed agent; Emma gives no medical or underwriting judgments.
- Do-not-call requests are honored on the call and propagated to the blacklist after hangup.

## Troubleshooting

- **First caller hears a long pause**: this is the fastembed cold start. The server pre-warms it in `lifespan`; if you bypassed startup, the first RAG query takes ~5–10 s.
- **Stale RAG answers after changing the FAQ**: startup ingestion is fingerprinted. If you changed code rather than the source file, run `ingest(force=True)` (see above).
- **Emma still uses an old script**: `data/agent_settings.json` holds the prompt and overrides the code default. Delete it or update the prompt via the dashboard.
- **Admin API returns 503**: `ADMIN_API_TOKEN` is not set. **401**: the dashboard has the wrong token.
- **Dashboard changes don't affect a call**: changes apply on the **next** call.
- **Transfer doesn't happen**: the AGI only sets `ESCALATE` channel vars; the actual `Dial` to the LA queue lives in your dialplan after the EAGI line. Check `debug.log` for `AGI vars set (ESCALATE=true)`.
- **Refinement never runs**: check `refinement.log` in the call directory. The runner path is resolved relative to `callapi.py` (`./transcript_agent/run_refinement.py`), and `OPENAI_API_KEY` must be present in the environment/.env on the Asterisk host.

## Twilio testing (optional)

To test over Twilio instead of Asterisk, tunnel the local server
(`cloudflared tunnel --url http://localhost:8000`) and point the Twilio
number's voice webhook at the tunnel URL. In trial accounts, calls are only
accepted from Verified Caller IDs.
