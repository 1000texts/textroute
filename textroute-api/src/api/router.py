"""Aggregate the API routers by trust boundary."""

from fastapi import APIRouter

from src.api.routes.health import router as health_router
from src.api.routes.moderator.auth import router as auth_router
from src.api.routes.moderator.group_settings import router as group_settings_router
from src.api.routes.moderator.members import router as member_router
from src.api.routes.moderator.moderation import router as moderation_router
from src.api.routes.moderator.requests import router as request_router
from src.api.routes.public.group import router as group_router
from src.api.routes.webhooks.conversation import router as conversation_router
from src.api.routes.webhooks.inbound import router as inbound_router

api_router = APIRouter()
api_router.include_router(health_router)
# Authentication begins unauthenticated, but serves the moderator web app.
api_router.include_router(auth_router)
# Provider callbacks remain separate from browser-facing API routes.
api_router.include_router(inbound_router)
# The simulator reads its conversation with the same webhook secret it sends
# with, which is the only credential it has.
api_router.include_router(conversation_router)
api_router.include_router(group_router)
# Group settings (routing policy) require an authenticated moderator.
api_router.include_router(group_settings_router)
api_router.include_router(moderation_router)
api_router.include_router(request_router)
api_router.include_router(member_router)
