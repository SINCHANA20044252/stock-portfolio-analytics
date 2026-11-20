import pytest

from app import assistant
from app.services import market
from tests.fakes import FakeProvider, make_service


def test_quote_change_and_alias_resolution():
    svc = make_service()
    q = svc.quote("infy")                         # user types INFY -> resolved to INFY.NS
    assert q.symbol == "INFY" and q.price == 1600 and q.change == 20 and q.change_pct == 1.27
    assert q.to_dict()["as_of"]


def test_quotes_are_cached():
    svc = make_service()
    svc.quote("INFY"), svc.quote("INFY"), svc.quote("infy")
    assert svc.provider.calls == 1


def test_unknown_symbol_and_provider_errors_are_distinct():
    svc = make_service()
    with pytest.raises(market.SymbolNotFound):
        svc.quote("NOPE")
    with pytest.raises(market.RateLimited):
        svc.quote("LIMITED.NS")


def test_search_adds_sector_and_ignores_short_queries():
    svc = make_service()
    assert svc.search("inf")[0]["sector"] == "IT"
    assert svc.search("i") == []


def test_demo_mode_never_returns_prices():
    svc = market.MarketService(market.DemoProvider())
    assert svc.status["live"] is False and "Demo" in svc.status["note"]
    assert svc.search("hdfc")[0]["sector"] == "Banking"
    with pytest.raises(market.ProviderUnavailable):
        svc.quote("INFY")
    with pytest.raises(market.ProviderUnavailable):
        svc.history("INFY", 30)


def test_alpha_vantage_without_key_falls_back_to_labelled_demo(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "alphavantage")
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    svc = market.build_service_from_env()
    assert svc.provider.name == "demo" and "ALPHAVANTAGE_API_KEY" in svc.status["note"]


def test_provider_is_configurable(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "yahoo")
    assert market.build_service_from_env().provider.name == "yahoo"
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "alphavantage")
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "k")
    assert market.build_service_from_env().provider.name == "alphavantage"
    market.set_market_service(None)


def test_history_fake_is_weekday_only():
    rows = FakeProvider().history("INFY.NS", 30)
    assert rows and all(d.weekday() < 5 for d, _ in rows)


# ---------------- assistant ----------------
CTX = {
    "holdings": [{"symbol": "INFY", "market_value": 15200, "weight": 60.0}, {"symbol": "TCS", "market_value": 10000, "weight": 40.0}],
    "totals": {"market_value": 25200, "total_invested": 24000, "total_pnl": 1200, "unrealized_pnl": 1000, "realized_pnl": 200, "overall_return_pct": 5.0},
    "sectors": [{"sector": "IT", "value": 25200, "percent": 100.0}], "best": {"symbol": "INFY", "pct": 6.2}, "worst": {"symbol": "TCS", "pct": -1.0},
    "missing_prices": [], "monthly": [{"period": "2025-01", "return_pct": 2.0}, {"period": "2025-02", "return_pct": -1.0}],
    "risk": {"diversification_score": 10, "risk_score": 80, "risk_category": "High", "warnings": ["IT is 100% of your portfolio (above 50%)."],
             "concentration": {"has_data": True, "n": 2, "sector_weights": {"IT": 100}, "hhi": 0.52, "effective_holdings": 1.9,
                               "top_stock": "INFY", "top_stock_pct": 60, "top_sector": "IT", "top_sector_pct": 100}},
}


@pytest.mark.parametrize("question,expect", [
    ("What is my total portfolio value?", "₹25,200"),
    ("Which stock has the highest allocation?", "INFY"),
    ("Which sector has the highest exposure?", "IT is your largest sector"),
    ("Which stock generated the highest return?", "6.20%"),
    ("What is my overall profit/loss?", "₹1,200"),
    ("Explain my portfolio diversification.", "10/100"),
    ("Explain the risk associated with my portfolio concentration.", "High"),
    ("Summarize my monthly portfolio performance.", "2025-02"),
])
def test_portfolio_questions_use_real_numbers(question, expect):
    out = assistant.answer(question, CTX)
    assert out["grounded"] is True and expect in out["answer"] and out["sources"][0] == "Your portfolio data"


def test_glossary_questions_do_not_need_portfolio():
    out = assistant.answer("What does maximum drawdown mean?", CTX)
    assert out["grounded"] is False and "Maximum drawdown" in out["sources"][0]
    assert "Expense ratio" in assistant.answer("what is an expense ratio?")["sources"][0]


def test_out_of_scope_question_gets_helpful_message():
    out = assistant.answer("Who won the cricket match yesterday?", CTX)
    assert out["sources"] == [] and "portfolio" in out["answer"]


def test_no_holdings_means_no_invented_figures():
    out = assistant.answer("What is my total portfolio value?", {"holdings": []})
    assert "no holdings" in out["answer"].lower() and "₹" not in out["answer"]


def test_missing_prices_are_mentioned():
    ctx = {**CTX, "missing_prices": ["ZZZ"]}
    assert "ZZZ" in assistant.answer("What is my total portfolio value?", ctx)["answer"]


def test_ai_text_never_replaces_the_computed_facts(monkeypatch):
    monkeypatch.setattr(assistant, "_ask_gemini", lambda q, p, f=None: "Rephrased by AI")
    out = assistant.answer("What is my overall profit/loss?", CTX)
    assert out["used_ai"] and out["answer"] == "Rephrased by AI" and "₹1,200" in out["plain_answer"] and out["facts"]["total_pnl"] == 1200


def test_gemini_failure_falls_back_to_plain_answer(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    out = assistant.answer("What is my total portfolio value?", CTX)
    assert out["used_ai"] is False and "₹25,200" in out["answer"]


def test_rupee_formatting():
    assert assistant.inr(1234567.5) == "₹12,34,567.50" and assistant.inr(-999) == "-₹999" and assistant.inr(None) == "n/a"
