import io
from datetime import date

import openpyxl
import pandas as pd
import pytest

from app.services import exporter, importer

TODAY = date(2025, 12, 1)


def existing(*rows):
    return [{"id": i + 1, "symbol": s, "type": t, "quantity": q, "price": p, "fees": 0.0, "date": d, "company_name": ""} for i, (s, t, q, p, d) in enumerate(rows)]


def run(csv: str, ex=None):
    return importer.validate(importer.parse_file("t.csv", csv.encode()), ex or [], today=TODAY)


HEAD = "date,symbol,type,quantity,price,fees\n"


def statuses(res):
    return [r["status"] for r in res["rows"]]


def test_valid_rows_and_column_aliases():
    res = run("Trade Date,Ticker,Side,Qty,Rate,Brokerage\n15/01/2025,infy.ns,Buy,10,\"1,450.50\",20\n")
    r = res["rows"][0]
    assert r["status"] == "valid" and r["data"] == {"symbol": "INFY.NS", "company_name": None, "sector": None, "type": "BUY",
                                                    "quantity": 10.0, "price": 1450.5, "fees": 20.0, "date": "2025-01-15"}


def test_missing_required_column_is_a_file_error():
    with pytest.raises(importer.ImportFileError, match="Missing required column"):
        importer.parse_file("t.csv", b"symbol,qty\nA,1\n")


def test_unsupported_empty_and_corrupt_files():
    with pytest.raises(importer.ImportFileError):
        importer.parse_file("t.txt", b"x")
    with pytest.raises(importer.ImportFileError):
        importer.parse_file("t.csv", b"")
    with pytest.raises(importer.ImportFileError):
        importer.parse_file("t.xlsx", b"this is not an excel file")
    with pytest.raises(importer.ImportFileError, match="larger"):
        importer.parse_file("t.csv", b"a" * (importer.MAX_BYTES + 1))


def test_row_level_errors_are_specific():
    res = run(HEAD + "2025-01-01,,BUY,1,1,0\n2025-01-01,A B,BUY,1,1,0\n2025-01-01,A,HOLD,1,1,0\n2025-01-01,A,BUY,0,1,0\n"
                     "2025-01-01,A,BUY,abc,1,0\n2025-01-01,A,BUY,1,-5,0\n2025-01-01,A,BUY,1,1,-1\n2025-13-45,A,BUY,1,1,0\n2030-01-01,A,BUY,1,1,0\n,A,BUY,1,1,0\n")
    assert statuses(res) == ["error"] * 10
    joined = " | ".join(" ".join(r["errors"]) for r in res["rows"])
    for needle in ("symbol is missing", "not valid", "BUY or SELL", "greater than zero", "not a number", "cannot be negative", "future", "date is missing"):
        assert needle in joined
    assert [r["row"] for r in res["rows"]][:2] == [2, 3]   # spreadsheet row numbers (header is row 1)


def test_optional_fees_default_to_zero():
    res = run("date,symbol,type,quantity,price\n2025-01-01,A,BUY,1,1\n")
    assert res["rows"][0]["data"]["fees"] == 0.0 and res["rows"][0]["status"] == "valid"


def test_duplicates_against_existing_and_within_file():
    ex = existing(("A", "BUY", 10.0, 100.0, date(2025, 1, 1)))
    res = run(HEAD + "2025-01-01,A,BUY,10,100,0\n2025-02-01,A,BUY,5,100,0\n2025-02-01,A,BUY,5,100,0\n", ex)
    assert statuses(res) == ["duplicate", "valid", "duplicate"]
    assert res["summary"] == {"total": 3, "valid": 1, "duplicates": 2, "errors": 0}


def test_oversell_is_caught_in_the_preview():
    ex = existing(("A", "BUY", 10.0, 100.0, date(2025, 1, 1)))
    res = run(HEAD + "2025-02-01,A,SELL,6,110,0\n2025-02-02,A,SELL,6,110,0\n", ex)
    assert statuses(res) == ["valid", "error"] and "only 4" in res["rows"][1]["errors"][0]


def test_sell_without_any_buy_is_an_error():
    assert statuses(run(HEAD + "2025-02-01,A,SELL,1,1,0\n")) == ["error"]


def test_formula_injection_text_is_rejected():
    res = run("date,symbol,type,quantity,price,company\n2025-01-01,A,BUY,1,1,=HYPERLINK(\"http://x\")\n")
    assert res["rows"][0]["status"] == "error" and "formula" in res["rows"][0]["errors"][0]


def test_excel_upload_with_real_dates():
    buf = io.BytesIO()
    pd.DataFrame({"Date": [pd.Timestamp("2025-01-15")], "Symbol": ["TCS.NS"], "Type": ["BUY"], "Quantity": [3], "Price": [3800.0]}).to_excel(buf, index=False)
    res = importer.validate(importer.parse_file("x.xlsx", buf.getvalue()), [], today=TODAY)
    assert res["rows"][0]["status"] == "valid" and res["rows"][0]["data"]["date"] == "2025-01-15"


def test_template_itself_imports_cleanly():
    res = run(importer.TEMPLATE_CSV)
    assert res["summary"]["errors"] == 0 and res["summary"]["valid"] == 2


# ---------------- export ----------------
def test_csv_export_neutralises_formulas():
    out = exporter.to_csv([{"symbol": "=1+1", "company_name": "+cmd", "quantity": 2}], ["symbol", "company_name", "quantity"]).decode()
    assert "'=1+1" in out and "'+cmd" in out


def test_excel_report_has_the_four_required_sheets():
    holdings = [{"symbol": "A", "company_name": "@x", "sector": "IT", "quantity": 1, "avg_cost": 1, "invested": 1, "current_price": 2,
                 "market_value": 2, "unrealized_pnl": 1, "unrealized_pct": 100, "realized_pnl": 0, "weight": 100}]
    txns = [{"date": date(2025, 1, 1), "symbol": "A", "company_name": "", "type": "BUY", "quantity": 1, "price": 1, "fees": 0, "note": None}]
    data = exporter.to_excel(holdings=holdings, transactions=txns, totals={"market_value": 2}, performance={"has_data": True, "cumulative_return_pct": 5},
                             risk={"risk_score": 10, "warnings": ["w"], "methodology": [{"metric": "m", "how": "h"}], "concentration": {}, "metrics": {}},
                             series=[{"date": "2025-01-01", "value": 2}], monthly=[{"period": "2025-01", "return_pct": 1}], closed=[])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert {"Holdings", "Transactions", "Performance", "Risk analysis"} <= set(wb.sheetnames)
    assert wb["Holdings"]["B2"].value == "'@x"
    assert wb["Transactions"].max_row == 2
