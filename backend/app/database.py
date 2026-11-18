from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

connect_args = {}
engine_kwargs = {"echo": False}

if "sqlite" in settings.database_url:
    connect_args["check_same_thread"] = False
elif "mssql" in settings.database_url:
    # Microsoft SQL Server connection pooling and execution settings
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["fast_executemany"] = True
else:
    # PostgreSQL / other production databases
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    **engine_kwargs,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a SQLAlchemy database session and
    ensures it is closed after request handling completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection(db: Session) -> bool:
    """
    Execute a minimal query to verify active connectivity with the database engine.
    Compatible with Microsoft SQL Server, PostgreSQL, and SQLite.
    """
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
