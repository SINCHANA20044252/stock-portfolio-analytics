"""Historical performance with Pandas.

The portfolio value for each trading day is RECONSTRUCTED from (a) the user's transactions and (b) stored
daily closing prices. Nothing is invented: a day only gets a value when every held symbol has a price
(a price may be carried forward from the last close for up to `ffill_limit` days, e.g. over holidays;
those days are flagged `filled`). Symbols with no stored prices are excluded and reported.

Returns are TIME-WEIGHTED so deposits and withdrawals do not look like gains. Cash flows are assumed to
happen at the start of the day and the value is taken at the close:

    r_t = V_t / (V_prev + flow_t) - 1        flow_t = buys (incl. fees) minus sell proceeds on day t

Weekly / monthly returns compound the daily returns. Annualised return needs at least 365 days of data.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

PERIOD_DAYS = {"1W": 7, "1M": 30, "3M": 91, "6M": 182, "1Y": 365}
ANNUALISE_MIN_DAYS = 365


def _clean(x):
    if x is None:
        return None
    if isinstance(x, (float, np.floating)):
        return None if (math.isnan(x) or math.isinf(x)) else round(float(x), 6)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def prices_frame(rows: list[tuple[str, date, float]]) -> pd.DataFrame:
    """rows of (symbol, date, close) -> DataFrame indexed by date, one column per symbol."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["symbol", "date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()


def build_series(transactions: list[dict], prices: pd.DataFrame, ffill_limit: int = 5) -> dict:
    """Return {"series": DataFrame, "excluded_symbols": [...], "notes": [...]}. DataFrame may be empty."""
    notes: list[str] = []
    empty = {"series": pd.DataFrame(), "excluded_symbols": [], "notes": notes}
    if not transactions:
        notes.append("No transactions yet.")
        return empty
    if prices is None or prices.empty:
        notes.append("No historical prices stored yet. Refresh market prices to load history.")
        empty["excluded_symbols"] = sorted({t["symbol"] for t in transactions})
        return empty

    syms_with_prices = [s for s in prices.columns if prices[s].notna().any()]
    tx = pd.DataFrame(transactions)
    tx["date"] = pd.to_datetime(tx["date"])
    excluded = sorted(set(tx["symbol"]) - set(syms_with_prices))
    tx = tx[tx["symbol"].isin(syms_with_prices)]
    if tx.empty:
        notes.append("None of your symbols have historical prices.")
        empty["excluded_symbols"] = excluded
        return empty

    start = tx["date"].min()
    px_all = prices[syms_with_prices].sort_index()
    px_ff = px_all.ffill(limit=ffill_limit)
    dates = px_all.index[px_all.index >= start]
    if len(dates) == 0:
        notes.append("Price history ends before your first transaction.")
        empty["excluded_symbols"] = excluded
        return empty
    px = px_ff.loc[dates]
    raw = px_all.loc[dates]

    # Map each transaction to the first trading day on/after its date (drop ones after the last price date).
    pos = dates.searchsorted(tx["date"].values)
    keep = pos < len(dates)
    if (~keep).any():
        notes.append(f"{int((~keep).sum())} transaction(s) dated after the last price were left out of the history.")
    tx, pos = tx[keep], pos[keep]
    tx = tx.assign(day=dates[pos])

    sign = np.where(tx["type"] == "BUY", 1.0, -1.0)
    tx = tx.assign(dq=sign * tx["quantity"].astype(float))
    tx = tx.assign(flow=np.where(tx["type"] == "BUY",
                                 tx["quantity"] * tx["price"] + tx["fees"].fillna(0),
                                 -(tx["quantity"] * tx["price"] - tx["fees"].fillna(0))).astype(float))

    qty = tx.pivot_table(index="day", columns="symbol", values="dq", aggfunc="sum").reindex(dates).fillna(0).cumsum()
    qty = qty.reindex(columns=px.columns, fill_value=0.0)
    qty = qty.where(qty.abs() > 1e-9, 0.0)
    flow = tx.groupby("day")["flow"].sum().reindex(dates).fillna(0.0)

    # Open cost basis over time via weighted-average replay (same rules as accounting.py).
    invested = _open_cost_series(tx, dates)

    held = qty > 0
    missing = (held & px.isna()).any(axis=1)
    filled = (held & raw.isna() & px.notna()).any(axis=1)
    value = (qty * px).where(~px.isna() | ~held, 0.0).sum(axis=1)
    value = value.where(~missing)

    df = pd.DataFrame({"value": value, "invested": invested, "filled": filled, "flow": flow})
    df = df.loc[(qty.abs().sum(axis=1) > 0) | (df["flow"] != 0)]
    n_incomplete = int(df["value"].isna().sum())
    if n_incomplete:
        notes.append(f"{n_incomplete} day(s) were skipped because a held stock had no price.")
    df = df[df["value"].notna()].copy()
    if df.empty:
        notes.append("Not enough price data to value your portfolio on any day.")
        empty["excluded_symbols"] = excluded
        return empty

    flow_cum = flow.cumsum().reindex(df.index)
    df["flow_since"] = flow_cum.diff().fillna(flow_cum)
    base = df["value"].shift(1).fillna(0.0) + df["flow_since"]
    r = pd.Series(np.where(base > 1e-9, df["value"] / base.where(base > 1e-9) - 1, np.nan), index=df.index)
    df["daily_return"] = r
    df["cumulative_return"] = (1 + r.fillna(0)).cumprod() - 1
    df["index"] = 100 * (1 + df["cumulative_return"])
    df["pnl"] = df["value"] - df["invested"]
    if excluded:
        notes.append("Excluded (no price history): " + ", ".join(excluded))
    if df["filled"].any():
        notes.append("Some days use the previous close (holiday or missing data); these are marked as estimates.")
    return {"series": df, "excluded_symbols": excluded, "notes": notes}


def _open_cost_series(tx: pd.DataFrame, dates) -> pd.Series:
    """Weighted-average open cost basis at the close of each date."""
    from .accounting import D, ZERO

    qty: dict[str, object] = {}
    cost: dict[str, object] = {}
    by_day = {d: g for d, g in tx.sort_values(["day"], kind="stable").groupby("day")}
    out, total = [], ZERO
    for d in dates:
        g = by_day.get(d)
        if g is not None:
            g = g.assign(_o=np.where(g["type"] == "BUY", 0, 1)).sort_values(["_o"], kind="stable")
            for _, t in g.iterrows():
                s = t["symbol"]
                q, p, fee = D(t["quantity"]), D(t["price"]), D(t["fees"] if pd.notna(t["fees"]) else 0)
                q0, c0 = qty.get(s, ZERO), cost.get(s, ZERO)
                if t["type"] == "BUY":
                    qty[s], cost[s] = q0 + q, c0 + q * p + fee
                elif q0 > 0:
                    take = c0 / q0 * min(q, q0)
                    qty[s], cost[s] = q0 - min(q, q0), c0 - take
            total = sum(cost.values(), ZERO)
        out.append(float(total))
    return pd.Series(out, index=dates)


def slice_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Restrict to a window and re-base cumulative return / index to the window start."""
    if df.empty or period.upper() == "ALL":
        return df
    days = PERIOD_DAYS.get(period.upper())
    if days is None:
        raise ValueError(f"Unknown period {period!r}")
    cutoff = df.index.max() - pd.Timedelta(days=days)
    out = df[df.index > cutoff].copy()
    if out.empty:
        return out
    out["cumulative_return"] = (1 + out["daily_return"].fillna(0)).cumprod() - 1
    out["index"] = 100 * (1 + out["cumulative_return"])
    return out


def _compound(r: pd.Series, rule: str) -> pd.Series:
    return (1 + r.dropna()).resample(rule).prod() - 1


def _period_best_worst(s: pd.Series, fmt) -> dict:
    if s.empty:
        return {"best": None, "worst": None}
    b, w = s.idxmax(), s.idxmin()
    return {"best": {"period": fmt(b), "return_pct": round(float(s[b]) * 100, 2)}, "worst": {"period": fmt(w), "return_pct": round(float(s[w]) * 100, 2)}}


def summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"has_data": False}
    r = df["daily_return"].dropna()
    days = (df.index.max() - df.index.min()).days
    cum = float(df["cumulative_return"].iloc[-1])
    annual = None
    reason = None
    if days >= ANNUALISE_MIN_DAYS and cum > -1:
        annual = round(((1 + cum) ** (365 / days) - 1) * 100, 2)
    else:
        reason = f"Annualised return needs at least {ANNUALISE_MIN_DAYS} days of history (you have {days})."
    weekly = _compound(r, "W")
    monthly = _compound(r, "ME")
    return {
        "has_data": True,
        "start_date": df.index.min().date().isoformat(),
        "end_date": df.index.max().date().isoformat(),
        "days": days,
        "trading_days": int(len(df)),
        "cumulative_return_pct": round(cum * 100, 2),     # time-weighted
        "portfolio_growth_pct": round(float(df["value"].iloc[-1] / df["invested"].iloc[-1] * 100 - 100), 2) if df["invested"].iloc[-1] else None,
        "annualized_return_pct": annual,
        "annualized_note": reason,
        "best_day": ({"period": r.idxmax().date().isoformat(), "return_pct": round(float(r.max()) * 100, 2)} if len(r) else None),
        "worst_day": ({"period": r.idxmin().date().isoformat(), "return_pct": round(float(r.min()) * 100, 2)} if len(r) else None),
        "weekly": _period_best_worst(weekly, lambda d: d.date().isoformat()),
        "monthly": _period_best_worst(monthly, lambda d: d.strftime("%b %Y")),
    }


def series_records(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "date": idx.date().isoformat(),
            "value": _clean(row["value"]),
            "invested": _clean(row["invested"]),
            "pnl": _clean(row["pnl"]),
            "daily_return_pct": _clean(row["daily_return"] * 100) if pd.notna(row["daily_return"]) else None,
            "cumulative_return_pct": _clean(row["cumulative_return"] * 100),
            "index": _clean(row["index"]),
            "estimated": bool(row["filled"]),
        }
        for idx, row in df.iterrows()
    ]


def period_returns(df: pd.DataFrame, rule: str) -> list[dict]:
    """rule 'W' weekly or 'ME' monthly."""
    if df.empty:
        return []
    s = _compound(df["daily_return"], rule)
    fmt = (lambda d: d.strftime("%Y-%m")) if rule == "ME" else (lambda d: d.date().isoformat())
    return [{"period": fmt(i), "return_pct": round(float(v) * 100, 2)} for i, v in s.items()]


def benchmark_comparison(df: pd.DataFrame, bench_close: pd.Series | None) -> dict:
    """Rebase portfolio (time-weighted) and benchmark (price return) to 100 at the first common date."""
    if df.empty:
        return {"available": False, "reason": "No portfolio history yet.", "points": []}
    if bench_close is None or bench_close.dropna().empty:
        return {"available": False, "reason": "No benchmark prices stored. Refresh market prices to load them.", "points": []}
    b = bench_close.sort_index().ffill(limit=5)
    joined = pd.DataFrame({"portfolio": df["index"], "benchmark": b.reindex(df.index)}).dropna()
    if len(joined) < 2:
        return {"available": False, "reason": "Not enough overlapping dates with the benchmark.", "points": []}
    joined["portfolio"] = joined["portfolio"] / joined["portfolio"].iloc[0] * 100
    joined["benchmark"] = joined["benchmark"] / joined["benchmark"].iloc[0] * 100
    pts = [{"date": i.date().isoformat(), "portfolio": _clean(r["portfolio"]), "benchmark": _clean(r["benchmark"])} for i, r in joined.iterrows()]
    return {"available": True, "points": pts,
            "portfolio_return_pct": round(float(joined["portfolio"].iloc[-1]) - 100, 2),
            "benchmark_return_pct": round(float(joined["benchmark"].iloc[-1]) - 100, 2)}
