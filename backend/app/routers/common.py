from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import AuditLog
from ..services import accounting, market


def audit(db: Session, user_id: int, action: str, detail: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:255]))


def public(val: dict) -> dict:
    """Strip internal objects from a valuation before returning it as JSON."""
    return {k: v for k, v in val.items() if k not in ("ledger", "transactions")}


def check_ledger(transactions: list[dict]) -> None:
    """Replay the full history; a transaction list that would sell shares you do not hold is a 409."""
    try:
        accounting.replay(transactions)
    except accounting.AccountingError as exc:
        raise HTTPException(409, str(exc)) from exc


def market_error(exc: market.MarketError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))
