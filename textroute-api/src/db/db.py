import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.config import Config

DATABASE_URL = Config.DATABASE_URL
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# Statement logging is useful while developing, but it writes every query and
# its bound parameters -- phone numbers, message bodies, login code hashes --
# into the container log, so it stays off unless asked for.
engine = create_engine(DATABASE_URL, echo=Config.SQL_ECHO)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
