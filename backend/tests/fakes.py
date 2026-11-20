from datetime import date, datetime, timedelta, timezone

from app.services import market


class FakeProvider(market.MarketDataProvider):
    """Deterministic fake: no network. Prices are fixed numbers chosen for the tests."""
    name = "fake"
    PRICES = {"INFY.NS": (1600.0, 1580.0), "TCS.NS": (3800.0, 3790.0), "^NSEI": (24000.0, 23900.0)}

    def __init__(self):
        self.calls = 0

    def search(self, query):
        return [{"symbol": "INFY.NS", "name": "Infosys", "exchange": "NSE", "type": "EQUITY"}] if "inf" in query.lower() else []

    def quote(self, symbol):
        self.calls += 1
        if symbol == "LIMITED.NS":
            raise market.RateLimited("rate limited")
        if symbol not in self.PRICES:
            raise market.SymbolNotFound(f"No market data found for {symbol}.")
        p, prev = self.PRICES[symbol]
        return market.Quote(symbol, "Fake Co", p, prev, "INR", datetime.now(timezone.utc), "fake")

    def history(self, symbol, days):
        if symbol not in self.PRICES:
            raise market.SymbolNotFound(f"No price history for {symbol}.")
        end = date.today()
        base = self.PRICES[symbol][0]
        out, d, i = [], end - timedelta(days=days), 0
        while d <= end:
            if d.weekday() < 5:
                out.append((d, round(base * (0.9 + 0.001 * i), 2)))
                i += 1
            d += timedelta(days=1)
        return out


def make_service():
    return market.MarketService(FakeProvider())
