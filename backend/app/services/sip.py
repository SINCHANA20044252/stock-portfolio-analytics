"""SIP and goal maths.

Model: the annual return is a *nominal* rate compounded monthly (r = annual / 12), contributions are made
at the END of each month (ordinary annuity), and a lump sum (today's portfolio value) is invested at once.

    FV = P * (1 + r)^n  +  S * ((1 + r)^n - 1) / r        (r = 0 -> FV = P + S * n)
    Required SIP for a target T:  S = (T - P * (1 + r)^n) * r / ((1 + r)^n - 1)

Every result is an ESTIMATE based on a constant assumed return. Real returns vary and can be negative.
"""
from __future__ import annotations


class PlanError(ValueError):
    pass


def _check(years: int, annual_return_pct: float, monthly_sip: float, starting: float):
    if not (1 <= years <= 50):
        raise PlanError("Years must be between 1 and 50.")
    if not (0 <= annual_return_pct <= 30):
        raise PlanError("Expected return must be between 0% and 30%.")
    if monthly_sip < 0 or starting < 0:
        raise PlanError("Amounts cannot be negative.")


def future_value(starting: float, monthly_sip: float, annual_return_pct: float, months: int) -> float:
    r = annual_return_pct / 100 / 12
    if r == 0:
        return starting + monthly_sip * months
    g = (1 + r) ** months
    return starting * g + monthly_sip * (g - 1) / r


def required_sip(starting: float, target: float, annual_return_pct: float, months: int) -> float:
    r = annual_return_pct / 100 / 12
    if months <= 0:
        return 0.0
    if r == 0:
        return max(0.0, (target - starting) / months)
    g = (1 + r) ** months
    return max(0.0, (target - starting * g) * r / (g - 1))


def goal_projection(current: float, monthly_sip: float, annual_return_pct: float, years: int, target: float) -> dict:
    _check(years, annual_return_pct, monthly_sip, current)
    months = years * 12
    series = []
    for y in range(1, years + 1):
        value = future_value(current, monthly_sip, annual_return_pct, y * 12)
        invested = current + monthly_sip * y * 12
        series.append({"year": y, "value": round(value, 2), "invested": round(invested, 2), "returns": round(value - invested, 2)})
    final = series[-1]["value"]
    invested_total = current + monthly_sip * months
    needed = required_sip(current, target, annual_return_pct, months)
    return {
        "projected_value": final,
        "target": target,
        "on_track": final >= target,
        "shortfall": round(max(0.0, target - final), 2),
        "required_monthly_sip": round(needed, 2),
        "total_invested": round(invested_total, 2),
        "estimated_returns": round(final - invested_total, 2),
        "series": series,
        "is_estimate": True,
        "disclaimer": "Projection based on a constant assumed return. It is an estimate, not a guaranteed outcome.",
    }


def compare_scenarios(current: float, target: float, scenarios: list[dict]) -> list[dict]:
    """Each scenario: name, years, annual_return_pct, monthly_sip (optional -> solved from target)."""
    if not 1 <= len(scenarios) <= 6:
        raise PlanError("Compare between 1 and 6 scenarios.")
    out = []
    for i, s in enumerate(scenarios):
        years, ret = int(s["years"]), float(s["annual_return_pct"])
        sip = s.get("monthly_sip")
        _check(years, ret, float(sip or 0), current)
        solved = sip is None
        if solved:
            sip = required_sip(current, target, ret, years * 12)
        plan = goal_projection(current, float(sip), ret, years, target)
        plan.update(name=s.get("name") or f"Scenario {i + 1}", years=years, annual_return_pct=ret,
                    monthly_sip=round(float(sip), 2), sip_was_solved=solved)
        out.append(plan)
    return out
