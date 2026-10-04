from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import uvicorn

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from agents import set_tracing_disabled

from insurance_agent.api.v1.main import api_router
from insurance_agent.admin_dashboard import page_router as admin_page_router
from insurance_agent.core.config import configuration
from insurance_agent.core.knowledge_base import get_knowledge_base
from insurance_agent.core.utils.logger import logger_config


logger = logger_config(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm the embedder and (re)ingest the knowledge base. The content
    # fingerprint makes this a no-op when the source is unchanged, so updating
    # the KB is just: edit data/final_expense_faq.md -> restart the server.
    try:
        chunks = await asyncio.to_thread(lambda: get_knowledge_base().ingest())
        logger.info(f"Knowledge base ready ({chunks} chunks).")
    except Exception as e:
        logger.error(f"Knowledge base ingestion failed: {e}", exc_info=True)
    yield
    logger.info("Lifespan END")


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


app = FastAPI(
    title=configuration.PROJECT_NAME,
    version=configuration.VERSION,
    description=configuration.DESCRIPTION or "",
    lifespan=lifespan,
    docs_url=f"{configuration.API_STR}/docs",
    openapi_url=f"{configuration.API_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    servers=[
        {"url": "http://localhost:8000", "description": "Development Server"},
    ],
)

# Set all CORS enabled origins
if configuration.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            str(origin).strip("/") for origin in configuration.BACKEND_CORS_ORIGINS
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=configuration.API_STR)
app.include_router(admin_page_router)  # serves the /admin dashboard page



# Browser call page: talks to /api/v1/realtime/call-session directly over a WebSocket.
# tags is required even off-schema: custom_generate_unique_id reads tags[0]
@app.get("/app", include_in_schema=False, tags=["Call"])
async def call_page():
    return FileResponse(_STATIC_DIR / "call.html", media_type="text/html")


@app.get("/", include_in_schema=False, tags=["Call"])
async def root():
    return RedirectResponse("/app")


def main():
    set_tracing_disabled(not configuration.ENABLE_TRACING)
    uvicorn.run(
        "insurance_agent.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
