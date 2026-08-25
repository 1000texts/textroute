from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import api_router
from src.db import models as db_models  # noqa: F401
from src import models as domain_models  # noqa: F401

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
