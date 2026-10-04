exten => 3333,1,Verbose(1, "test call ...")
   same => n,Answer()
   same => n,NoOp(Original UNIQUEID: ${UNIQUEID})
   same => n,Set(CLEAN_UNIQUEID=${CUT(UNIQUEID,.,1)}${CUT(UNIQUEID,.,2)})
   same => n,Set(first_name=abbasi)
   same => n,Set(dob=1955-05-15)
   same => n,Set(BNUM=${CALLERID(num)})
   same => n,Set(state=Texas)
   ; args: call id, first name, DOB, caller number (optional), state (optional)
   same => n,EAGI(/var/lib/asterisk/agi-bin/insurance_agent/callapi.py,${CLEAN_UNIQUEID},${first_name},${dob},${BNUM},${state})
   ; After AGI exits, check if the AI requested a transfer to a licensed agent
   same => n,GotoIf($["${ESCALATE}" = "true"]?escalate)
   same => n,Hangup()

   same => n(escalate),Verbose(1, "Transferring to licensed agent. Lead: ${ESCALATE_REASON}")
   ; No licensed agent is connected yet: the AI has already spoken the transfer
   ; line, so just end the call. To enable live transfer later, set
   ; LA_TRANSFER_ENABLED=true in the backend .env and replace Hangup() with e.g.
   ; same => n,Queue(licensed_agents) or same => n,Dial(PJSIP/la-queue)
   same => n,Hangup()
