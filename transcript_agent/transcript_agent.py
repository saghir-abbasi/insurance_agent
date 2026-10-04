import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from agents import (
    Agent,
    AsyncOpenAI,
    OpenAIChatCompletionsModel,
    Runner,
    set_tracing_disabled,
)
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class RefinementResult(BaseModel):
    """Structured output returned by the refiner agent."""

    refined_text: str  # Full cleaned transcript + lead summary (the formatted block)
    do_not_call: bool  # True if the customer asked not to be contacted again
    do_not_call_quote: str  # The exact customer phrase that triggered it ("" if none)


# Configuration (from .env / environment; this script also runs standalone
# on the Asterisk host, spawned by callapi.py, hence load_dotenv above).
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError(
        "OPENAI_API_KEY is not set. Add it to the .env next to this script "
        "or export it in the environment."
    )

model = os.getenv("TRANSCRIPT_MODEL", "gpt-5-nano-2025-08-07")
ext_client = AsyncOpenAI(api_key=openai_api_key)
ext_model = OpenAIChatCompletionsModel(model=model, openai_client=ext_client)
set_tracing_disabled(True)

agent = Agent(
    name="TranscriptRefiner",
    instructions=(
        """
            You are an expert insurance sales call transcript analyst for an AI call center dashboard.
            The calls are Final Expense whole life insurance qualification calls: the AI agent (first agent)
            confirms the customer's details, asks qualification questions, explains the product, and
            transfers interested customers to a licensed agent (LA).

            Your task is to convert noisy raw event-based transcripts into a clean, professional,
            accurate conversation record plus a lead qualification summary for the licensed agent.

            STRICT RULES:
            1. Preserve the exact meaning of both agent and customer responses.
            2. NEVER invent answers, health conditions, medications, personal details, or responses that are not explicitly present.
            3. Fix grammar, punctuation, encoding issues, and ASR noise.
            Example: "AlÃ³" -> "Hello?"
            4. Merge repeated assistant prompts caused by latency, retries, or interruption.
            5. Remove duplicated questions if the same question was asked repeatedly without a meaningful new variation.
            6. Keep the conversation in chronological order.
            7. Clearly label each line as:
            Agent:
            Customer:
            8. Convert unclear phrases into the most likely clean wording ONLY if confidence is high.
            Otherwise mark as:
            [unclear]
            9. If the customer response appears unrelated because of ASR error, preserve it but mark:
            [possibly misheard]
            10. Do NOT infer eligibility, underwriting decisions, or details that are not explicitly stated.
            11. If information for any summary field is missing, explicitly write: "Not mentioned".
            12. Keep the output concise, structured, and suitable for licensed-agent dashboard review.

            DO-NOT-CALL DETECTION:
            13. Determine whether the CUSTOMER explicitly asked NOT to be contacted/called again.
            Set "do_not_call" = true ONLY if the customer clearly expresses an opt-out, e.g.:
            "do not disturb", "don't call me again", "stop calling me", "remove me from your list",
            "no me llamen mas", "please don't contact me", or any clear equivalent / paraphrase
            in any language.
            14. Casual phrases like "not now", "call me later", "I'm busy", "not interested", or
            scheduling a callback are NOT opt-outs -> do_not_call = false.
            15. When do_not_call = true, copy the exact triggering customer phrase into
            "do_not_call_quote". Otherwise set "do_not_call_quote" to an empty string.
            16. An agent/assistant line NEVER triggers do_not_call; only the customer's own words count.

            OUTPUT (return the structured object):
            - "refined_text": the FULL formatted block below (Transcript + Lead Summary), exactly as specified.
            - "do_not_call": boolean per rules 13-16.
            - "do_not_call_quote": string per rule 15.

            FORMAT FOR "refined_text" (strictly follow the headings format):

            1.Transcript:
            Agent: ...
            Customer: ...

            2.Contact & Eligibility:
            - Name confirmed: Yes / No / Not mentioned
            - State: ...
            - ZIP code: ...
            - Date of birth: ...
            - Height / weight: ...
            - Smoker status: Smoker / Non-smoker / Not mentioned
            - Bank account type: Checking / Savings / Not mentioned
            - Same state for past 12 months: Yes / No / Not mentioned

            3.Coverage Goal:
            - Primary goal: Burial / Cremation / Leave money behind / Not mentioned
            - First or additional policy: ...
            - Existing coverage mentioned: ...

            4.Health Qualification:
            - Hospitalized / nursing facility / bed / wheelchair: Yes / No / Not mentioned
            - Heart attack, stroke, cancer, or kidney dialysis: Yes / No / Not mentioned (include details only if stated)
            - Oxygen, nebulizer, CHF, dementia, AIDS, or HIV: Yes / No / Not mentioned (include details only if stated)
            - Medications per day: ...
            - Medication purposes: ...

            5.Questions & Objections:
            - Product questions the customer asked and concerns or objections raised.
            - If none mentioned, write: Not mentioned

            6.Call Outcome:
            - One of: Transferred to licensed agent / Not interested / Callback requested / Do-not-call requested / Voicemail or IVR / Call dropped / Incomplete
            - Next step stated in the call (do NOT add new recommendations).
            """
    ),
    model=ext_model,
    output_type=RefinementResult,
)

DB_BASE_URL = os.getenv("DB_BASE_URL", "http://23.158.200.139:5002")
DB_LOGIN_ENDPOINT = "/api/token"
DB_TRANSCRIPT_ENDPOINT = "/api/Caller/Addtranscript"
DB_DONOTCALL_ENDPOINT = "/api/Caller/AddBlacklistNumbers"
DB_USERNAME = os.getenv("DB_USERNAME", "MaxAdmin.com")
DB_PASSWORD = os.getenv("DB_PASSWORD", "MaxAdmin.com")


def _get_db_token() -> str:
    """Authenticate against the remote DB and return a bearer token."""
    login_url = f"{DB_BASE_URL}{DB_LOGIN_ENDPOINT}"
    login_resp = requests.post(
        login_url,
        headers={"Content-Type": "application/json"},
        json={"username": DB_USERNAME, "password": DB_PASSWORD},
        timeout=30,
    )
    login_resp.raise_for_status()
    token_data = login_resp.json()
    token = token_data.get("token") or token_data.get("access_token")
    if not token:
        raise RuntimeError("Auth token not found in login response")
    return token


def upload_transcript_to_db(refined_text: str, session_id: str, token: str = None):
    """Authenticate (if needed) and upload the refined transcript to the remote database."""
    if token is None:
        token = _get_db_token()

    # Convert session_id to integer (e.g. "1776263861_194" -> 1776263861194)
    numeric_session_id = int(session_id.replace("_", "").replace(".", ""))

    # Upload transcript

    payload = [
        {
            "full_transcript": refined_text,
            "remarks": "Call Transcript & Lead Summary",
            "session_id": numeric_session_id,
            "transcript_datetime": datetime.now(timezone.utc).isoformat(),
        }
    ]
    upload_url = f"{DB_BASE_URL}{DB_TRANSCRIPT_ENDPOINT}"
    upload_resp = requests.post(
        upload_url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json=payload,
        timeout=30,
    )
    upload_resp.raise_for_status()
    return upload_resp.json()


def upload_do_not_call_to_db(
    phone_number: str,
    quote: str,
    firstname: str = "",
    lastname: str = "",
    token: str = None,
):
    """Add the caller's phone number to the remote blacklist so future calls
    are filtered out. `quote` is the exact customer phrase that triggered it.
    """
    if token is None:
        token = _get_db_token()

    # The remarks DB column is now nvarchar(MAX), so length is no longer a concern.
    # Still collapse to a single line to avoid newline artifacts in the dashboard.
    safe_quote = " ".join(str(quote).split())
    remarks = f"Auto-blacklisted by AI call agent (customer opt-out): {safe_quote}"

    payload = [
        {
            "firstName": firstname or "",
            "lastName": lastname or "",
            "phone_number": phone_number,
            "remarks": remarks,
            "createdBy": "AI Call Agent",
        }
    ]
    url = f"{DB_BASE_URL}{DB_DONOTCALL_ENDPOINT}"
    resp = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json=payload,
        timeout=30,
    )
    if not resp.ok:
        # Surface the server's validation message instead of a bare "400 Client Error".
        raise RuntimeError(
            f"Blacklist upload failed: {resp.status_code} {resp.reason} | "
            f"body={resp.text[:500]} | payload={json.dumps(payload)}"
        )
    return resp.json()


async def refine_transcript(
    raw_file_path: str,
    target_dir: str,
    session_id: str = None,
    firstname: str = None,
    date_of_birth: str = None,
    phone_number: str = None,
):
    """
    Reads from raw_file_path and saves the refined version into target_dir.
    If session_id is provided, also uploads the refined transcript to the remote database.
    If the customer asked not to be called again, adds the caller's phone number to
    the remote blacklist for future filtering.
    """

    raw_path = Path(raw_file_path)
    output_path = Path(target_dir) / "refined_transcript.txt"

    if not raw_path.exists():
        return f"Error: Raw file not found at {raw_file_path}"

    # Parse JSON lines
    raw_text = ""
    with open(raw_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
                role = "Agent" if "assistant" in data.get("event", "") else "Customer"
                text = data.get("transcript", "").strip()
                if text:
                    raw_text += f"{role}: {text}\n"
            except Exception:
                continue

    if not raw_text.strip():
        return "Error: No transcript content found to refine."

    # Process with AI -> structured RefinementResult
    prompt = f"Rewrite and clean the following conversation:\n\n{raw_text}"
    result = await Runner.run(agent, prompt)
    refinement: RefinementResult = result.final_output

    # Save to the specific target directory
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(refinement.refined_text)

    if refinement.do_not_call:
        print(
            f"[TranscriptAgent] DO-NOT-CALL detected for session {session_id} "
            f"(caller={firstname}/{date_of_birth}): {refinement.do_not_call_quote!r}"
        )

    # Upload to remote database if session_id was provided
    if session_id:
        try:
            db_result = upload_transcript_to_db(refinement.refined_text, session_id)
            print(
                f"[TranscriptAgent] Uploaded to DB for session {session_id}: {db_result}"
            )
        except Exception as e:
            print(f"[TranscriptAgent] DB upload failed for session {session_id}: {e}")

    # Blacklist caller's phone number for future filtering
    if refinement.do_not_call and phone_number:
        try:
            dnc_result = upload_do_not_call_to_db(
                phone_number=phone_number,
                quote=refinement.do_not_call_quote,
                firstname=firstname or "",
            )
            print(f"[TranscriptAgent] Blacklisted {phone_number}: {dnc_result}")
        except Exception as e:
            print(f"[TranscriptAgent] Blacklist upload failed for {phone_number}: {e}")
    elif refinement.do_not_call:
        print(
            "[TranscriptAgent] Do-not-call detected but phone_number missing; "
            "cannot blacklist caller for future filtering."
        )

    return str(output_path)
