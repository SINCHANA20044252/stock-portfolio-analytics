from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services import performance as P
from app.services import risk as R


def px(**cols):
    idx = pd.bdate_range("2025-01-01", periods=len(next(iter(cols.values()))))
    return pd.DataFrame(cols, index=idx)


def tx(i, sym, typ, q, p, d, fees=0.0):
    return {"id": i, "symbol": sym, "type": typ, "quantity": q, "price": p, "fees": fees, "date": d}


def test_value_and_return_for_a_single_stock():
    prices = px(A=[100, 110, 121, 121])
    res = P.build_series([tx(1, "A", "BUY", 10, 100, date(2025, 1, 1))], prices)["series"]
    assert list(res["value"].round(2)) == [1000, 1100, 1210, 1210]
    assert res["cumulative_return"].iloc[-1] == pytest.approx(0.21)
    assert res["daily_return"].iloc[1] == pytest.approx(0.10)
    assert res["invested"].iloc[-1] == 1000


def test_deposits_do_not_count_as_returns():
    # price flat at 100; buying more must not create performance
    prices = px(A=[100, 100, 100, 100])
    res = P.build_series([tx(1, "A", "BUY", 10, 100, date(2025, 1, 1)), tx(2, "A", "BUY", 10, 100, date(2025, 1, 3))], prices)["series"]
    assert res["value"].iloc[-1] == 2000
    assert res["cumulative_return"].iloc[-1] == pytest.approx(0.0, abs=1e-12)


def test_sell_flow_is_neutral():
    prices = px(A=[100, 100, 100, 100])
    res = P.build_series([tx(1, "A", "BUY", 10, 100, date(2025, 1, 1)), tx(2, "A", "SELL", 5, 100, date(2025, 1, 3))], prices)["series"]
    assert res["value"].iloc[-1] == 500
    assert res["cumulative_return"].iloc[-1] == pytest.approx(0.0, abs=1e-12)
    assert res["invested"].iloc[-1] == 500


def test_missing_prices_carry_forward_and_are_flagged():
    prices = px(A=[100, np.nan, np.nan, 130])
    res = P.build_series([tx(1, "A", "BUY", 1, 100, date(2025, 1, 1))], prices)["series"]
    assert list(res["filled"]) == [False, True, True, False]
    assert res["value"].iloc[1] == 100


def test_days_beyond_fill_limit_are_skipped_not_invented():
    prices = px(A=[100] + [np.nan] * 8 + [120])
    out = P.build_series([tx(1, "A", "BUY", 1, 100, date(2025, 1, 1))], prices, ffill_limit=2)
    assert len(out["series"]) < 10 and any("skipped" in n for n in out["notes"])


def test_symbol_without_prices_is_excluded_and_reported():
    prices = px(A=[100, 101, 102])
    out = P.build_series([tx(1, "A", "BUY", 1, 100, date(2025, 1, 1)), tx(2, "ZZZ", "BUY", 1, 5, date(2025, 1, 1))], prices)
    assert out["excluded_symbols"] == ["ZZZ"] and out["series"]["value"].iloc[-1] == 102


def test_empty_cases_have_explanations():
    assert P.build_series([], pd.DataFrame())["series"].empty
    out = P.build_series([tx(1, "A", "BUY", 1, 1, date(2025, 1, 1))], pd.DataFrame())
    assert out["series"].empty and "Refresh" in out["notes"][0]
    assert P.summarize(out["series"]) == {"has_data": False}


def _long_series():
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2024-01-01", "2025-06-30")
    prices = pd.DataFrame({"A": 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(idx)))}, index=idx)
    return prices, [tx(1, "A", "BUY", 10, float(prices["A"].iloc[0]), date(2024, 1, 1))]


def test_summary_annualised_needs_a_year_of_data():
    prices, txns = _long_series()
    df = P.build_series(txns, prices)["series"]
    full = P.summarize(df)
    assert full["annualized_return_pct"] is not None and full["days"] > 365
    short = P.summarize(P.slice_period(df, "1M"))
    assert short["annualized_return_pct"] is None and "365" in short["annualized_note"]


def test_periods_and_compounding_are_consistent():
    prices, txns = _long_series()
    df = P.build_series(txns, prices)["series"]
    monthly = P.period_returns(df, "ME")
    compounded = np.prod([1 + m["return_pct"] / 100 for m in monthly]) - 1
    assert compounded == pytest.approx(df["cumulative_return"].iloc[-1], abs=1e-3)
    assert P.slice_period(df, "1W").index.min() > df.index.max() - pd.Timedelta(days=7)
    assert len(P.slice_period(df, "ALL")) == len(df)
    with pytest.raises(ValueError):
        P.slice_period(df, "2Y")


def test_series_records_are_json_safe():
    import json
    prices, txns = _long_series()
    json.dumps(P.series_records(P.build_series(txns, prices)["series"]))


def test_benchmark_comparison_rebased_and_empty_states():
    prices, txns = _long_series()
    df = P.build_series(txns, prices)["series"]
    bench = pd.Series(np.linspace(100, 120, len(df)), index=df.index)
    c = P.benchmark_comparison(df, bench)
    assert c["available"] and c["points"][0]["portfolio"] == pytest.approx(100) and c["points"][0]["benchmark"] == pytest.approx(100)
    assert P.benchmark_comparison(df, None)["available"] is False
    assert P.benchmark_comparison(pd.DataFrame(), bench)["available"] is False


# ---------------- risk ----------------
def H(sym, sec, mv):
    return {"symbol": sym, "sector": sec, "market_value": mv}


def test_hhi_known_values():
    c = R.concentration([H("A", "IT", 50), H("B", "Bank", 50)])
    assert c["hhi"] == 0.5 and c["effective_holdings"] == 2.0
    one = R.concentration([H("A", "IT", 100)])
    assert one["hhi"] == 1.0 and one["diversification_score"] == 0


def test_risk_warns_on_concentration():
    r = R.risk_report([H("A", "IT", 100), H("B", "IT", 1)])
    assert any("holding" in w for w in r["warnings"]) and any("IT" in w for w in r["warnings"]) and any("Fewer than 5" in w for w in r["warnings"])
    assert r["level"] == "high" and r["risk_category"] == "High"


def test_risk_better_when_spread():
    r = R.risk_report([H(str(i), f"S{i}", 10) for i in range(6)])
    assert r["level"] == "low" and r["warnings"] == [] and r["risk_category"] == "Low"


def test_empty_portfolio():
    r = R.risk_report([])
    assert r["risk_score"] is None and r["warnings"]


def test_holdings_without_prices_are_ignored_by_concentration():
    c = R.concentration([H("A", "IT", 100), {"symbol": "B", "sector": "IT", "market_value": None}])
    assert c["n"] == 1


def test_max_drawdown_and_volatility():
    idx = pd.bdate_range("2025-01-01", periods=30)
    index = pd.Series([100] * 5 + [120] * 5 + [90] * 10 + [100] * 10, index=idx, dtype=float)
    rets = index.pct_change()
    m = R.return_metrics(rets, index)
    assert m["max_drawdown_pct"] == pytest.approx(-25.0)
    assert m["max_drawdown_peak"] == idx[5].date().isoformat() or m["max_drawdown_peak"] == idx[9].date().isoformat()
    assert m["volatility_pct"] is not None and m["sharpe"] is None  # < 60 observations
    assert any("Sharpe" in n for n in m["notes"])


def test_sharpe_sign_and_requirements():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2024-01-01", periods=300)
    up = pd.Series(rng.normal(0.002, 0.01, 300), index=idx)
    m = R.return_metrics(up, (1 + up).cumprod() * 100, risk_free_pct=0)
    assert m["sharpe"] > 0
    flat = R.return_metrics(pd.Series([0.0] * 100, index=pd.bdate_range("2024-01-01", periods=100)), None)
    assert flat["sharpe"] is None   # zero volatility -> undefined, not infinity


def test_no_history_gives_explanatory_note():
    m = R.return_metrics(None, None)
    assert m["volatility_pct"] is None and m["notes"]


def test_methodology_and_disclaimer_present():
    r = R.risk_report([H("A", "IT", 10), H("B", "Bank", 10)])
    assert {x["metric"] for x in r["methodology"]} >= {"HHI (Herfindahl-Hirschman Index)", "Maximum drawdown", "Sharpe ratio"}
    assert "not a complete measure" in r["disclaimer"]
