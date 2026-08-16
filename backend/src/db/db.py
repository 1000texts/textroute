import os  # OS and environment utilities

from sqlalchemy import create_engine  # DB engine
from sqlalchemy.orm import sessionmaker, declarative_base

from src.config.config import Config  # Sessions and ORM base

DATABASE_URL = Config.DATABASE_URL  # Database connection string

engine = create_engine(DATABASE_URL)  # Create DB engine

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)  # Session factory


def get_db():
    db = SessionLocal()  # Open session
    try:
        yield db  # Provide session
    finally:
        db.close()  # Close session


def exec_db(model_instance):
    db = SessionLocal()  # Open session
    try:
        db.add(model_instance)  # Add instance
        db.commit()  # Commit transaction
        db.refresh(model_instance)  # Refresh instance
        return model_instance  # Return instance
    except Exception as e:
        db.rollback()  # Rollback on error
        print(e)
        raise e
    finally:
        db.close()  # Close session


def execute_query(sql, params):
    db = SessionLocal()  # Open session
    try:
        result = db.execute(sql, params)  # Execute query
        return result  # Return result
    finally:
        db.close()  # Close session
