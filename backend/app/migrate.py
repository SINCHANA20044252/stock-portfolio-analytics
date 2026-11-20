"""Run Alembic migrations programmatically (used on startup and by `python -m app.migrate`)."""
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parent.parent


def run_migrations() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    run_migrations()
    print("Database is up to date.")
