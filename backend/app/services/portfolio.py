"""Database-aware portfolio services used by the routers. Business rules live in the pure modules
(accounting, performance, risk, sip); this file only loads the signed-in user's rows and feeds them in.

Every function takes `user_id` and filters on it. There is no function that reads another user's data."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

from .. import config
from ..models import PortfolioSnapshot, Position, PriceHistory, Transaction
from . import accounting, market, performance, risk


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes while freshly assigned ones are timezone-aware; make them comparable."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def txn_dict(t: Transaction) -> dict:
    return {"id": t.id, "symbol": t.symbol, "company_name": t.company_name or "", "type": t.type, "quantity": t.quantity,
            "price": t.price, "fees": t.fees or 0.0, "date": t.trade_date, "note": t.note, "source": t.source}


def load_transactions(db: Session, user_id: int) -> list[dict]:
    rows = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    return sorted((txn_dict(t) for t in rows), key=accounting.sort_key)


def load_positions(db: Session, user_id: int) -> dict[str, Position]:
    return {p.symbol: p for p in db.query(Position).filter(Position.user_id == user_id).all()}


def ensure_position(db: Session, user_id: int, symbol: str, company_name: str | None = None, sector: str | None = None,
                    price_hint: float | None = None) -> Position:
    pos = db.query(Position).filter(Position.user_id == user_id, Position.symbol == symbol).first()
    dir_name, dir_sector = market.directory_info(symbol)
    if pos is None:
        pos = Position(user_id=user_id, symbol=symbol, company_name=company_name or dir_name, sector=sector or dir_sector or "Other")
        db.add(pos)
        db.flush()  # autoflush is off: without this, a second call for the same symbol (e.g. two import rows) would not find it
    else:
        if company_name:
            pos.company_name = company_name
        if sector:
            pos.sector = sector
    if price_hint is not None and pos.current_price is None:
        pos.current_price, pos.price_source, pos.price_updated_at = price_hint, "transaction", datetime.now(timezone.utc)
    return pos


def valuation(db: Session, user_id: int) -> dict:
    """Ledger + latest prices for one user. Holdings without any price are reported, not valued at zero."""
    txns = load_transactions(db, user_id)
    ledger = accounting.replay(txns)
    positions = load_positions(db, user_id)
    prices, sectors = {}, {}
    for sym, lot in ledger.lots.items():
        pos = positions.get(sym)
        sectors[sym] = pos.sector if pos else "Other"
        if pos is not None and pos.current_price is not None:
            prices[sym] = pos.current_price
        else:
            prices[sym] = None
    val = accounting.valuate(ledger, prices, sectors)
    for h in val["holdings"]:
        pos = positions.get(h["symbol"])
        h["id"] = pos.id if pos else None
        if pos and pos.company_name:
            h["company_name"] = pos.company_name
        h["price_source"] = pos.price_source if pos else None
        h["price_updated_at"] = _aware(pos.price_updated_at).isoformat() if pos and pos.price_updated_at else None
        prev = pos.prev_close if pos else None
        if prev and h["current_price"] is not None and pos.price_source == "market":
            h["day_change"] = round((h["current_price"] - prev) * h["quantity"], 2)
            h["day_change_pct"] = round((h["current_price"] - prev) / prev * 100, 2)
        else:
            h["day_change"] = h["day_change_pct"] = None
    val["sectors"] = accounting.sector_allocation(val["holdings"])
    val["stocks"] = accounting.stock_allocation(val["holdings"])
    val["pnl_distribution"] = accounting.pnl_distribution(val["holdings"])
    stamps = [_aware(p.price_updated_at) for s, p in positions.items() if p.price_updated_at and s in ledger.lots and ledger.lots[s].quantity > 0]
    val["prices_as_of"] = min(stamps).isoformat() if stamps else None
    val["ledger"] = ledger
    val["transactions"] = txns
    return val


def history_rows(db: Session, symbols: list[str]) -> list[tuple[str, date, float]]:
    if not symbols:
        return []
    rows = db.query(PriceHistory.symbol, PriceHistory.price_date, PriceHistory.close).filter(PriceHistory.symbol.in_(symbols)).all()
    return [(r[0], r[1], r[2]) for r in rows]


def performance_bundle(db: Session, user_id: int, period: str = "ALL", txns: list[dict] | None = None) -> dict:
    txns = txns if txns is not None else load_transactions(db, user_id)
    symbols = sorted({t["symbol"] for t in txns})
    frame = performance.prices_frame(history_rows(db, symbols))
    built = performance.build_series(txns, frame)
    df = built["series"]
    full = df
    df = performance.slice_period(df, period) if not df.empty else df

    bench_sym = config.BENCHMARK_SYMBOL
    brows = db.query(PriceHistory.price_date, PriceHistory.close).filter(PriceHistory.symbol == bench_sym).all()
    bench = pd.Series({pd.Timestamp(d): c for d, c in brows}).sort_index() if brows else None
    comparison = performance.benchmark_comparison(df, bench)
    comparison["benchmark_symbol"] = bench_sym

    return {
        "period": period.upper(),
        "has_data": not df.empty,
        "source": "reconstructed from your transactions and stored daily closing prices",
        "summary": performance.summarize(df),
        "series": performance.series_records(df),
        "weekly": performance.period_returns(df, "W"),
        "monthly": performance.period_returns(df, "ME"),
        "comparison": comparison,
        "notes": built["notes"],
        "excluded_symbols": built["excluded_symbols"],
        "_df": df,
        "_full": full,
    }


def risk_bundle(db: Session, user_id: int, val: dict | None = None, perf: dict | None = None) -> dict:
    val = val or valuation(db, user_id)
    perf = perf or performance_bundle(db, user_id, "ALL", val["transactions"])
    full = perf["_full"]
    rets = full["daily_return"] if not full.empty else None
    idx = full["index"] if not full.empty else None
    return risk.risk_report(val["holdings"], rets, idx, config.RISK_FREE_RATE_PCT)


def assistant_context(db: Session, user_id: int) -> dict:
    val = valuation(db, user_id)
    perf = performance_bundle(db, user_id, "ALL", val["transactions"])
    return {"holdings": val["holdings"], "totals": val["totals"], "sectors": val["sectors"], "best": val["best"], "worst": val["worst"],
            "missing_prices": val["missing_prices"], "monthly": perf["monthly"], "risk": risk_bundle(db, user_id, val, perf)}


# ---------- price refresh ----------
def _store_history(db: Session, symbol: str, rows: list[tuple[date, float]]) -> int:
    existing = {d: p for d, p in db.query(PriceHistory.price_date, PriceHistory).filter(PriceHistory.symbol == symbol).all()}
    added = 0
    for d, close in rows:
        cur = existing.get(d)
        if cur is None:
            db.add(PriceHistory(symbol=symbol, price_date=d, close=close, source="market"))
            added += 1
        elif abs(cur.close - close) > 1e-9:
            cur.close = close
    return added


def _history_is_fresh(db: Session, symbol: str, start: date) -> bool:
    first, last = (db.query(PriceHistory.price_date).filter(PriceHistory.symbol == symbol).order_by(PriceHistory.price_date.asc()).limit(1).scalar(),
                   db.query(PriceHistory.price_date).filter(PriceHistory.symbol == symbol).order_by(PriceHistory.price_date.desc()).limit(1).scalar())
    if first is None or last is None:
        return False
    return first <= start and (date.today() - last).days <= 1


def refresh_prices(db: Session, user_id: int, svc: market.MarketService) -> dict:
    """Fetch quotes + history for the user's symbols. One bad symbol never aborts the rest."""
    if not svc.provider.is_live:
        raise market.ProviderUnavailable(market.DemoProvider.MSG)
    txns = load_transactions(db, user_id)
    first_buy: dict[str, date] = {}
    for t in txns:
        first_buy.setdefault(t["symbol"], t["date"])
    ledger = accounting.replay(txns)
    open_syms = [s for s, lot in ledger.lots.items() if lot.quantity > 0]
    positions = load_positions(db, user_id)
    updated, failed, hist_added = [], [], 0

    for sym in sorted(first_buy):
        pos = positions.get(sym) or ensure_position(db, user_id, sym)
        if sym in open_syms:
            try:
                q = svc.quote(sym)
                pos.current_price, pos.prev_close = q.price, q.previous_close
                pos.price_source, pos.price_updated_at = "market", q.as_of
                if q.name and not pos.company_name:
                    pos.company_name = q.name
                updated.append({"symbol": sym, "price": q.price, "change": q.change, "change_pct": q.change_pct, "as_of": q.as_of.isoformat()})
            except market.RateLimited as exc:
                failed.append({"symbol": sym, "reason": str(exc), "code": "rate_limited"})
                break  # further calls would hit the same limit
            except market.MarketError as exc:
                failed.append({"symbol": sym, "reason": str(exc), "code": "unavailable" if isinstance(exc, market.ProviderUnavailable) else "not_found"})
        try:
            start = first_buy[sym]
            if not _history_is_fresh(db, sym, start):
                rows = svc.history(sym, (date.today() - start).days + 10)
                hist_added += _store_history(db, sym, rows)
        except market.RateLimited as exc:
            failed.append({"symbol": sym, "reason": "History: " + str(exc), "code": "rate_limited"})
            break
        except market.MarketError as exc:
            if not any(f["symbol"] == sym for f in failed):
                failed.append({"symbol": sym, "reason": "History: " + str(exc), "code": "no_history"})

    if first_buy:  # benchmark for the comparison chart
        start = min(first_buy.values())
        try:
            if not _history_is_fresh(db, config.BENCHMARK_SYMBOL, start):
                hist_added += _store_history(db, config.BENCHMARK_SYMBOL, svc.history(config.BENCHMARK_SYMBOL, (date.today() - start).days + 10))
        except market.MarketError as exc:
            failed.append({"symbol": config.BENCHMARK_SYMBOL, "reason": "Benchmark: " + str(exc), "code": "benchmark"})

    db.flush()
    _record_snapshot(db, user_id)
    return {"provider": svc.provider.name, "updated": updated, "failed": failed, "history_rows_added": hist_added,
            "as_of": datetime.now(timezone.utc).isoformat()}


def _record_snapshot(db: Session, user_id: int) -> None:
    val = valuation(db, user_id)
    if not val["holdings"] or val["missing_prices"]:
        return  # never record a partial number as if it were the whole portfolio
    today = date.today()
    snap = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.user_id == user_id, PortfolioSnapshot.snap_date == today).first()
    if snap is None:
        snap = PortfolioSnapshot(user_id=user_id, snap_date=today, market_value=0, invested=0)
        db.add(snap)
    snap.market_value, snap.invested = val["totals"]["market_value"], val["totals"]["open_cost"]
