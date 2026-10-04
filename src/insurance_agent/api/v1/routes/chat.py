from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agents import Runner
from openai.types.responses import ResponseTextDeltaEvent, EasyInputMessageParam

from insurance_agent.core.utils.logger import logger_config
from insurance_agent.agents.chat_agent import chat_agent

logger = logger_config(__name__)

router = APIRouter()


@router.post("/stream", response_class=StreamingResponse)
async def stream_chat(messages: list[EasyInputMessageParam]):
    result = Runner.run_streamed(starting_agent=chat_agent, input=messages)

    async def event_generator():
        async for event in result.stream_events():
            if event.type == "raw_response_event" and isinstance(
                event.data, ResponseTextDeltaEvent
            ):
                yield event.data.delta

    return StreamingResponse(event_generator())
