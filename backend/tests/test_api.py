"""API tests. They need FastAPI, SQLAlchemy and httpx installed (pip install -r requirements.txt -r requirements-dev.txt)."""
import io
from datetime import date, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from app import config, main, ratelimit  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.services import market  # noqa: E402
from tests.fakes import make_service  # noqa: E402

CSRF = {"X-CSRF-Protection": "1"}


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ratelimit.reset_all()
    main.market.__dict__.get("_last_refresh", {}).clear()
    market.set_market_service(make_service())
    with TestClient(main.app) as c:
        yield c
    market.set_market_service(None)


def register(client, email="a@example.com", password="password123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def day(n):  # n days ago, as ISO
    return (date.today() - timedelta(days=n)).isoformat()


def txn(symbol="INFY.NS", type="BUY", qty=10, price=1500, fees=0, d=None, **extra):
    return {"symbol": symbol, "type": type, "quantity": qty, "price": price, "fees": fees, "date": d or day(30), **extra}


# ---------------- auth & sessions ----------------
def test_unauthorized_requests_are_rejected(client):
    for path in ("/transactions", "/positions", "/portfolio/summary", "/portfolio/risk", "/goals", "/audit", "/data/export/holdings.csv", "/auth/me"):
        assert client.get(path).status_code == 401, path
    assert client.get("/transactions", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert client.post("/assistant/ask", json={"question": "what is a sip"}).status_code == 401


def test_register_login_flow_and_validation(client):
    register(client)
    assert client.post("/auth/register", json={"email": "a@example.com", "password": "password123"}).status_code == 409
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "wrongpass1"}).status_code == 401
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).status_code == 200
    assert client.post("/auth/register", json={"email": "bad", "password": "password123"}).status_code == 422
    assert client.post("/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422


def test_cookies_are_httponly_and_csrf_header_is_required(client):
    r = client.post("/auth/register", json={"email": "c@example.com", "password": "password123"})
    cookie = r.headers.get_list("set-cookie")
    assert any("access_token=" in c and "HttpOnly" in c for c in cookie) and any("refresh_token=" in c and "HttpOnly" in c for c in cookie)
    assert client.get("/auth/me").status_code == 200                      # cookie alone is fine for reads
    assert client.post("/transactions", json=txn()).status_code == 403    # but writes need the CSRF header
    assert client.post("/transactions", json=txn(), headers=CSRF).status_code == 201


def test_refresh_rotates_and_reuse_revokes(client):
    client.post("/auth/register", json={"email": "d@example.com", "password": "password123"})
    old_refresh = client.cookies.get("refresh_token", path="/")
    assert client.post("/auth/refresh", headers=CSRF).status_code == 200
    assert client.cookies.get("refresh_token", path="/") != old_refresh
    client.cookies.set("refresh_token", old_refresh, path="/")        # replay the already-used token
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_logout_clears_session(client):
    client.post("/auth/register", json={"email": "e@example.com", "password": "password123"})
    assert client.post("/auth/logout").status_code == 200
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401


def test_login_rate_limit_and_account_lockout(client):
    for _ in range(5):
        client.post("/auth/login", json={"email": "x@example.com", "password": "password123"})
    assert client.post("/auth/login", json={"email": "x@example.com", "password": "password123"}).status_code == 429
    ratelimit.reset_all()
    for _ in range(10):
        client.post("/auth/login", json={"email": f"{_}@example.com", "password": "password123"})
    assert client.post("/auth/login", json={"email": "z@example.com", "password": "password123"}).status_code == 429


def test_legacy_password_hash_still_works_and_is_upgraded(client):
    import hashlib

    from app import security
    from app.database import SessionLocal
    from app.models import User
    salt = b"0123456789abcdef"
    legacy = salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", b"password123", salt, 200_000).hex()
    with SessionLocal() as db:
        db.add(User(email="old@example.com", password_hash=legacy))
        db.commit()
    assert client.post("/auth/login", json={"email": "old@example.com", "password": "password123"}).status_code == 200
    with SessionLocal() as db:
        assert db.query(User).filter_by(email="old@example.com").one().password_hash.startswith(security.PASSWORD_SCHEME)


def test_change_password(client):
    h = register(client)
    assert client.post("/auth/change-password", json={"current_password": "nope12345", "new_password": "newpassword1"}, headers=h).status_code == 400
    assert client.post("/auth/change-password", json={"current_password": "password123", "new_password": "newpassword1"}, headers=h).status_code == 200
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "newpassword1"}).status_code == 200


# ---------------- transactions ----------------
def test_buy_sell_and_positions(client):
    h = register(client)
    assert client.post("/transactions", json=txn(qty=10, price=100, fees=10), headers=h).status_code == 201
    r = client.post("/transactions", json=txn(type="SELL", qty=4, price=120, fees=5, d=day(10)), headers=h)
    assert r.status_code == 201
    pos = client.get("/positions", headers=h).json()
    row = pos["holdings"][0]
    assert row["quantity"] == 6 and row["avg_cost"] == pytest.approx(101.0)       # (1000+10)/10
    assert pos["totals"]["realized_pnl"] == pytest.approx(4 * 120 - 5 - 4 * 101)  # 71
    sells = client.get("/transactions?type=SELL", headers=h).json()["items"]
    assert sells[0]["realized_pnl"] == pytest.approx(71)


def test_cannot_sell_more_than_owned(client):
    h = register(client)
    client.post("/transactions", json=txn(qty=5), headers=h)
    r = client.post("/transactions", json=txn(type="SELL", qty=6, d=day(5)), headers=h)
    assert r.status_code == 409 and "only 5" in r.json()["detail"]


def test_edit_and_delete_must_keep_later_sales_valid(client):
    h = register(client)
    buy = client.post("/transactions", json=txn(qty=10, d=day(30)), headers=h).json()
    client.post("/transactions", json=txn(type="SELL", qty=8, d=day(10)), headers=h)
    assert client.put(f"/transactions/{buy['id']}", json=txn(qty=5, d=day(30)), headers=h).status_code == 409
    assert client.delete(f"/transactions/{buy['id']}?confirm=true", headers=h).status_code == 409
    assert client.put(f"/transactions/{buy['id']}", json=txn(qty=12, d=day(30)), headers=h).status_code == 200


def test_delete_needs_confirmation(client):
    h = register(client)
    t = client.post("/transactions", json=txn(), headers=h).json()
    assert client.delete(f"/transactions/{t['id']}", headers=h).status_code == 400
    assert client.delete(f"/transactions/{t['id']}?confirm=true", headers=h).status_code == 204
    assert client.get("/transactions", headers=h).json()["total"] == 0


@pytest.mark.parametrize("bad", [{"quantity": 0}, {"quantity": -1}, {"price": 0}, {"price": -5}, {"fees": -1}, {"date": "2999-01-01"},
                                 {"date": "not-a-date"}, {"type": "HOLD"}, {"symbol": "A B"}, {"symbol": ""}, {"company_name": "=cmd"}])
def test_invalid_transactions_are_rejected(client, bad):
    h = register(client)
    assert client.post("/transactions", json={**txn(), **bad}, headers=h).status_code == 422


def test_transaction_filters(client):
    h = register(client)
    client.post("/transactions", json=txn("INFY.NS", d=day(60)), headers=h)
    client.post("/transactions", json=txn("TCS.NS", price=3800, d=day(20)), headers=h)
    client.post("/transactions", json=txn("TCS.NS", "SELL", 2, 3900, d=day(5)), headers=h)
    q = lambda s: client.get("/transactions" + s, headers=h).json()["total"]  # noqa: E731
    assert q("") == 3 and q("?symbol=tcs.ns") == 2 and q("?type=SELL") == 1
    assert q(f"?date_from={day(30)}") == 2 and q(f"?date_to={day(30)}") == 1


def test_users_cannot_touch_each_others_data(client):
    alice, bob = register(client, "alice@example.com"), register(client, "bob@example.com")
    t = client.post("/transactions", json=txn(), headers=alice).json()
    g = client.post("/goals", json={"name": "House", "target_amount": 100000, "years": 5}, headers=alice).json()
    assert client.get("/transactions", headers=bob).json()["total"] == 0
    assert client.get("/positions", headers=bob).json()["holdings"] == []
    assert client.put(f"/transactions/{t['id']}", json=txn(), headers=bob).status_code == 404
    assert client.delete(f"/transactions/{t['id']}?confirm=true", headers=bob).status_code == 404
    assert client.delete(f"/goals/{g['id']}", headers=bob).status_code == 404
    assert client.get("/goals", headers=bob).json() == []
    assert client.get("/audit", headers=bob).json() != client.get("/audit", headers=alice).json()


# ---------------- legacy /holdings ----------------
HOLDING = {"symbol": "infy", "sector": "IT", "quantity": 10, "buy_price": 1450, "current_price": 1520}


def test_legacy_holdings_api_still_works(client):
    h = register(client)
    c = client.post("/holdings", json=HOLDING, headers=h).json()
    assert c["symbol"] == "INFY" and len(client.get("/holdings", headers=h).json()) == 1
    s = client.get("/portfolio/summary", headers=h).json()
    assert s["current_value"] == 15200 and s["gain"] == 700 and s["allocation"][0]["sector"] == "IT"
    assert client.put(f"/holdings/{c['id']}", json={**HOLDING, "current_price": 1600}, headers=h).json()["current_price"] == 1600
    assert client.delete(f"/holdings/{c['id']}", headers=h).status_code == 204
    assert client.get("/holdings", headers=h).json() == []


# ---------------- portfolio, risk, market ----------------
def test_manual_price_and_missing_price_handling(client):
    h = register(client)
    client.post("/transactions", json=txn("ZZZ", price=50, qty=2), headers=h)    # price hint = last trade
    row = client.get("/positions", headers=h).json()["holdings"][0]
    assert row["price_source"] == "transaction"
    pid = row["id"]
    assert client.patch(f"/positions/{pid}", json={"current_price": 60, "sector": "IT"}, headers=h).status_code == 200
    row = client.get("/positions", headers=h).json()["holdings"][0]
    assert row["current_price"] == 60 and row["price_source"] == "manual" and row["sector"] == "IT"
    assert client.patch(f"/positions/{pid}", json={"current_price": -1}, headers=h).status_code == 422


def test_market_search_quote_and_errors(client):
    h = register(client)
    assert client.get("/market/search?q=infy", headers=h).json()["results"][0]["symbol"] == "INFY.NS"
    assert client.get("/market/quote/INFY", headers=h).json()["price"] == 1600
    assert client.get("/market/quote/NOPE", headers=h).status_code == 404
    assert client.get("/market/quote/LIMITED.NS", headers=h).status_code == 429
    assert client.get("/market/search?q=a", headers=h).status_code == 422


def test_demo_mode_refresh_is_clearly_unavailable(client):
    h = register(client)
    market.set_market_service(market.MarketService(market.DemoProvider()))
    client.post("/transactions", json=txn(), headers=h)
    r = client.post("/market/refresh", headers=h)
    assert r.status_code == 503 and "Demo mode" in r.json()["detail"]
    assert client.get("/market/status", headers=h).json()["live"] is False


def test_refresh_updates_prices_history_and_enables_analytics(client, monkeypatch):
    monkeypatch.setattr(config, "REFRESH_MIN_INTERVAL_SECONDS", 0)
    h = register(client)
    client.post("/transactions", json=txn("INFY.NS", qty=10, price=1500, d=day(40)), headers=h)
    client.post("/transactions", json=txn("MISSING.NS", qty=1, price=10, d=day(40)), headers=h)
    perf = client.get("/portfolio/performance", headers=h).json()
    assert perf["has_data"] is False and perf["notes"]          # honest empty state before any prices exist
    rep = client.post("/market/refresh", headers=h).json()
    assert rep["updated"][0]["price"] == 1600 and rep["failed"][0]["symbol"] == "MISSING.NS"
    row = [r for r in client.get("/positions", headers=h).json()["holdings"] if r["symbol"] == "INFY.NS"][0]
    assert row["current_price"] == 1600 and row["price_source"] == "market" and row["day_change_pct"] == pytest.approx(1.27, abs=0.01)
    perf = client.get("/portfolio/performance?period=1M", headers=h).json()
    assert perf["has_data"] and perf["excluded_symbols"] == ["MISSING.NS"] and perf["period"] == "1M"
    assert client.get("/portfolio/performance?period=2Y", headers=h).status_code == 422
    risk = client.get("/portfolio/risk", headers=h).json()
    assert "methodology" in risk and risk["metrics"]["notes"] is not None
    assert client.get("/portfolio/snapshots", headers=h).status_code == 200


# ---------------- goals ----------------
def test_goal_plan_compare_and_crud(client):
    h = register(client)
    g = client.post("/goal/plan", json={"target": 100000, "years": 5, "monthly_sip": 500}, headers=h).json()
    assert len(g["series"]) == 5 and g["is_estimate"] and g["starting_value"] == 0
    assert client.post("/goal/plan", json={"target": 100000, "years": 0}, headers=h).status_code == 422
    cmp_ = client.post("/goal/compare", json={"target": 500000, "scenarios": [{"years": 5, "annual_return_pct": 8}, {"years": 10, "annual_return_pct": 8, "monthly_sip": 1000}]}, headers=h).json()
    assert cmp_["scenarios"][0]["sip_was_solved"] and not cmp_["scenarios"][1]["sip_was_solved"]
    saved = client.post("/goals", json={"name": "House", "target_amount": 500000, "years": 8, "monthly_sip": 3000}, headers=h).json()
    assert saved["projection"]["series"] and client.put(f"/goals/{saved['id']}", json={"name": "Flat", "target_amount": 1, "years": 2}, headers=h).json()["name"] == "Flat"
    assert client.delete(f"/goals/{saved['id']}", headers=h).status_code == 204


# ---------------- import / export ----------------
def upload(client, h, text, name="t.csv"):
    return client.post("/data/import/preview", files={"file": (name, io.BytesIO(text.encode()), "text/csv")}, headers=h)


CSV = "date,symbol,type,quantity,price,fees\n{a},INFY.NS,BUY,10,1500,10\n{b},INFY.NS,SELL,4,1600,5\n{a},INFY.NS,SELL,500,1,0\n"


def test_import_preview_confirm_flow(client):
    h = register(client)
    r = upload(client, h, CSV.format(a=day(30), b=day(10)))
    body = r.json()
    assert r.status_code == 200 and body["summary"] == {"total": 3, "valid": 2, "duplicates": 0, "errors": 1}
    assert client.get("/transactions", headers=h).json()["total"] == 0                    # nothing saved yet
    assert client.post(f"/data/import/{body['import_id']}/confirm", json={}, headers=h).status_code == 400   # errors need explicit opt-in
    ok = client.post(f"/data/import/{body['import_id']}/confirm", json={"import_valid_only": True}, headers=h)
    assert ok.json()["imported"] == 2 and client.get("/transactions", headers=h).json()["total"] == 2
    again = upload(client, h, CSV.format(a=day(30), b=day(10))).json()                   # same file: now duplicates
    assert again["summary"]["duplicates"] == 2


def test_import_cancel_and_isolation(client):
    alice, bob = register(client, "alice@example.com"), register(client, "bob@example.com")
    imp = upload(client, alice, CSV.format(a=day(30), b=day(10))).json()["import_id"]
    assert client.post(f"/data/import/{imp}/confirm", json={"import_valid_only": True}, headers=bob).status_code == 404
    assert client.delete(f"/data/import/{imp}", headers=alice).status_code == 204
    assert client.post(f"/data/import/{imp}/confirm", json={"import_valid_only": True}, headers=alice).status_code == 404


def test_import_rejects_bad_files(client):
    h = register(client)
    assert upload(client, h, "a,b\n1,2\n").status_code == 400
    assert upload(client, h, "x", name="t.txt").status_code == 400
    assert upload(client, h, "", name="t.csv").status_code == 400


def test_exports(client):
    import openpyxl
    h = register(client)
    client.post("/transactions", json=txn(company_name="Infosys"), headers=h)
    for name in ("holdings.csv", "transactions.csv", "pnl.csv", "analytics.csv"):
        r = client.get(f"/data/export/{name}", headers=h)
        assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "INFY.NS" in client.get("/data/export/transactions.csv", headers=h).text
    x = client.get("/data/export/report.xlsx", headers=h)
    assert {"Holdings", "Transactions", "Performance", "Risk analysis"} <= set(openpyxl.load_workbook(io.BytesIO(x.content)).sheetnames)


# ---------------- assistant, settings ----------------
def test_assistant_uses_only_the_callers_data(client):
    alice, bob = register(client, "alice@example.com"), register(client, "bob@example.com")
    client.post("/transactions", json=txn(qty=10, price=1000), headers=alice)
    a = client.post("/assistant/ask", json={"question": "What is my total portfolio value?"}, headers=alice).json()
    b = client.post("/assistant/ask", json={"question": "What is my total portfolio value?"}, headers=bob).json()
    assert a["grounded"] and "10,000" in a["answer"]
    assert "no holdings" in b["answer"].lower() and "10,000" not in b["answer"]
    assert client.post("/assistant/ask", json={"question": "What is a SIP?"}, headers=bob).json()["sources"]
    assert client.post("/assistant/ask", json={"question": "hi"}, headers=bob).status_code == 422


def test_preferences_audit_and_security_headers(client):
    h = register(client)
    assert client.get("/settings/preferences", headers=h).json()["theme"] == "system"
    assert client.put("/settings/preferences", json={"theme": "dark", "default_period": "1Y"}, headers=h).json()["theme"] == "dark"
    assert client.put("/settings/preferences", json={"theme": "neon"}, headers=h).status_code == 422
    client.post("/transactions", json=txn(), headers=h)
    assert {"register", "buy"} <= {e["action"] for e in client.get("/audit", headers=h).json()}
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
