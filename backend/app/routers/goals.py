from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Goal, User
from ..schemas import CompareIn, GoalIn, GoalSave
from ..security import get_current_user
from ..services import portfolio, sip
from .common import audit

router = APIRouter(tags=["goals"])


def _portfolio_value(db: Session, user: User) -> float:
    return portfolio.valuation(db, user.id)["totals"]["market_value"]


def _start(db: Session, user: User, override):
    return float(override) if override is not None else _portfolio_value(db, user)


def _wrap(fn, *a):
    try:
        return fn(*a)
    except sip.PlanError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/goal/plan")
def goal_plan(body: GoalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    start = _start(db, user, body.starting_amount)
    result = _wrap(sip.goal_projection, start, body.monthly_sip, body.annual_return_pct, body.years, body.target)
    result["starting_value"] = start
    return result


@router.post("/goal/compare")
def goal_compare(body: CompareIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    start = _start(db, user, body.starting_amount)
    plans = _wrap(sip.compare_scenarios, start, body.target, [s.model_dump() for s in body.scenarios])
    return {"starting_value": start, "target": body.target, "scenarios": plans}


def _goal_out(g: Goal, start: float) -> dict:
    s = g.starting_amount if g.starting_amount is not None else start
    plan = sip.goal_projection(s, g.monthly_sip, g.expected_return_pct, g.years, g.target_amount)
    return {"id": g.id, "name": g.name, "target_amount": g.target_amount, "years": g.years, "expected_return_pct": g.expected_return_pct,
            "monthly_sip": g.monthly_sip, "starting_amount": g.starting_amount, "created_at": g.created_at.isoformat(), "projection": plan}


def _own(db: Session, user: User, goal_id: int) -> Goal:
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not g:
        raise HTTPException(404, "Goal not found")
    return g


@router.get("/goals")
def list_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    start = _portfolio_value(db, user)
    rows = db.query(Goal).filter(Goal.user_id == user.id).order_by(Goal.id).all()
    return [_goal_out(g, start) for g in rows]


@router.post("/goals", status_code=201)
def create_goal(body: GoalSave, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(Goal).filter(Goal.user_id == user.id).count() >= 20:
        raise HTTPException(409, "You can save up to 20 goals.")
    g = Goal(user_id=user.id, **body.model_dump())
    db.add(g)
    audit(db, user.id, "create_goal", body.name)
    db.commit()
    db.refresh(g)
    return _goal_out(g, _portfolio_value(db, user))


@router.put("/goals/{goal_id}")
def update_goal(goal_id: int, body: GoalSave, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = _own(db, user, goal_id)
    for k, v in body.model_dump().items():
        setattr(g, k, v)
    audit(db, user.id, "update_goal", g.name)
    db.commit()
    return _goal_out(g, _portfolio_value(db, user))


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = _own(db, user, goal_id)
    audit(db, user.id, "delete_goal", g.name)
    db.delete(g)
    db.commit()
