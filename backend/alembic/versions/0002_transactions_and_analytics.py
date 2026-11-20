"""Transactions, positions, price history, snapshots, goals, preferences, sessions, import batches.

DATA SAFETY
  * Nothing is dropped. The old `holdings` table is left exactly as it was (it becomes a read-only backup).
  * Every legacy holding becomes one BUY transaction (quantity x buy_price, no fees) plus a position that
    keeps its sector and the price you had entered. The original buy date was never stored, so the
    transaction is dated on the migration day and says so in its note.
  * Re-running is safe: legacy rows are only converted when no legacy transaction exists yet.

Revision ID: 0002
Revises: 0001
"""
from datetime import date, datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _create_if_missing(insp, name, *cols_and_constraints, indexes=()):
    """Create the table and its indexes only when the table does not exist yet."""
    if insp.has_table(name):
        return
    op.create_table(name, *cols_and_constraints)
    for idx_name, cols in indexes:
        op.create_index(idx_name, name, cols)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # users.display_name
    if "display_name" not in [c["name"] for c in insp.get_columns("users")]:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("display_name", sa.String(80), nullable=True))

    uid = lambda: sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # noqa: E731

    _create_if_missing(
        insp, "positions",
        sa.Column("id", sa.Integer, primary_key=True), uid(),
        sa.Column("symbol", sa.String(20), nullable=False), sa.Column("company_name", sa.String(120)),
        sa.Column("sector", sa.String(50), nullable=False, server_default="Other"),
        sa.Column("current_price", sa.Float), sa.Column("prev_close", sa.Float),
        sa.Column("price_source", sa.String(20)), sa.Column("price_updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "symbol", name="uq_position_user_symbol"),
        indexes=[("ix_positions_user_id", ["user_id"])])

    _create_if_missing(
        insp, "transactions",
        sa.Column("id", sa.Integer, primary_key=True), uid(),
        sa.Column("symbol", sa.String(20), nullable=False), sa.Column("company_name", sa.String(120)),
        sa.Column("type", sa.String(4), nullable=False), sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("price", sa.Float, nullable=False), sa.Column("fees", sa.Float, nullable=False, server_default="0"),
        sa.Column("trade_date", sa.Date, nullable=False), sa.Column("note", sa.String(255)),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("type IN ('BUY','SELL')", name="ck_txn_type"),
        sa.CheckConstraint("quantity > 0", name="ck_txn_qty_positive"),
        sa.CheckConstraint("price > 0", name="ck_txn_price_positive"),
        sa.CheckConstraint("fees >= 0", name="ck_txn_fees_nonneg"),
        indexes=[("ix_txn_user_date", ["user_id", "trade_date"]), ("ix_txn_user_symbol", ["user_id", "symbol"])])

    _create_if_missing(
        insp, "price_history",
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("price_date", sa.Date, nullable=False), sa.Column("close", sa.Float, nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="market"),
        sa.UniqueConstraint("symbol", "price_date", name="uq_price_symbol_date"),
        indexes=[("ix_price_history_symbol", ["symbol"])])

    _create_if_missing(
        insp, "portfolio_snapshots",
        sa.Column("id", sa.Integer, primary_key=True), uid(), sa.Column("snap_date", sa.Date, nullable=False),
        sa.Column("market_value", sa.Float, nullable=False), sa.Column("invested", sa.Float, nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="recorded"),
        sa.UniqueConstraint("user_id", "snap_date", name="uq_snapshot_user_date"),
        indexes=[("ix_portfolio_snapshots_user_id", ["user_id"])])

    _create_if_missing(
        insp, "goals",
        sa.Column("id", sa.Integer, primary_key=True), uid(), sa.Column("name", sa.String(80), nullable=False),
        sa.Column("target_amount", sa.Float, nullable=False), sa.Column("years", sa.Integer, nullable=False),
        sa.Column("expected_return_pct", sa.Float, nullable=False, server_default="10"),
        sa.Column("monthly_sip", sa.Float, nullable=False, server_default="0"), sa.Column("starting_amount", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("target_amount > 0", name="ck_goal_target"),
        sa.CheckConstraint("years >= 1 AND years <= 50", name="ck_goal_years"),
        indexes=[("ix_goals_user_id", ["user_id"])])

    _create_if_missing(
        insp, "user_preferences",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("theme", sa.String(10), nullable=False, server_default="system"),
        sa.Column("default_period", sa.String(4), nullable=False, server_default="ALL"),
        sa.Column("benchmark_symbol", sa.String(20)),
    )

    _create_if_missing(
        insp, "import_batches",
        sa.Column("id", sa.String(36), primary_key=True), uid(), sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("records_json", sa.Text, nullable=False), sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        indexes=[("ix_import_batches_user_id", ["user_id"])])

    _create_if_missing(
        insp, "refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True), uid(), sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        indexes=[("ix_refresh_tokens_user_id", ["user_id"])])

    _convert_legacy_holdings(bind)


def _convert_legacy_holdings(bind) -> None:
    insp = sa.inspect(bind)
    if not insp.has_table("holdings"):
        return
    holdings = sa.table("holdings", sa.column("id"), sa.column("user_id"), sa.column("symbol"), sa.column("sector"),
                        sa.column("quantity"), sa.column("buy_price"), sa.column("current_price"))
    txns = sa.table("transactions", sa.column("user_id"), sa.column("symbol"), sa.column("type"), sa.column("quantity"), sa.column("price"),
                    sa.column("fees"), sa.column("trade_date"), sa.column("note"), sa.column("source"), sa.column("created_at"), sa.column("updated_at"))
    positions = sa.table("positions", sa.column("user_id"), sa.column("symbol"), sa.column("sector"), sa.column("current_price"),
                         sa.column("price_source"), sa.column("price_updated_at"))

    already = bind.execute(sa.select(sa.func.count()).select_from(txns).where(txns.c.source == "legacy")).scalar()
    if already:
        return
    rows = bind.execute(sa.select(holdings.c.id, holdings.c.user_id, holdings.c.symbol, holdings.c.sector, holdings.c.quantity,
                                  holdings.c.buy_price, holdings.c.current_price).order_by(holdings.c.id)).fetchall()
    now, today = datetime.now(timezone.utc), date.today()
    seen: set = set()
    for hid, user_id, symbol, sector, qty, buy, cur in rows:
        symbol = (symbol or "").strip().upper()
        if not symbol or not qty or qty <= 0 or not buy or buy <= 0:
            continue  # cannot satisfy the new constraints; the row stays untouched in `holdings`
        bind.execute(txns.insert().values(
            user_id=user_id, symbol=symbol, type="BUY", quantity=qty, price=buy, fees=0.0, trade_date=today,
            note=f"Migrated from legacy holding #{hid} (original buy date was not stored)", source="legacy", created_at=now, updated_at=now))
        key = (user_id, symbol)
        if key in seen:  # same symbol added twice: keep the latest sector/price entered
            bind.execute(positions.update().where((positions.c.user_id == user_id) & (positions.c.symbol == symbol))
                         .values(sector=sector or "Other", current_price=cur, price_source="manual", price_updated_at=now))
        else:
            seen.add(key)
            bind.execute(positions.insert().values(user_id=user_id, symbol=symbol, sector=sector or "Other", current_price=cur,
                                                   price_source="manual", price_updated_at=now))


def downgrade() -> None:
    # Only the new tables are removed. Legacy `holdings` was never modified, so no data is lost.
    for t in ("refresh_tokens", "import_batches", "user_preferences", "goals", "portfolio_snapshots", "price_history", "transactions", "positions"):
        op.drop_table(t)
    with op.batch_alter_table("users") as batch:
        batch.drop_column("display_name")
