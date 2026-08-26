import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.config import Config

DATABASE_URL = Config.DATABASE_URL
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(DATABASE_URL, echo=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
