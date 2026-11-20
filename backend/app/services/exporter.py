"""CSV and Excel export. Cells that start with = + - @ are prefixed with an apostrophe so spreadsheet
programs do not run them as formulas (CSV/Excel formula injection)."""
from __future__ import annotations

import io

import pandas as pd

FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _safe(v):
    if isinstance(v, str) and v.startswith(FORMULA_CHARS):
        return "'" + v
    return v


def _frame(rows: list[dict], columns: list[str] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if columns:
        df = df.reindex(columns=columns)
    return df.map(_safe) if len(df) else df


HOLDING_COLS = ["symbol", "company_name", "sector", "quantity", "avg_cost", "invested", "current_price", "market_value", "unrealized_pnl", "unrealized_pct", "realized_pnl", "weight"]
TXN_COLS = ["date", "symbol", "company_name", "type", "quantity", "price", "fees", "note"]


def to_csv(rows: list[dict], columns: list[str]) -> bytes:
    return _frame(rows, columns).to_csv(index=False).encode("utf-8")


def pnl_rows(holdings: list[dict], closed: list[dict]) -> list[dict]:
    out = [{"symbol": h["symbol"], "status": "Open", "invested": h.get("invested"), "market_value": h.get("market_value"),
            "unrealized_pnl": h.get("unrealized_pnl"), "realized_pnl": h.get("realized_pnl")} for h in holdings]
    out += [{"symbol": c["symbol"], "status": "Closed", "invested": 0, "market_value": 0, "unrealized_pnl": 0, "realized_pnl": c["realized_pnl"]} for c in closed]
    return out


def to_excel(*, holdings: list[dict], transactions: list[dict], totals: dict, performance: dict, risk: dict, series: list[dict], monthly: list[dict], closed: list[dict]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        _frame(holdings, HOLDING_COLS).to_excel(xw, sheet_name="Holdings", index=False)
        _frame(transactions, TXN_COLS).to_excel(xw, sheet_name="Transactions", index=False)
        _frame(pnl_rows(holdings, closed)).to_excel(xw, sheet_name="Profit and loss", index=False)
        perf_rows = [{"metric": k, "value": v} for k, v in totals.items()]
        perf_rows += [{"metric": f"performance: {k}", "value": v if not isinstance(v, dict) else f"{v.get('period')} ({v.get('return_pct')}%)"}
                      for k, v in performance.items() if k not in ("has_data", "weekly", "monthly")]
        for label, key in (("Weekly", "weekly"), ("Monthly", "monthly")):
            blk = performance.get(key) or {}
            for side in ("best", "worst"):
                v = blk.get(side)
                if v:
                    perf_rows.append({"metric": f"{side} {label.lower()} period", "value": f"{v['period']} ({v['return_pct']}%)"})
        _frame(perf_rows).to_excel(xw, sheet_name="Performance", index=False)
        if monthly:
            _frame(monthly).to_excel(xw, sheet_name="Monthly returns", index=False)
        if series:
            _frame(series).to_excel(xw, sheet_name="Daily history", index=False)
        conc = risk.get("concentration", {})
        met = risk.get("metrics", {})
        risk_rows = [
            {"metric": "Risk score (0-100, higher = riskier)", "value": risk.get("risk_score")},
            {"metric": "Risk category", "value": risk.get("risk_category")},
            {"metric": "Diversification score", "value": risk.get("diversification_score")},
            {"metric": "HHI", "value": conc.get("hhi")},
            {"metric": "Effective holdings", "value": conc.get("effective_holdings")},
            {"metric": "Largest stock", "value": f"{conc.get('top_stock')} ({conc.get('top_stock_pct')}%)" if conc.get("top_stock") else None},
            {"metric": "Largest sector", "value": f"{conc.get('top_sector')} ({conc.get('top_sector_pct')}%)" if conc.get("top_sector") else None},
            {"metric": "Volatility % (annualised)", "value": met.get("volatility_pct")},
            {"metric": "Maximum drawdown %", "value": met.get("max_drawdown_pct")},
            {"metric": "Sharpe ratio", "value": met.get("sharpe")},
        ]
        risk_rows += [{"metric": "Warning", "value": w} for w in risk.get("warnings", [])]
        risk_rows += [{"metric": f"How: {m['metric']}", "value": m["how"]} for m in risk.get("methodology", [])]
        risk_rows.append({"metric": "Note", "value": risk.get("disclaimer")})
        _frame(risk_rows).to_excel(xw, sheet_name="Risk analysis", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 60)
            ws.freeze_panes = "A2"
    return buf.getvalue()
