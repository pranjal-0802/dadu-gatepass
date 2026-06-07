from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base

import os
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./gatepass.db")
# Railway PostgreSQL URLs use postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def init_db():
    """Creates all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)

def get_db():
    """
    FastAPI dependency. Yields a DB session per request, closes it after.
    Usage in router: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()