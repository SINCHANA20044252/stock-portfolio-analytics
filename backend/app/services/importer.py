"""CSV / Excel import: parse, validate every row, detect duplicates, simulate the result.

Nothing is written here. `validate` returns a preview where every row is `valid`, `duplicate` or `error`
with human-readable reasons, so the user can confirm or cancel before anything is saved.
"""
from __future__ import annotations

import io
import math
import re
from datetime import date, datetime

import pandas as pd

from .accounting import AccountingError, replay

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-_.^]{0,19}$")
MIN_DATE = date(1990, 1, 1)
FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")

ALIASES = {
    "symbol": ["symbol", "ticker", "stock", "scrip", "instrument", "stock_symbol"],
    "company_name": ["company_name", "company", "name", "stock_name"],
    "type": ["type", "transaction_type", "side", "action", "buy_sell", "trade_type"],
    "quantity": ["quantity", "qty", "shares", "units", "no_of_shares"],
    "price": ["price", "transaction_price", "rate", "trade_price", "avg_price"],
    "date": ["date", "transaction_date", "trade_date"],
    "fees": ["fees", "fee", "brokerage", "charges", "brokerage_charges", "transaction_charges"],
    "sector": ["sector", "industry"],
}
REQUIRED = ["symbol", "type", "quantity", "price", "date"]
TYPE_MAP = {"buy": "BUY", "b": "BUY", "purchase": "BUY", "bought": "BUY", "sell": "SELL", "s": "SELL", "sale": "SELL", "sold": "SELL"}
TEMPLATE_CSV = "date,symbol,company_name,type,quantity,price,fees,sector\n2025-01-15,INFY.NS,Infosys,BUY,10,1450.50,20,IT\n2025-03-10,INFY.NS,Infosys,SELL,4,1520,15,IT\n"


class ImportFileError(ValueError):
    """The file itself cannot be used (wrong type, too big, missing columns)."""


def _norm_col(c) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def parse_file(filename: str, content: bytes) -> pd.DataFrame:
    if not content:
        raise ImportFileError("The file is empty.")
    if len(content) > MAX_BYTES:
        raise ImportFileError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    name = (filename or "").lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, encoding="utf-8-sig", skip_blank_lines=True)
        elif name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(content), dtype=object, engine="openpyxl")
        else:
            raise ImportFileError("Only .csv and .xlsx files are supported.")
    except ImportFileError:
        raise
    except Exception as exc:  # corrupt files, wrong encoding, not really an xlsx...
        raise ImportFileError(f"Could not read the file ({type(exc).__name__}). Check it is a valid CSV or Excel file.") from exc
    if len(df) > MAX_ROWS:
        raise ImportFileError(f"Too many rows ({len(df)}). The limit is {MAX_ROWS}.")

    df.columns = [_norm_col(c) for c in df.columns]
    rename = {}
    for canon, names in ALIASES.items():
        for n in names:
            if n in df.columns and canon not in rename.values():
                rename[n] = canon
                break
    df = df.rename(columns=rename)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ImportFileError("Missing required column(s): " + ", ".join(missing) + ". Found: " + (", ".join(df.columns) or "none") + ".")
    return df


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip()) or v is pd.NaT


def _num(v, field, errors, allow_blank=False, default=None):
    if _blank(v):
        if allow_blank:
            return default
        errors.append(f"{field} is missing")
        return None
    try:
        x = float(str(v).replace(",", "").strip()) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        errors.append(f"{field} is not a number ({v!r})")
        return None
    if math.isnan(x) or math.isinf(x):
        errors.append(f"{field} is not a valid number")
        return None
    return x


def _date(v, errors, today: date):
    if _blank(v):
        errors.append("date is missing")
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        s = str(v).strip()
        d = None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y"):
            try:
                d = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            try:  # ISO timestamp such as 2025-01-15 00:00:00
                d = datetime.fromisoformat(s).date()
            except ValueError:
                errors.append(f"date {s!r} is not valid (use YYYY-MM-DD or DD/MM/YYYY)")
                return None
    if d > today:
        errors.append(f"date {d} is in the future")
        return None
    if d < MIN_DATE:
        errors.append(f"date {d} is before {MIN_DATE.year}")
        return None
    return d


def _text(v, field, errors, maxlen):
    if _blank(v):
        return None
    s = str(v).strip()
    if s.startswith(FORMULA_CHARS):
        errors.append(f"{field} starts with a formula character ({s[0]!r}); remove it")
        return None
    return s[:maxlen]


def duplicate_key(t: dict) -> tuple:
    return (t["symbol"], t["type"], t["date"], round(float(t["quantity"]), 6), round(float(t["price"]), 4))


def validate(df: pd.DataFrame, existing: list[dict], today: date | None = None) -> dict:
    """existing: the user's current transactions (dicts for accounting.replay)."""
    today = today or date.today()
    seen = {duplicate_key(t) for t in existing}
    rows, candidates = [], []
    for i, rec in enumerate(df.to_dict("records")):
        n = i + 2  # spreadsheet row number: header is row 1
        errors: list[str] = []
        sym = rec.get("symbol")
        sym = None if _blank(sym) else str(sym).strip().upper()
        if sym is None:
            errors.append("symbol is missing")
        elif not SYMBOL_RE.match(sym):
            errors.append(f"symbol {sym!r} is not valid (letters, digits, & - _ . ^ only, max 20)")
        raw_type = rec.get("type")
        ttype = None if _blank(raw_type) else TYPE_MAP.get(str(raw_type).strip().lower())
        if ttype is None:
            errors.append("type must be BUY or SELL" if not _blank(raw_type) else "type is missing")
        qty = _num(rec.get("quantity"), "quantity", errors)
        if qty is not None and qty <= 0:
            errors.append("quantity must be greater than zero")
        price = _num(rec.get("price"), "price", errors)
        if price is not None and price <= 0:
            errors.append("price must be greater than zero")
        fees = _num(rec.get("fees"), "fees", errors, allow_blank=True, default=0.0)
        if fees is not None and fees < 0:
            errors.append("fees cannot be negative")
        d = _date(rec.get("date"), errors, today)
        company = _text(rec.get("company_name"), "company_name", errors, 120)
        sector = _text(rec.get("sector"), "sector", errors, 50)

        item = {"row": n, "status": "valid", "errors": errors,
                "data": {"symbol": sym, "company_name": company, "sector": sector, "type": ttype,
                         "quantity": qty, "price": price, "fees": fees, "date": d.isoformat() if d else None}}
        if errors:
            item["status"] = "error"
        else:
            t = {"id": None, "symbol": sym, "company_name": company or "", "type": ttype, "quantity": qty,
                 "price": price, "fees": fees or 0.0, "date": d}
            key = duplicate_key(t)
            if key in seen:
                item["status"] = "duplicate"
                item["errors"] = ["Same symbol, type, date, quantity and price already exists (or appears earlier in this file)."]
            else:
                seen.add(key)
                candidates.append((item, t))
        rows.append(item)

    # Simulate: would the valid rows make any sale exceed the shares held at that point?
    live = list(candidates)
    for _ in range(len(live) + 1):
        trial = []
        for k, (_, t) in enumerate(live):
            trial.append({**t, "id": f"import-{k}"})
        try:
            replay(existing + trial)
            break
        except AccountingError as exc:
            if isinstance(exc.txn_id, str) and exc.txn_id.startswith("import-"):
                k = int(exc.txn_id.split("-")[1])
                item = live[k][0]
                item["status"] = "error"
                item["errors"] = [str(exc)]
                live.pop(k)
            else:  # existing data was already inconsistent; do not block on it
                break

    summary = {
        "total": len(rows),
        "valid": sum(r["status"] == "valid" for r in rows),
        "duplicates": sum(r["status"] == "duplicate" for r in rows),
        "errors": sum(r["status"] == "error" for r in rows),
    }
    return {"rows": rows, "summary": summary}
