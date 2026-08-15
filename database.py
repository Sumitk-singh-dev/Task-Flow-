"""
database.py — SQLAlchemy engine, session factory, and FastAPI dependency.

Credentials are loaded from a .env file (never hard-coded here).
Copy .env.example → .env and fill in your real DATABASE_URL.
"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from models import Base

# Load variables from .env file (if it exists)
load_dotenv()

# Read DATABASE_URL from environment; raise a clear error if missing
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Create a .env file based on .env.example."
    )

engine = create_engine(
    DATABASE_URL,
    echo=False,         # Set to True temporarily if you need to debug SQL queries
    pool_pre_ping=True, # Detect stale connections automatically (important for cloud DBs)
    pool_size=10,       # Number of connections to keep open
    max_overflow=20,    # Additional connections when pool is full
    pool_recycle=3600,  # Recycle connections after 1 hour (prevents timeout issues)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# SQLite does not enforce foreign keys (including ON DELETE CASCADE) unless
# explicitly told to on every connection. Without this, models.py's
# passive_deletes=True relationships would silently stop cascading deletes
# on SQLite (rows would just be orphaned instead of removed). This is a
# no-op for Postgres/MySQL, which enforce foreign keys by default.
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db():
    """
    Yield a SQLAlchemy session, then close it after the request completes.
    Used via FastAPI's Depends() in endpoint functions.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()