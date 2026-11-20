"""Risk metrics. Everything is explainable and none of it is a complete measure of investment risk.

Concentration metrics use today's market values. Volatility, drawdown and Sharpe use the time-weighted
daily returns from performance.py and only appear when there is enough history.
"""
from __future__ import annotations

import math
from collections import defaultdict

import pandas as pd

TRADING_DAYS = 252
MIN_OBS_VOL = 20
MIN_OBS_SHARPE = 60

METHODOLOGY = [
    {"metric": "Stock concentration", "how": "Each holding's share of total market value. Warning above 40% in one stock."},
    {"metric": "Sector concentration", "how": "Each sector's share of total market value. Warning above 50% in one sector."},
    {"metric": "HHI (Herfindahl-Hirschman Index)", "how": "Sum of squared portfolio weights (0 to 1). 1 means everything is in one stock; 1/n means perfectly equal weights. Effective holdings = 1 / HHI."},
    {"metric": "Diversification score", "how": "0-100. (1 - HHI) / (1 - 1/n), scaled down when you hold fewer than 5 stocks. Higher is more diversified."},
    {"metric": "Historical volatility", "how": f"Standard deviation of daily returns x sqrt({TRADING_DAYS}), as a yearly percentage. Needs at least {MIN_OBS_VOL} daily returns."},
    {"metric": "Maximum drawdown", "how": "Largest fall from a previous peak of the cumulative return index, in percent. Uses returns, so deposits do not hide or fake a drop."},
    {"metric": "Sharpe ratio", "how": f"(Annualised mean daily return - risk-free rate) / annualised volatility. Needs at least {MIN_OBS_SHARPE} daily returns. Short histories make it unreliable."},
    {"metric": "Risk score", "how": "0-100 (higher = riskier). Blend of concentration (60%), sector concentration (15%) and volatility (25%); without enough history the volatility part is dropped and the rest re-weighted. A screening aid only: it ignores valuation, company quality, liquidity and market events."},
]


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def concentration(holdings: list[dict]) -> dict:
    rows = [h for h in holdings if h.get("market_value")]
    total = sum(h["market_value"] for h in rows)
    if total <= 0:
        return {"has_data": False}
    n = len(rows)
    w = {h["symbol"]: h["market_value"] / total for h in rows}
    sec: dict[str, float] = defaultdict(float)
    for h in rows:
        sec[h["sector"]] += h["market_value"] / total
    hhi = sum(x * x for x in w.values())
    sector_hhi = sum(x * x for x in sec.values())
    if n == 1:
        div = 0.0
    else:
        div = (1 - hhi) / (1 - 1 / n) * 100 * min(1.0, math.log(n) / math.log(5))
    top_sym, top_w = max(w.items(), key=lambda kv: kv[1])
    top_sec, top_sec_w = max(sec.items(), key=lambda kv: kv[1])
    k = len(sec)
    sector_conc = 100.0 if k == 1 else _clamp((sector_hhi - 1 / k) / (1 - 1 / k) * 100)
    return {
        "has_data": True, "n": n, "hhi": round(hhi, 4), "effective_holdings": round(1 / hhi, 2),
        "diversification_score": round(div, 1), "top_stock": top_sym, "top_stock_pct": round(top_w * 100, 2),
        "top_sector": top_sec, "top_sector_pct": round(top_sec_w * 100, 2), "sector_concentration_score": round(sector_conc, 1),
        "stock_weights": {s: round(v * 100, 2) for s, v in w.items()},
        "sector_weights": {s: round(v * 100, 2) for s, v in sec.items()},
    }


def return_metrics(daily_returns: pd.Series | None, index: pd.Series | None, risk_free_pct: float = 7.0) -> dict:
    out = {"volatility_pct": None, "max_drawdown_pct": None, "max_drawdown_peak": None, "max_drawdown_trough": None,
           "sharpe": None, "notes": []}
    if daily_returns is None:
        out["notes"].append("No price history yet, so volatility, drawdown and Sharpe ratio are unavailable.")
        return out
    r = daily_returns.dropna()
    if len(r) >= MIN_OBS_VOL:
        vol = float(r.std(ddof=1) * math.sqrt(TRADING_DAYS))
        out["volatility_pct"] = round(vol * 100, 2)
    else:
        out["notes"].append(f"Volatility needs at least {MIN_OBS_VOL} daily returns (you have {len(r)}).")
    if index is not None and len(index) >= 2:
        idx = index.astype(float)
        dd = idx / idx.cummax() - 1
        trough = dd.idxmin()
        out["max_drawdown_pct"] = round(float(dd.min()) * 100, 2)
        out["max_drawdown_trough"] = trough.date().isoformat()
        out["max_drawdown_peak"] = idx.loc[:trough].idxmax().date().isoformat()
    if len(r) >= MIN_OBS_SHARPE and out["volatility_pct"]:
        ann_mean = float(r.mean() * TRADING_DAYS)
        out["sharpe"] = round((ann_mean - risk_free_pct / 100) / (out["volatility_pct"] / 100), 2)
    else:
        out["notes"].append(f"Sharpe ratio needs at least {MIN_OBS_SHARPE} daily returns (you have {len(r)}).")
    return out


def risk_report(holdings: list[dict], daily_returns: pd.Series | None = None, index: pd.Series | None = None,
                risk_free_pct: float = 7.0) -> dict:
    c = concentration(holdings)
    rm = return_metrics(daily_returns, index, risk_free_pct)
    if not c["has_data"]:
        return {"diversification_score": 0, "level": "n/a", "risk_score": None, "risk_category": "n/a",
                "warnings": ["Add holdings with prices to see risk analysis."], "insights": [], "concentration": c,
                "metrics": rm, "methodology": METHODOLOGY, "disclaimer": DISCLAIMER}

    warnings, insights = [], []
    if c["top_stock_pct"] > 40:
        warnings.append(f"One holding ({c['top_stock']}) is {c['top_stock_pct']:.0f}% of your portfolio (above 40%).")
    if c["top_sector_pct"] > 50:
        warnings.append(f"{c['top_sector']} is {c['top_sector_pct']:.0f}% of your portfolio (above 50%).")
    if c["n"] < 5:
        warnings.append("Fewer than 5 holdings: consider spreading across more assets.")
    insights.append(f"You hold {c['n']} stocks across {len(c['sector_weights'])} sectors. HHI is {c['hhi']:.2f}, "
                    f"which behaves like about {c['effective_holdings']:.1f} equally sized holdings.")
    insights.append(f"Largest stock: {c['top_stock']} ({c['top_stock_pct']:.1f}%). Largest sector: {c['top_sector']} ({c['top_sector_pct']:.1f}%).")
    if not warnings:
        insights.append("No concentration limit is breached. That does not mean the portfolio is low risk.")

    conc_risk = 100 - c["diversification_score"]
    if rm["volatility_pct"] is not None:
        vol_component = _clamp(rm["volatility_pct"] / 40 * 100)
        score = 0.60 * conc_risk + 0.15 * c["sector_concentration_score"] + 0.25 * vol_component
    else:
        score = 0.80 * conc_risk + 0.20 * c["sector_concentration_score"]
    score = round(_clamp(score), 1)
    category = "Low" if score < 35 else "Moderate" if score < 60 else "High"
    div = c["diversification_score"]
    return {
        "diversification_score": div,
        "level": "low" if div >= 70 else "medium" if div >= 40 else "high",  # kept for the old API
        "risk_score": score, "risk_category": category,
        "warnings": warnings, "insights": insights, "concentration": c, "metrics": rm,
        "methodology": METHODOLOGY, "disclaimer": DISCLAIMER,
    }


DISCLAIMER = ("Educational analysis of the data you entered. A concentration or volatility score is not a complete measure "
              "of investment risk and is not personal investment advice.")
