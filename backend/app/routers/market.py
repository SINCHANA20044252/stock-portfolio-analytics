import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import config, ratelimit
from ..database import get_db
from ..models import User
from ..security import get_current_user
from ..services import market as mkt
from ..services import portfolio
from .common import audit, market_error

router = APIRouter(prefix="/market", tags=["market data"])
_last_refresh: dict[int, float] = {}


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    return mkt.get_market_service().status


@router.get("/search")
def search(q: str = Query(..., min_length=2, max_length=60), user: User = Depends(get_current_user)):
    ratelimit.limit_user(user.id, "search")
    try:
        return {"results": mkt.get_market_service().search(q), **mkt.get_market_service().status}
    except mkt.MarketError as exc:
        raise market_error(exc)


@router.get("/quote/{symbol}")
def quote(symbol: str, user: User = Depends(get_current_user)):
    ratelimit.limit_user(user.id, "quote")
    try:
        return mkt.get_market_service().quote(symbol).to_dict()
    except mkt.MarketError as exc:
        raise market_error(exc)


@router.post("/refresh")
def refresh(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Update prices and price history for every symbol you have traded. Cached for 5 minutes."""
    ratelimit.limit_user(user.id, "refresh")
    now = time.time()
    if now - _last_refresh.get(user.id, 0) < config.REFRESH_MIN_INTERVAL_SECONDS:
        raise HTTPException(429, "Prices were just refreshed. Wait a few seconds.")
    try:
        report = portfolio.refresh_prices(db, user.id, mkt.get_market_service())
    except mkt.MarketError as exc:
        raise market_error(exc)
    _last_refresh[user.id] = now
    audit(db, user.id, "refresh_prices", f"{len(report['updated'])} updated, {len(report['failed'])} failed")
    db.commit()
    return report
