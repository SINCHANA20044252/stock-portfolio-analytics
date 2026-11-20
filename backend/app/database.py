import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite by default (zero setup). For PostgreSQL set DATABASE_URL, e.g.
#   postgresql+psycopg2://user:password@host:5432/portfolio?sslmode=require
# Hosts such as Render give "postgres://..." which SQLAlchemy 2 no longer accepts; it is rewritten here.
_url = os.getenv("DATABASE_URL", "sqlite:///./portfolio.db")
if _url.startswith("postgres://"):
    _url = "postgresql+psycopg2://" + _url[len("postgres://"):]
elif _url.startswith("postgresql://"):
    _url = "postgresql+psycopg2://" + _url[len("postgresql://"):]
DATABASE_URL = _url

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # pool_pre_ping drops dead connections; for production use sslmode=require in the URL.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=1800)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
