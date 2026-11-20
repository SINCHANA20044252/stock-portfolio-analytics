import importlib

import pytest


def test_production_refuses_default_secret(monkeypatch):
    from app import config
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = importlib.reload(config)
    try:
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            cfg.validate_for_production()
        monkeypatch.setenv("SECRET_KEY", "x" * 40)
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
        cfg = importlib.reload(config)
        cfg.validate_for_production()
        assert cfg.COOKIE_SECURE is True and cfg.ENABLE_DOCS is False
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_postgres_urls_are_normalised(monkeypatch):
    pytest.importorskip("sqlalchemy")
    from app import database
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h/db")
    try:
        db = importlib.reload(database)
        assert db.DATABASE_URL.startswith("postgresql+psycopg2://")
    finally:
        monkeypatch.undo()
        importlib.reload(database)
