from datetime import date, datetime, timezone

from sqlalchemy import (CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    positions: Mapped[list["Position"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Position(Base):
    """Per-user, per-symbol details: sector, company name and the latest known price.

    Quantity and average cost are NOT stored here. They are always derived from transactions
    (single source of truth), so they can never drift out of sync.
    """

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_position_user_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    company_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sector: Mapped[str] = mapped_column(String(50), default="Other")
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # market | manual | transaction
    price_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="positions")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("type IN ('BUY','SELL')", name="ck_txn_type"),
        CheckConstraint("quantity > 0", name="ck_txn_qty_positive"),
        CheckConstraint("price > 0", name="ck_txn_price_positive"),
        CheckConstraint("fees >= 0", name="ck_txn_fees_nonneg"),
        Index("ix_txn_user_date", "user_id", "trade_date"),
        Index("ix_txn_user_symbol", "user_id", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    company_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    type: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    trade_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import | legacy
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    owner: Mapped["User"] = relationship(back_populates="transactions")


class PriceHistory(Base):
    """Daily closing prices from the market data provider. Shared by all users (public market data)."""

    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("symbol", "price_date", name="uq_price_symbol_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    price_date: Mapped[date] = mapped_column(Date)
    close: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="market")


class PortfolioSnapshot(Base):
    """A value actually recorded on the day prices were refreshed (as opposed to reconstructed later)."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "snap_date", name="uq_snapshot_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    snap_date: Mapped[date] = mapped_column(Date)
    market_value: Mapped[float] = mapped_column(Float)
    invested: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="recorded")


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="ck_goal_target"),
        CheckConstraint("years >= 1 AND years <= 50", name="ck_goal_years"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    target_amount: Mapped[float] = mapped_column(Float)
    years: Mapped[int] = mapped_column(Integer)
    expected_return_pct: Mapped[float] = mapped_column(Float, default=10.0)
    monthly_sip: Mapped[float] = mapped_column(Float, default=0.0)
    starting_amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # None = use portfolio value
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    theme: Mapped[str] = mapped_column(String(10), default="system")  # light | dark | system
    default_period: Mapped[str] = mapped_column(String(4), default="ALL")
    benchmark_symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ImportBatch(Base):
    """A parsed upload waiting for the user to confirm or cancel."""

    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    records_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | confirmed | cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RefreshToken(Base):
    """Only a SHA-256 hash of the token is stored, so a database leak does not leak sessions."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    """Every change to a user's data is recorded here (standard in financial software)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
