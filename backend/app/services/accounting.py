"""Transaction accounting: weighted-average cost basis.

Rules (also documented in README):
  * BUY  : cost_basis += quantity * price + fees ; quantity += q
  * SELL : avg = cost_basis / quantity (held just before the sale)
           realized += (q * price - fees) - q * avg
           cost_basis -= q * avg ; quantity -= q
  * Fees are part of the cost of a buy and reduce the proceeds of a sell.
  * Selling more than is held is an error (checked chronologically on every replay, so
    editing or deleting an old buy cannot leave a later sell without shares).
  * Order of replay: trade date, then BUYs before SELLs on the same date, then id.

Pure Python (Decimal inside, float outside) so it is easy to test without a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable

ZERO = Decimal("0")


class AccountingError(ValueError):
    """A transaction list that cannot be valid (for example selling shares you do not own)."""

    def __init__(self, message: str, txn_id=None, symbol: str | None = None):
        super().__init__(message)
        self.txn_id = txn_id
        self.symbol = symbol


def D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _f(x: Decimal, places: int = 2) -> float:
    return float(round(x, places))


def sort_key(t: dict):
    # Saved rows have integer ids. Not-yet-saved rows (id None or a string) sort after saved rows of the
    # same day and keep their given order (Python's sort is stable), so mixed id types never get compared.
    tid = t.get("id")
    return (t["date"], 0 if t["type"] == "BUY" else 1, tid if isinstance(tid, int) else 10**12)


@dataclass
class Lot:
    symbol: str
    company_name: str = ""
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO       # cost of shares still held (incl. buy fees)
    total_bought: Decimal = ZERO     # gross spent on all buys (incl. fees) ever
    total_sold: Decimal = ZERO       # net proceeds of all sells (after fees) ever
    realized: Decimal = ZERO
    fees: Decimal = ZERO
    first_buy: date | None = None
    last_trade: date | None = None
    last_price: Decimal | None = None  # price of the most recent transaction (a fallback, not a market price)


@dataclass
class Ledger:
    lots: dict[str, Lot] = field(default_factory=dict)
    realized_by_txn: dict = field(default_factory=dict)


def replay(transactions: Iterable[dict]) -> Ledger:
    """Apply transactions in order. Each dict needs: id, symbol, type, quantity, price, fees, date."""
    ledger = Ledger()
    for t in sorted(transactions, key=sort_key):
        sym = t["symbol"]
        lot = ledger.lots.setdefault(sym, Lot(symbol=sym))
        if t.get("company_name"):
            lot.company_name = t["company_name"]
        q, p, fee = D(t["quantity"]), D(t["price"]), D(t.get("fees") or 0)
        if q <= 0:
            raise AccountingError("Quantity must be greater than zero.", t.get("id"), sym)
        if p < 0 or fee < 0:
            raise AccountingError("Price and fees cannot be negative.", t.get("id"), sym)
        lot.fees += fee
        lot.last_trade = t["date"]
        lot.last_price = p
        if t["type"] == "BUY":
            lot.quantity += q
            lot.cost_basis += q * p + fee
            lot.total_bought += q * p + fee
            lot.first_buy = lot.first_buy or t["date"]
        elif t["type"] == "SELL":
            if q > lot.quantity:
                raise AccountingError(
                    f"Cannot sell {q.normalize():f} {sym} on {t['date']}: only {lot.quantity.normalize():f} held at that point.",
                    t.get("id"),
                    sym,
                )
            avg = lot.cost_basis / lot.quantity
            proceeds = q * p - fee
            gain = proceeds - q * avg
            lot.realized += gain
            lot.total_sold += proceeds
            lot.cost_basis -= q * avg
            lot.quantity -= q
            ledger.realized_by_txn[t.get("id")] = gain
            if lot.quantity == 0:
                lot.cost_basis = ZERO  # kill rounding dust
        else:
            raise AccountingError(f"Unknown transaction type {t['type']!r}.", t.get("id"), sym)
    return ledger


def valuate(ledger: Ledger, prices: dict[str, float | None], sectors: dict[str, str] | None = None) -> dict:
    """Combine the ledger with current prices.

    `prices` maps symbol -> latest price (None when unknown). Holdings with no price are listed in
    `missing_prices` and are left out of market value totals instead of being valued at zero.
    """
    sectors = sectors or {}
    open_rows, closed_rows, missing = [], [], []
    mv_total = ZERO
    open_cost_total = ZERO
    for sym, lot in sorted(ledger.lots.items()):
        if lot.quantity > 0:
            price = prices.get(sym)
            row = {
                "symbol": sym,
                "company_name": lot.company_name or sym,
                "sector": sectors.get(sym) or "Other",
                "quantity": _f(lot.quantity, 6),
                "avg_cost": _f(lot.cost_basis / lot.quantity, 4),
                "invested": _f(lot.cost_basis),
                "realized_pnl": _f(lot.realized),
                "current_price": None,
                "market_value": None,
                "unrealized_pnl": None,
                "unrealized_pct": None,
                "weight": None,
            }
            if price is None:
                missing.append(sym)
            else:
                p = D(price)
                mv = lot.quantity * p
                un = mv - lot.cost_basis
                mv_total += mv
                open_cost_total += lot.cost_basis
                row.update(
                    current_price=_f(p, 4),
                    market_value=_f(mv),
                    unrealized_pnl=_f(un),
                    unrealized_pct=_f(un / lot.cost_basis * 100) if lot.cost_basis else 0.0,
                    _mv=mv,
                )
            open_rows.append(row)
        elif lot.total_bought > 0:
            closed_rows.append({"symbol": sym, "realized_pnl": _f(lot.realized), "total_bought": _f(lot.total_bought)})

    for r in open_rows:
        mv = r.pop("_mv", None)
        if mv is not None and mv_total > 0:
            r["weight"] = _f(mv / mv_total * 100)

    # Totals over every lot (open or closed) so realized P&L from fully sold stocks still counts.
    realized = sum((l.realized for l in ledger.lots.values()), ZERO)
    bought = sum((l.total_bought for l in ledger.lots.values()), ZERO)
    fees = sum((l.fees for l in ledger.lots.values()), ZERO)
    unrealized = mv_total - open_cost_total
    total_pnl = realized + unrealized
    priced = [r for r in open_rows if r["unrealized_pct"] is not None]
    best = max(priced, key=lambda r: r["unrealized_pct"], default=None)
    worst = min(priced, key=lambda r: r["unrealized_pct"], default=None)

    return {
        "holdings": open_rows,
        "closed": closed_rows,
        "missing_prices": missing,
        "totals": {
            "market_value": _f(mv_total),
            "open_cost": _f(open_cost_total),           # cost of what you still hold (priced holdings only)
            "total_invested": _f(bought),               # everything ever spent on buys
            "unrealized_pnl": _f(unrealized),
            "unrealized_pct": _f(unrealized / open_cost_total * 100) if open_cost_total else 0.0,
            "realized_pnl": _f(realized),
            "total_pnl": _f(total_pnl),
            "overall_return_pct": _f(total_pnl / bought * 100) if bought else 0.0,
            "fees_paid": _f(fees),
            "holdings_count": len(open_rows),
        },
        "best": {"symbol": best["symbol"], "pct": best["unrealized_pct"]} if best else None,
        "worst": {"symbol": worst["symbol"], "pct": worst["unrealized_pct"]} if worst else None,
    }


def sector_allocation(holdings: list[dict]) -> list[dict]:
    totals: dict[str, float] = {}
    for h in holdings:
        if h.get("market_value") is not None:
            totals[h["sector"]] = totals.get(h["sector"], 0.0) + h["market_value"]
    grand = sum(totals.values())
    return [
        {"sector": s, "value": round(v, 2), "percent": round(v / grand * 100, 2) if grand else 0.0}
        for s, v in sorted(totals.items(), key=lambda kv: -kv[1])
    ]


def stock_allocation(holdings: list[dict]) -> list[dict]:
    rows = [h for h in holdings if h.get("market_value") is not None]
    grand = sum(h["market_value"] for h in rows)
    return [
        {"symbol": h["symbol"], "value": h["market_value"], "percent": round(h["market_value"] / grand * 100, 2) if grand else 0.0}
        for h in sorted(rows, key=lambda h: -h["market_value"])
    ]


PNL_BUCKETS = [(-1e9, -20, "Below -20%"), (-20, -10, "-20% to -10%"), (-10, 0, "-10% to 0%"), (0, 10, "0% to 10%"), (10, 20, "10% to 20%"), (20, 1e9, "Above 20%")]


def pnl_distribution(holdings: list[dict]) -> list[dict]:
    out = []
    for lo, hi, label in PNL_BUCKETS:
        syms = [h["symbol"] for h in holdings if h.get("unrealized_pct") is not None and lo <= h["unrealized_pct"] < hi]
        out.append({"bucket": label, "count": len(syms), "symbols": syms})
    return out
