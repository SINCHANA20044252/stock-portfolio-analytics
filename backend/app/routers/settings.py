from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, User, UserPreference
from ..schemas import Preferences
from ..security import get_current_user
from .common import audit

router = APIRouter(tags=["settings"])


def _prefs(db: Session, user: User) -> UserPreference:
    p = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if p is None:
        p = UserPreference(user_id=user.id)
        db.add(p)
        db.flush()
    return p


def _out(p: UserPreference) -> dict:
    return {"theme": p.theme, "default_period": p.default_period, "benchmark_symbol": p.benchmark_symbol}


@router.get("/settings/preferences")
def get_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _prefs(db, user)
    db.commit()
    return _out(p)


@router.put("/settings/preferences")
def put_preferences(body: Preferences, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _prefs(db, user)
    p.theme, p.default_period = body.theme, body.default_period
    p.benchmark_symbol = (body.benchmark_symbol or "").strip().upper() or None
    audit(db, user.id, "update_preferences", f"theme={p.theme}")
    db.commit()
    return _out(p)


@router.get("/audit")
def audit_log(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(AuditLog).filter(AuditLog.user_id == user.id).order_by(AuditLog.id.desc()).limit(50).all()
    return [{"action": r.action, "detail": r.detail, "at": r.created_at.isoformat()} for r in rows]
