Here is where the transfer to a licensed agent (Escalate-to-Human) is implemented across the project:

  Backend (AI side — generates the transfer)

  src/insurance_agent/tools/all_escalate_to_human_tools.py
  - `escalate_to_human_tool` (registered as `escalate_to_human`) sends
    {"event": "escalate_to_human", "reason": "..."} over the call's FastAPI
    WebSocket (taken from the realtime agent's run context). The reason is
    a one-line qualification summary for the licensed agent (e.g.
    "qualified lead: TX 75001, non-smoker, burial, 2 meds (blood pressure)"),
    sanitized to a single quote-free line before sending. The tool never
    closes the WebSocket itself.

  src/insurance_agent/core/prompts.py (instructs the LLM when to call the tool)
  - "Transfer to a Licensed Agent" section: transfer after Phase 6 (product
    explanation) when the customer is still interested, or earlier when the
    customer asks for a licensed agent / real person or insists on an exact
    quote, carrier, or approval decision; speak the transfer line first;
    never call disconnect_websocket_tool afterwards; never promise approval.
    Medical emergencies are NOT transfers (911 + disconnect instead).

  src/insurance_agent/agents/realtime_call_agent.py (registers the tool)
  - `escalate_to_human_tool` is in the `tools` list of `realtime_call_agent`.

  Telephony / AGI side (receives the transfer)

  callapi.py
  - EventType.ESCALATE_TO_HUMAN = "escalate_to_human" enum value.
  - receiver dispatch routes the event to _handle_escalation_event.
  - _handle_escalation_event: quiesces playback, sets AGI variables
    ESCALATE=true and ESCALATE_REASON=<sanitized summary>, then stops the
    receiver so control returns to the dialplan.

  Asterisk dialplan (acts on the AGI variables)

  dialplan.md
  - after EAGI exits, GotoIf checks ${ESCALATE} == "true".
  - escalate label: logs ${ESCALATE_REASON} (the lead summary), then
    transfers to the licensed-agent queue (the Queue/Dial step goes here).

  Browser testing (/app)
  - src/insurance_agent/static/call.html stores the reason when the event
    arrives and shows it as a "Lead summary" card when the call ends.

  End-to-end flow

  LLM decides to transfer → escalate_to_human tool (backend) → WebSocket
  escalate_to_human event → _handle_escalation_event (callapi.py) → sets
  ESCALATE / ESCALATE_REASON channel vars → AGI exits → dialplan's GotoIf
  branches to the escalate label → licensed agent.
