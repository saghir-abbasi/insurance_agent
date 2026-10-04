from fastapi import APIRouter

from insurance_agent.api.v1.routes import realtime, chat
from insurance_agent.admin_dashboard import router as admin_router

api_router = APIRouter()

api_router.include_router(realtime.router, prefix="/realtime", tags=["Realtime"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])

