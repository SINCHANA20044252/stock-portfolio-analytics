from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Position, Transaction, User
from ..schemas import HoldingIn, PositionPatch, TransactionIn, TransactionOut
from ..security import get_current_user
from ..services import accounting, portfolio
from .common import audit, check_ledger, public

router = APIRouter(tags=["transactions"])


def _out(t: Transaction, realized: dict | None = None) -> dict:
    r = (realized or {}).get(t.id)
    return {"id": t.id, "symbol": t.symbol, "company_name": t.company_name, "type": t.type, "quantity": t.quantity,
            "price": t.price, "fees": t.fees or 0.0, "date": t.trade_date, "note": t.note, "source": t.source,
            "realized_pnl": round(float(r), 2) if r is not None else None}


def _own(db: Session, user: User, txn_id: int) -> Transaction:
    t = db.query(Transaction).filter(Transaction.id == txn_id, Transaction.user_id == user.id).first()
    if not t:
        raise HTTPException(404, "Transaction not found")
    return t


def _as_dict(body: TransactionIn, txn_id: int) -> dict:
    return {"id": txn_id, "symbol": body.symbol, "company_name": body.company_name or "", "type": body.type,
            "quantity": body.quantity, "price": body.price, "fees": body.fees, "date": body.date}


@router.get("/transactions")
def list_transactions(
    symbol: str | None = Query(None, max_length=20),
    type: str | None = Query(None, pattern="^(BUY|SELL|buy|sell)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    all_txns = portfolio.load_transactions(db, user.id)
    realized = accounting.replay(all_txns).realized_by_txn if all_txns else {}
    q = db.query(Transaction).filter(Transaction.user_id == user.id)
    if symbol:
        q = q.filter(Transaction.symbol == symbol.strip().upper())
    if type:
        q = q.filter(Transaction.type == type.upper())
    if date_from:
        q = q.filter(Transaction.trade_date >= date_from)
    if date_to:
        q = q.filter(Transaction.trade_date <= date_to)
    total = q.count()
    rows = q.order_by(Transaction.trade_date.desc(), Transaction.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [_out(t, realized) for t in rows]}


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = portfolio.load_transactions(db, user.id)
    check_ledger(existing + [_as_dict(body, 10**12)])  # also rejects selling more than is held
    t = Transaction(user_id=user.id, symbol=body.symbol, company_name=body.company_name, type=body.type, quantity=body.quantity,
                    price=body.price, fees=body.fees, trade_date=body.date, note=body.note, source="manual")
    db.add(t)
    portfolio.ensure_position(db, user.id, body.symbol, body.company_name, body.sector, price_hint=body.price)
    db.flush()
    audit(db, user.id, f"{body.type.lower()}", f"{body.symbol} x{body.quantity} @ {body.price}")
    db.commit()
    db.refresh(t)
    return _out(t)


@router.put("/transactions/{txn_id}", response_model=TransactionOut)
def update_transaction(txn_id: int, body: TransactionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _own(db, user, txn_id)
    others = [x for x in portfolio.load_transactions(db, user.id) if x["id"] != txn_id]
    check_ledger(others + [_as_dict(body, txn_id)])  # an edit must keep every later sale covered
    t.symbol, t.company_name, t.type = body.symbol, body.company_name, body.type
    t.quantity, t.price, t.fees, t.trade_date, t.note = body.quantity, body.price, body.fees, body.date, body.note
    portfolio.ensure_position(db, user.id, body.symbol, body.company_name, body.sector)
    audit(db, user.id, "edit_transaction", f"#{txn_id} {body.symbol}")
    db.commit()
    db.refresh(t)
    return _out(t)


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, confirm: bool = Query(False), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not confirm:
        raise HTTPException(400, "Deleting needs confirmation: send ?confirm=true")
    t = _own(db, user, txn_id)
    others = [x for x in portfolio.load_transactions(db, user.id) if x["id"] != txn_id]
    check_ledger(others)  # deleting a buy must not leave a later sell without shares
    audit(db, user.id, "delete_transaction", f"#{txn_id} {t.symbol}")
    db.delete(t)
    db.commit()


# ---------- positions (what you hold now; derived from transactions) ----------
@router.get("/positions")
def positions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return public(portfolio.valuation(db, user.id))


@router.patch("/positions/{position_id}")
def patch_position(position_id: int, body: PositionPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == position_id, Position.user_id == user.id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    from datetime import datetime, timezone
    if body.sector:
        pos.sector = body.sector
    if body.company_name:
        pos.company_name = body.company_name
    if body.current_price is not None:
        pos.current_price, pos.prev_close = body.current_price, None
        pos.price_source, pos.price_updated_at = "manual", datetime.now(timezone.utc)
    audit(db, user.id, "update_position", pos.symbol)
    db.commit()
    return {"id": pos.id, "symbol": pos.symbol, "sector": pos.sector, "company_name": pos.company_name,
            "current_price": pos.current_price, "price_source": pos.price_source}


# ---------- legacy /holdings API (kept for older clients; new code should use /transactions and /positions) ----------
def _holding_out(pos: Position, row: dict) -> dict:
    return {"id": pos.id, "symbol": row["symbol"], "sector": row["sector"], "quantity": row["quantity"],
            "buy_price": row["avg_cost"], "current_price": row["current_price"] if row["current_price"] is not None else 0}


@router.get("/holdings", deprecated=True)
def list_holdings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    val = portfolio.valuation(db, user.id)
    pos = portfolio.load_positions(db, user.id)
    return [_holding_out(pos[h["symbol"]], h) for h in val["holdings"] if h["symbol"] in pos]


@router.post("/holdings", status_code=201, deprecated=True)
def add_holding(body: HoldingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Legacy: records a BUY dated today and sets the current price by hand."""
    from datetime import datetime, timezone
    check_ledger(portfolio.load_transactions(db, user.id))
    db.add(Transaction(user_id=user.id, symbol=body.symbol, type="BUY", quantity=body.quantity, price=body.buy_price,
                       fees=0.0, trade_date=date.today(), note="Added via legacy holdings API", source="manual"))
    pos = portfolio.ensure_position(db, user.id, body.symbol, None, body.sector)
    pos.sector = body.sector
    pos.current_price, pos.prev_close, pos.price_source, pos.price_updated_at = body.current_price, None, "manual", datetime.now(timezone.utc)
    audit(db, user.id, "add_holding", f"{body.symbol} x{body.quantity}")
    db.commit()
    val = portfolio.valuation(db, user.id)
    row = next(h for h in val["holdings"] if h["symbol"] == body.symbol)
    db.refresh(pos)
    return _holding_out(pos, row)


@router.put("/holdings/{holding_id}", deprecated=True)
def update_holding(holding_id: int, body: HoldingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Legacy: only sector and current price can change here. Quantity and cost come from transactions."""
    from datetime import datetime, timezone
    pos = db.query(Position).filter(Position.id == holding_id, Position.user_id == user.id).first()
    if not pos:
        raise HTTPException(404, "Holding not found")
    pos.sector = body.sector
    pos.current_price, pos.prev_close, pos.price_source, pos.price_updated_at = body.current_price, None, "manual", datetime.now(timezone.utc)
    audit(db, user.id, "update_holding", pos.symbol)
    db.commit()
    val = portfolio.valuation(db, user.id)
    row = next((h for h in val["holdings"] if h["symbol"] == pos.symbol), None)
    if row is None:
        raise HTTPException(404, "Holding not found")
    return _holding_out(pos, row)


@router.delete("/holdings/{holding_id}", status_code=204, deprecated=True)
def delete_holding(holding_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Legacy: removes every transaction for this symbol and the position itself."""
    pos = db.query(Position).filter(Position.id == holding_id, Position.user_id == user.id).first()
    if not pos:
        raise HTTPException(404, "Holding not found")
    db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.symbol == pos.symbol).delete(synchronize_session=False)
    audit(db, user.id, "delete_holding", pos.symbol)
    db.delete(pos)
    db.commit()
