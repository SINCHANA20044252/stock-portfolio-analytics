"""Market data behind a provider interface, with caching and clear errors.

Providers:
  yahoo         Yahoo Finance public endpoints. No key. UNOFFICIAL: can change, block or rate-limit.
  alphavantage  Official API. Needs ALPHAVANTAGE_API_KEY. Free tier is small (about 25 calls a day).
  demo          No prices at all. Search works over a built-in symbol directory; quotes/history raise
                ProviderUnavailable. Used when a provider needs a key that is not set. It NEVER invents prices.

Add a provider by subclassing MarketDataProvider and registering it in PROVIDERS.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone

log = logging.getLogger("market")


class MarketError(Exception):
    status_code = 502


class SymbolNotFound(MarketError):
    status_code = 404


class RateLimited(MarketError):
    status_code = 429


class ProviderUnavailable(MarketError):
    status_code = 503


@dataclass
class Quote:
    symbol: str
    name: str | None
    price: float
    previous_close: float | None
    currency: str | None
    as_of: datetime
    source: str

    @property
    def change(self):
        return None if self.previous_close in (None, 0) else round(self.price - self.previous_close, 4)

    @property
    def change_pct(self):
        return None if self.previous_close in (None, 0) else round((self.price - self.previous_close) / self.previous_close * 100, 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["as_of"] = self.as_of.isoformat()
        d["change"], d["change_pct"] = self.change, self.change_pct
        return d


# A small directory so search can suggest a sector. Matching is by symbol without exchange suffix.
DIRECTORY = {
    "INFY": ("Infosys", "IT"), "TCS": ("Tata Consultancy Services", "IT"), "WIPRO": ("Wipro", "IT"), "HCLTECH": ("HCL Technologies", "IT"),
    "TECHM": ("Tech Mahindra", "IT"), "HDFCBANK": ("HDFC Bank", "Banking"), "ICICIBANK": ("ICICI Bank", "Banking"),
    "SBIN": ("State Bank of India", "Banking"), "KOTAKBANK": ("Kotak Mahindra Bank", "Banking"), "AXISBANK": ("Axis Bank", "Banking"),
    "BAJFINANCE": ("Bajaj Finance", "Finance"), "RELIANCE": ("Reliance Industries", "Energy"), "ONGC": ("Oil and Natural Gas Corporation", "Energy"),
    "NTPC": ("NTPC", "Energy"), "POWERGRID": ("Power Grid Corporation", "Energy"), "ITC": ("ITC", "FMCG"), "HINDUNILVR": ("Hindustan Unilever", "FMCG"),
    "NESTLEIND": ("Nestle India", "FMCG"), "BRITANNIA": ("Britannia Industries", "FMCG"), "SUNPHARMA": ("Sun Pharmaceutical", "Pharma"),
    "DRREDDY": ("Dr. Reddy's Laboratories", "Pharma"), "CIPLA": ("Cipla", "Pharma"), "MARUTI": ("Maruti Suzuki", "Auto"),
    "TATAMOTORS": ("Tata Motors", "Auto"), "M&M": ("Mahindra & Mahindra", "Auto"), "BAJAJ-AUTO": ("Bajaj Auto", "Auto"),
    "LT": ("Larsen & Toubro", "Infrastructure"), "ULTRACEMCO": ("UltraTech Cement", "Materials"), "TATASTEEL": ("Tata Steel", "Materials"),
    "ASIANPAINT": ("Asian Paints", "Materials"), "BHARTIARTL": ("Bharti Airtel", "Telecom"), "TITAN": ("Titan Company", "Consumer"),
    "NIFTYBEES": ("Nippon India ETF Nifty 50 BeES", "Index Fund"), "BANKBEES": ("Nippon India ETF Bank BeES", "Index Fund"),
    "GOLDBEES": ("Nippon India ETF Gold BeES", "Gold"),
}


def base_symbol(symbol: str) -> str:
    s = symbol.upper()
    for suf in (".NS", ".BO"):
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def directory_info(symbol: str) -> tuple[str | None, str | None]:
    hit = DIRECTORY.get(base_symbol(symbol))
    return (hit[0], hit[1]) if hit else (None, None)


class MarketDataProvider(ABC):
    name = "base"
    is_live = True

    @abstractmethod
    def search(self, query: str) -> list[dict]: ...

    @abstractmethod
    def quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    def history(self, symbol: str, days: int) -> list[tuple[date, float]]: ...


def _get_json(url: str, headers: dict | None = None, timeout: float = 10.0):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (PortfolioTracker educational project)", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimited("The market data provider is rate limiting requests. Try again in a few minutes.") from exc
        if exc.code == 404:
            raise SymbolNotFound("Symbol not found at the market data provider.") from exc
        raise ProviderUnavailable(f"Market data provider returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ProviderUnavailable("Could not reach the market data provider. Check your internet connection or try later.") from exc


def _range_for(days: int) -> str:
    for limit, rng in ((31, "1mo"), (92, "3mo"), (183, "6mo"), (366, "1y"), (731, "2y"), (1827, "5y"), (3653, "10y")):
        if days <= limit:
            return rng
    return "max"


class YahooProvider(MarketDataProvider):
    name = "yahoo"

    def search(self, query: str) -> list[dict]:
        q = urllib.parse.quote(query)
        data = _get_json(f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=10&newsCount=0")
        out = []
        for r in data.get("quotes", []):
            if r.get("quoteType") not in ("EQUITY", "ETF", "INDEX", "MUTUALFUND"):
                continue
            out.append({"symbol": r.get("symbol"), "name": r.get("longname") or r.get("shortname"),
                        "exchange": r.get("exchDisp") or r.get("exchange"), "type": r.get("quoteType")})
        return [o for o in out if o["symbol"]]

    def _chart(self, symbol: str, rng: str):
        sym = urllib.parse.quote(symbol)
        data = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d")
        chart = data.get("chart", {})
        if chart.get("error"):
            code = (chart["error"] or {}).get("code", "")
            if "not found" in code.lower():
                raise SymbolNotFound(f"No market data found for {symbol}.")
            raise ProviderUnavailable(f"Provider error: {code or 'unknown'}")
        res = (chart.get("result") or [None])[0]
        if not res:
            raise SymbolNotFound(f"No market data found for {symbol}.")
        return res

    def quote(self, symbol: str) -> Quote:
        res = self._chart(symbol, "5d")
        meta = res.get("meta", {})
        price = meta.get("regularMarketPrice")
        if price is None:
            raise SymbolNotFound(f"No price available for {symbol}.")
        closes = [c for c in (res.get("indicators", {}).get("quote", [{}])[0].get("close") or []) if c is not None]
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if len(closes) >= 2:  # last completed session before the latest price
            prev = closes[-2] if abs(closes[-1] - price) < 1e-9 else closes[-1]
        ts = meta.get("regularMarketTime")
        as_of = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
        return Quote(symbol=symbol, name=meta.get("longName") or meta.get("shortName"), price=float(price),
                     previous_close=float(prev) if prev else None, currency=meta.get("currency"), as_of=as_of, source="yahoo")

    def history(self, symbol: str, days: int) -> list[tuple[date, float]]:
        res = self._chart(symbol, _range_for(days))
        stamps = res.get("timestamp") or []
        closes = (res.get("indicators", {}).get("quote", [{}])[0].get("close")) or []
        out = []
        for t, c in zip(stamps, closes):
            if c is not None:
                out.append((datetime.fromtimestamp(t, tz=timezone.utc).date(), float(c)))
        if not out:
            raise SymbolNotFound(f"No price history for {symbol}.")
        return out


class AlphaVantageProvider(MarketDataProvider):
    name = "alphavantage"
    URL = "https://www.alphavantage.co/query"

    def __init__(self, key: str):
        self.key = key

    def _call(self, **params):
        data = _get_json(self.URL + "?" + urllib.parse.urlencode({**params, "apikey": self.key}))
        note = data.get("Note") or data.get("Information")
        if note:
            raise RateLimited("Alpha Vantage limit reached (free keys allow few calls per day). Try again later.")
        if "Error Message" in data:
            raise SymbolNotFound("Symbol not found at Alpha Vantage.")
        return data

    def search(self, query: str) -> list[dict]:
        data = self._call(function="SYMBOL_SEARCH", keywords=query)
        return [{"symbol": m.get("1. symbol"), "name": m.get("2. name"), "exchange": m.get("4. region"), "type": m.get("3. type")}
                for m in data.get("bestMatches", []) if m.get("1. symbol")]

    def quote(self, symbol: str) -> Quote:
        g = self._call(function="GLOBAL_QUOTE", symbol=symbol).get("Global Quote") or {}
        if not g.get("05. price"):
            raise SymbolNotFound(f"No price available for {symbol}.")
        prev = g.get("08. previous close")
        day = g.get("07. latest trading day")
        as_of = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) if day else datetime.now(timezone.utc)
        return Quote(symbol=symbol, name=None, price=float(g["05. price"]), previous_close=float(prev) if prev else None,
                     currency=None, as_of=as_of, source="alphavantage")

    def history(self, symbol: str, days: int) -> list[tuple[date, float]]:
        data = self._call(function="TIME_SERIES_DAILY", symbol=symbol, outputsize="compact")  # last ~100 days on the free tier
        series = data.get("Time Series (Daily)") or {}
        out = sorted((date.fromisoformat(d), float(v["4. close"])) for d, v in series.items())
        if not out:
            raise SymbolNotFound(f"No price history for {symbol}.")
        return out


class DemoProvider(MarketDataProvider):
    """No live data. Clearly labelled; never fabricates a number."""
    name = "demo"
    is_live = False
    MSG = "Demo mode: no market data provider is configured, so live prices are unavailable. Enter prices manually, or set MARKET_DATA_PROVIDER=yahoo."

    def search(self, query: str) -> list[dict]:
        q = query.strip().lower()
        return [{"symbol": f"{s}.NS", "name": n, "exchange": "NSE (directory only)", "type": "EQUITY"}
                for s, (n, _) in DIRECTORY.items() if q in s.lower() or q in n.lower()][:10]

    def quote(self, symbol: str) -> Quote:
        raise ProviderUnavailable(self.MSG)

    def history(self, symbol: str, days: int):
        raise ProviderUnavailable(self.MSG)


class TTLCache:
    def __init__(self):
        self._d: dict = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._d.get(key)
            if hit and hit[0] > time.time():
                return hit[1]
            self._d.pop(key, None)
            return None

    def set(self, key, value, ttl: float):
        with self._lock:
            if len(self._d) > 2000:
                self._d.clear()
            self._d[key] = (time.time() + ttl, value)

    def clear(self):
        with self._lock:
            self._d.clear()


class MarketService:
    """Caching + exchange-suffix resolution on top of a provider."""

    QUOTE_TTL = 300
    SEARCH_TTL = 3600
    HISTORY_TTL = 6 * 3600

    def __init__(self, provider: MarketDataProvider, suffixes: tuple[str, ...] = (".NS", ".BO"), fallback_note: str | None = None):
        self.provider = provider
        self.suffixes = suffixes
        self.cache = TTLCache()
        self.fallback_note = fallback_note

    @property
    def status(self) -> dict:
        return {"provider": self.provider.name, "live": self.provider.is_live, "note": self.fallback_note or (None if self.provider.is_live else DemoProvider.MSG)}

    def candidates(self, symbol: str) -> list[str]:
        s = symbol.strip().upper()
        if "." in s or s.startswith("^") or not self.suffixes:
            return [s]
        return [s + suf for suf in self.suffixes] + [s]

    def _try(self, symbol: str, fn):
        last: MarketError | None = None
        for cand in self.candidates(symbol):
            try:
                return cand, fn(cand)
            except SymbolNotFound as exc:
                last = exc
            # RateLimited / ProviderUnavailable are not retried with other suffixes
        raise last or SymbolNotFound(f"No market data found for {symbol}.")

    def search(self, query: str) -> list[dict]:
        q = query.strip()
        if len(q) < 2:
            return []
        key = ("search", q.lower())
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        results = self.provider.search(q)
        for r in results:
            _, sector = directory_info(r["symbol"])
            r["sector"] = sector
        self.cache.set(key, results, self.SEARCH_TTL)
        return results

    def quote(self, symbol: str) -> Quote:
        key = ("quote", symbol.upper())
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        resolved, q = self._try(symbol, self.provider.quote)
        q.symbol = symbol.upper()  # keep the symbol the user holds, even if we resolved to SYMBOL.NS
        q.resolved_symbol = resolved  # type: ignore[attr-defined]
        self.cache.set(key, q, self.QUOTE_TTL)
        return q

    def history(self, symbol: str, days: int) -> list[tuple[date, float]]:
        key = ("hist", symbol.upper(), _range_for(days))
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        _, rows = self._try(symbol, lambda s: self.provider.history(s, days))
        self.cache.set(key, rows, self.HISTORY_TTL)
        return rows


_service: MarketService | None = None


def build_service_from_env() -> MarketService:
    name = os.getenv("MARKET_DATA_PROVIDER", "yahoo").lower()
    suffixes = tuple(s.strip() for s in os.getenv("DEFAULT_EXCHANGE_SUFFIXES", ".NS,.BO").split(",") if s.strip())
    if name == "yahoo":
        return MarketService(YahooProvider(), suffixes)
    if name == "alphavantage":
        key = os.getenv("ALPHAVANTAGE_API_KEY")
        if key:
            return MarketService(AlphaVantageProvider(key), suffixes)
        return MarketService(DemoProvider(), suffixes, fallback_note="ALPHAVANTAGE_API_KEY is not set, so the app is in demo mode (no live prices).")
    if name == "demo":
        return MarketService(DemoProvider(), suffixes)
    log.warning("Unknown MARKET_DATA_PROVIDER %r; using demo mode", name)
    return MarketService(DemoProvider(), suffixes, fallback_note=f"Unknown MARKET_DATA_PROVIDER {name!r}; running in demo mode.")


def get_market_service() -> MarketService:
    global _service
    if _service is None:
        _service = build_service_from_env()
    return _service


def set_market_service(service: MarketService | None) -> None:
    """For tests: inject a fake provider (or None to rebuild from the environment)."""
    global _service
    _service = service
