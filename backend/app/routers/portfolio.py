from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PortfolioSnapshot, User
from ..security import get_current_user
from ..services import portfolio
from .common import public

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
PERIOD = Query("ALL", pattern="^(1W|1M|3M|6M|1Y|ALL|1w|1m|3m|6m|1y|all)$")


@router.get("/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    val = public(portfolio.valuation(db, user.id))
    t = val["totals"]
    # Old keys first (kept for compatibility), then the richer data.
    return {
        "invested": t["open_cost"], "current_value": t["market_value"], "gain": t["unrealized_pnl"], "gain_percent": t["unrealized_pct"],
        "allocation": val["sectors"], **val,
    }


@router.get("/performance")
def performance(period: str = PERIOD, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = portfolio.performance_bundle(db, user.id, period)
    out.pop("_df"), out.pop("_full")
    return out


@router.get("/risk")
def risk(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return portfolio.risk_bundle(db, user.id)


@router.get("/snapshots")
def snapshots(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.user_id == user.id).order_by(PortfolioSnapshot.snap_date).all()
    return [{"date": r.snap_date.isoformat(), "market_value": r.market_value, "invested": r.invested, "source": r.source} for r in rows]
