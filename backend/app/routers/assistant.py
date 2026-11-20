from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import assistant as ai
from .. import ratelimit
from ..database import get_db
from ..models import User
from ..schemas import Question
from ..security import get_current_user
from ..services import portfolio

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask")
def ask(body: Question, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ratelimit.limit_user(user.id, "ask")
    # The context is built from the signed-in user's rows only; the assistant itself has no database access.
    ctx = portfolio.assistant_context(db, user.id)
    return ai.answer(body.question, ctx)
