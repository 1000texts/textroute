from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import api_router
from src import models as orm_models  # noqa: F401 — register ORM metadata
from src.config.config import Config

app = FastAPI()

allowed_origins = list(
    dict.fromkeys([Config.MODERATOR_WEB_ORIGIN, *Config.CORS_ALLOWED_ORIGINS])
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
