"""Baseline: the schema of version 1 (users, holdings, audit_log).

Existing databases already have these tables (the first version created them with create_all), so each
table is only created when it is missing. Nothing is dropped or changed here.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    if not insp.has_table("holdings"):
        op.create_table(
            "holdings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("symbol", sa.String(20), nullable=False),
            sa.Column("sector", sa.String(50)),
            sa.Column("quantity", sa.Float, nullable=False),
            sa.Column("buy_price", sa.Float, nullable=False),
            sa.Column("current_price", sa.Float, nullable=False),
        )
        op.create_index("ix_holdings_user_id", "holdings", ["user_id"])
    if not insp.has_table("audit_log"):
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, nullable=False),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("detail", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])


def downgrade() -> None:
    pass  # the baseline is never removed
