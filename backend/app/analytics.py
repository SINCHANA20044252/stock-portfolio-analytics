"""Portfolio maths. Pure functions so they are easy to unit test."""
from collections import defaultdict
from math import log


def holding_value(qty: float, price: float) -> float:
    return qty * price


def portfolio_summary(holdings: list[dict]) -> dict:
    invested = sum(h["quantity"] * h["buy_price"] for h in holdings)
    value = sum(h["quantity"] * h["current_price"] for h in holdings)
    gain = value - invested
    gain_pct = (gain / invested * 100) if invested else 0.0

    by_sector: dict[str, float] = defaultdict(float)
    for h in holdings:
        by_sector[h["sector"]] += h["quantity"] * h["current_price"]
    allocation = [
        {"sector": s, "value": round(v, 2), "percent": round(v / value * 100, 2) if value else 0.0}
        for s, v in sorted(by_sector.items(), key=lambda kv: -kv[1])
    ]
    return {
        "invested": round(invested, 2),
        "current_value": round(value, 2),
        "gain": round(gain, 2),
        "gain_percent": round(gain_pct, 2),
        "allocation": allocation,
    }


def risk_report(holdings: list[dict]) -> dict:
    """Simple, explainable risk checks based on concentration (not market volatility)."""
    total = sum(h["quantity"] * h["current_price"] for h in holdings)
    if total == 0:
        return {"diversification_score": 0, "level": "n/a", "warnings": ["Add holdings to see risk analysis."]}

    weights = [h["quantity"] * h["current_price"] / total for h in holdings]
    sector_w: dict[str, float] = defaultdict(float)
    for h, w in zip(holdings, weights):
        sector_w[h["sector"]] += w

    # Herfindahl-Hirschman Index: 1.0 = everything in one holding, 1/n = perfectly even.
    hhi = sum(w * w for w in weights)
    n = len(weights)
    # Score 0-100: 100 means perfectly spread, 0 means a single holding.
    score = 0 if n == 1 else round((1 - hhi) / (1 - 1 / n) * 100 * min(1.0, log(n) / log(5)), 1)

    warnings = []
    top_holding = max(weights)
    top_sector, top_sector_w = max(sector_w.items(), key=lambda kv: kv[1])
    if top_holding > 0.4:
        warnings.append(f"One holding is {top_holding * 100:.0f}% of your portfolio (above 40%).")
    if top_sector_w > 0.5:
        warnings.append(f"{top_sector} is {top_sector_w * 100:.0f}% of your portfolio (above 50%).")
    if n < 5:
        warnings.append("Fewer than 5 holdings: consider spreading across more assets.")

    level = "low" if score >= 70 else "medium" if score >= 40 else "high"
    return {"diversification_score": score, "level": level, "warnings": warnings}


def goal_projection(current: float, monthly_sip: float, annual_return_pct: float, years: int, target: float) -> dict:
    """Month-by-month growth with a fixed monthly contribution (SIP)."""
    r = annual_return_pct / 100 / 12
    balance = current
    series = []
    for month in range(1, years * 12 + 1):
        balance = balance * (1 + r) + monthly_sip
        if month % 12 == 0:
            series.append({"year": month // 12, "value": round(balance, 2)})

    # Monthly SIP needed to reach the target from today's balance.
    months = years * 12
    if r == 0:
        needed = max(0.0, (target - current) / months) if months else 0.0
    else:
        growth = (1 + r) ** months
        needed = max(0.0, (target - current * growth) * r / (growth - 1)) if months else 0.0

    return {
        "projected_value": round(balance, 2),
        "target": target,
        "on_track": balance >= target,
        "shortfall": round(max(0.0, target - balance), 2),
        "required_monthly_sip": round(needed, 2),
        "series": series,
    }
