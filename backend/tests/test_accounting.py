from datetime import date

import pytest

from app.services import accounting as a

D1, D2, D3, D4 = date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)


def t(i, sym, typ, q, p, d, fees=0):
    return {"id": i, "symbol": sym, "type": typ, "quantity": q, "price": p, "fees": fees, "date": d}


def test_average_cost_includes_fees():
    ledger = a.replay([t(1, "A", "BUY", 10, 100, D1, 10), t(2, "A", "BUY", 10, 120, D2)])
    lot = ledger.lots["A"]
    assert lot.quantity == 20
    assert lot.cost_basis == 2210  # 1000 + 10 fee + 1200
    assert float(lot.cost_basis / lot.quantity) == pytest.approx(110.5)


def test_sell_realizes_profit_against_average_cost_and_fees():
    ledger = a.replay([t(1, "A", "BUY", 10, 100, D1, 10), t(2, "A", "BUY", 10, 120, D2), t(3, "A", "SELL", 5, 150, D3, 5)])
    lot = ledger.lots["A"]
    # avg 110.5 -> cost of 5 = 552.5 ; proceeds 750 - 5 = 745 ; realized 192.5
    assert float(lot.realized) == pytest.approx(192.5)
    assert float(ledger.realized_by_txn[3]) == pytest.approx(192.5)
    assert lot.quantity == 15
    assert float(lot.cost_basis) == pytest.approx(1657.5)


def test_average_cost_unchanged_by_selling():
    ledger = a.replay([t(1, "A", "BUY", 10, 100, D1), t(2, "A", "SELL", 4, 130, D2)])
    lot = ledger.lots["A"]
    assert float(lot.cost_basis / lot.quantity) == pytest.approx(100)


def test_selling_everything_leaves_no_cost_and_keeps_realized():
    ledger = a.replay([t(1, "A", "BUY", 10, 100, D1), t(2, "A", "SELL", 10, 90, D2)])
    assert ledger.lots["A"].quantity == 0 and ledger.lots["A"].cost_basis == 0
    assert float(ledger.lots["A"].realized) == pytest.approx(-100)


def test_cannot_sell_more_than_held():
    with pytest.raises(a.AccountingError, match="only 10"):
        a.replay([t(1, "A", "BUY", 10, 100, D1), t(2, "A", "SELL", 11, 100, D2)])


def test_cannot_sell_before_buying_even_if_buy_is_later():
    with pytest.raises(a.AccountingError):
        a.replay([t(1, "A", "SELL", 1, 100, D1), t(2, "A", "BUY", 5, 100, D2)])


def test_same_day_buy_then_sell_is_allowed():
    a.replay([t(2, "A", "SELL", 5, 100, D1), t(1, "A", "BUY", 5, 100, D1)])


def test_symbols_are_independent():
    with pytest.raises(a.AccountingError):
        a.replay([t(1, "A", "BUY", 10, 1, D1), t(2, "B", "SELL", 1, 1, D2)])


def test_zero_or_negative_values_rejected():
    for bad in (t(1, "A", "BUY", 0, 100, D1), t(1, "A", "BUY", -1, 100, D1), t(1, "A", "BUY", 1, -5, D1)):
        with pytest.raises(a.AccountingError):
            a.replay([bad])


def test_unsaved_rows_with_string_ids_do_not_break_sorting():
    a.replay([t(5, "A", "BUY", 10, 1, D1), {**t(None, "A", "BUY", 1, 1, D1), "id": "imp-0"}, {**t(None, "A", "SELL", 2, 1, D1), "id": "imp-1"}])


def test_valuation_totals_reconcile():
    txns = [t(1, "A", "BUY", 10, 100, D1, 10), t(2, "A", "BUY", 10, 120, D2), t(3, "A", "SELL", 5, 150, D3, 5), t(4, "B", "BUY", 2, 50, D3), t(5, "B", "SELL", 2, 60, D4)]
    v = a.valuate(a.replay(txns), {"A": 130}, {"A": "IT"})
    tot = v["totals"]
    assert tot["market_value"] == 1950 and tot["unrealized_pnl"] == pytest.approx(292.5)
    assert tot["realized_pnl"] == pytest.approx(192.5 + 20)
    # total P&L = market value + all sale proceeds - everything spent on buys
    spent = 1010 + 1200 + 100
    proceeds = 745 + 120
    assert tot["total_pnl"] == pytest.approx(1950 + proceeds - spent)
    assert tot["total_invested"] == pytest.approx(spent)
    assert tot["overall_return_pct"] == pytest.approx(tot["total_pnl"] / spent * 100, abs=0.01)
    assert v["closed"][0]["symbol"] == "B"


def test_missing_price_is_reported_not_valued_at_zero():
    v = a.valuate(a.replay([t(1, "A", "BUY", 10, 100, D1), t(2, "B", "BUY", 1, 50, D1)]), {"A": 110, "B": None})
    assert v["missing_prices"] == ["B"]
    assert v["totals"]["market_value"] == 1100
    assert next(h for h in v["holdings"] if h["symbol"] == "B")["market_value"] is None


def test_allocation_best_worst_and_distribution():
    v = a.valuate(a.replay([t(1, "A", "BUY", 10, 100, D1), t(2, "B", "BUY", 10, 100, D1)]), {"A": 130, "B": 80}, {"A": "IT", "B": "Bank"})
    assert v["best"]["symbol"] == "A" and v["worst"]["symbol"] == "B"
    assert a.sector_allocation(v["holdings"])[0]["sector"] == "IT"
    assert sum(s["percent"] for s in a.stock_allocation(v["holdings"])) == pytest.approx(100, abs=0.02)
    dist = {d["bucket"]: d["symbols"] for d in a.pnl_distribution(v["holdings"])}
    assert dist["Above 20%"] == ["A"] and dist["-20% to -10%"] == ["B"]  # buckets are lower-inclusive: -20% falls in "-20% to -10%"
