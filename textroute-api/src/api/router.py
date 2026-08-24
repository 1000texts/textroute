from fastapi import APIRouter

from src.api.health import router as health_router
from src.api.webhooks.inbound import router as inbound_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(inbound_router)
