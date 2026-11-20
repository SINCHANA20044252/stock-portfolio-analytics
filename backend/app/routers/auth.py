from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .. import ratelimit, security
from ..database import get_db
from ..models import User, UserPreference
from ..schemas import ChangePassword, Credentials, ProfileUpdate
from .common import audit

router = APIRouter(prefix="/auth", tags=["auth"])
_DUMMY_HASH: str | None = None


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "created_at": u.created_at.isoformat()}


def _start_session(db: Session, user: User, response: Response) -> dict:
    access = security.create_access_token(user.id)
    refresh = security.issue_refresh_token(db, user.id)
    db.commit()
    security.set_session_cookies(response, access, refresh)
    # The browser app ignores access_token (it uses the httpOnly cookie). It is returned for API tools / Swagger.
    return {"user": user_out(user), "access_token": access, "token_type": "bearer"}


@router.post("/register", status_code=201, dependencies=[Depends(ratelimit.limit_auth)])
def register(body: Credentials, response: Response, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=body.email, password_hash=security.hash_password(body.password))
    db.add(user)
    db.flush()
    db.add(UserPreference(user_id=user.id))
    audit(db, user.id, "register", "account created")
    return _start_session(db, user, response)


@router.post("/login", dependencies=[Depends(ratelimit.limit_auth)])
def login(body: Credentials, response: Response, db: Session = Depends(get_db)):
    global _DUMMY_HASH
    if ratelimit.LOGIN_FAILS.blocked(body.email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed logins for this account. Try again in 15 minutes.")
    user = db.query(User).filter(User.email == body.email).first()
    if user is None:  # spend the same time as a real check so response time does not reveal which emails exist
        _DUMMY_HASH = _DUMMY_HASH or security.hash_password("dummy-password")
        security.verify_password(body.password, _DUMMY_HASH)
        ok = False
    else:
        ok = security.verify_password(body.password, user.password_hash)
    if not ok:
        ratelimit.LOGIN_FAILS.add(body.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    ratelimit.LOGIN_FAILS.hits.pop(body.email, None)
    if security.needs_rehash(user.password_hash):  # silently upgrade old hashes
        user.password_hash = security.hash_password(body.password)
    audit(db, user.id, "login", "successful login")
    return _start_session(db, user, response)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    security.require_csrf_header(request)
    token = request.cookies.get(security.REFRESH_COOKIE)
    result = security.rotate_refresh_token(db, token) if token else None
    if result is None:
        security.clear_session_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please log in again.")
    user, new_refresh = result
    access = security.create_access_token(user.id)
    db.commit()
    security.set_session_cookies(response, access, new_refresh)
    return {"user": user_out(user), "access_token": access, "token_type": "bearer"}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(security.REFRESH_COOKIE)
    if token:
        security.revoke_refresh_token(db, token)
        db.commit()
    security.clear_session_cookies(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(security.get_current_user)):
    return user_out(user)


@router.put("/me")
def update_me(body: ProfileUpdate, user: User = Depends(security.get_current_user), db: Session = Depends(get_db)):
    user.display_name = body.display_name
    audit(db, user.id, "update_profile", "display name changed")
    db.commit()
    return user_out(user)


@router.post("/change-password", dependencies=[Depends(ratelimit.limit_auth)])
def change_password(body: ChangePassword, response: Response, user: User = Depends(security.get_current_user), db: Session = Depends(get_db)):
    if not security.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
    user.password_hash = security.hash_password(body.new_password)
    security.revoke_all_refresh_tokens(db, user.id)  # signs out every other device
    audit(db, user.id, "change_password", "password changed")
    return _start_session(db, user, response)
