"""Passwords, tokens, cookies and the current-user dependency.

Sessions: a short-lived (30 min) access JWT and a rotating refresh token, both in httpOnly cookies, so
JavaScript (and therefore XSS) can never read them. Cookie path is "/" because the app reaches the API
through a "/api" proxy prefix, so a "/auth" path would never match the browser's request URL. Cookie-authenticated state-changing requests must
also send the header `X-CSRF-Protection: 1` (browsers will not add it cross-site without a CORS
preflight), on top of SameSite=Lax. API clients can still send `Authorization: Bearer <token>`.
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import RefreshToken, User

ALGORITHM = "HS256"
ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_HEADER = "x-csrf-protection"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PASSWORD_SCHEME = "pbkdf2_sha256"

bearer = HTTPBearer(auto_error=False)


# ---------- passwords ----------
def _pbkdf2(password: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations).hex()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    n = config.PBKDF2_ITERATIONS
    return f"{PASSWORD_SCHEME}${n}${salt.hex()}${_pbkdf2(password, salt, n)}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    try:
        if len(parts) == 4 and parts[0] == PASSWORD_SCHEME:
            _, n, salt_hex, digest = parts
            iterations = int(n)
        elif len(parts) == 2:  # legacy format from the first version: salt$hash at 200,000 iterations
            salt_hex, digest = parts
            iterations = 200_000
        else:
            return False
        return hmac.compare_digest(_pbkdf2(password, bytes.fromhex(salt_hex), iterations), digest)
    except ValueError:
        return False


def needs_rehash(stored: str) -> bool:
    parts = stored.split("$")
    return not (len(parts) == 4 and parts[0] == PASSWORD_SCHEME and int(parts[1]) >= config.PBKDF2_ITERATIONS)


# ---------- tokens ----------
def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": "access", "iat": now, "jti": uuid.uuid4().hex,
               "exp": now + timedelta(minutes=config.ACCESS_TOKEN_MINUTES)}
    return jwt.encode(payload, config.SECRET_KEY, algorithm=ALGORITHM)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh_token(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    db.add(RefreshToken(user_id=user_id, token_hash=_hash_token(token),
                        expires_at=datetime.now(timezone.utc) + timedelta(days=config.REFRESH_TOKEN_DAYS)))
    return token


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite returns naive datetimes


def rotate_refresh_token(db: Session, token: str) -> tuple[User, str] | None:
    """Validate and replace a refresh token. Re-using an already-used token revokes the whole family."""
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == _hash_token(token)).first()
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    if row.revoked_at is not None:
        revoke_all_refresh_tokens(db, row.user_id)  # possible theft: sign every session out
        db.commit()
        return None
    if _aware(row.expires_at) < now:
        return None
    user = db.get(User, row.user_id)
    if user is None:
        return None
    row.revoked_at = now
    return user, issue_refresh_token(db, user.id)


def revoke_refresh_token(db: Session, token: str) -> None:
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == _hash_token(token)).first()
    if row and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)


def revoke_all_refresh_tokens(db: Session, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    for row in db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)).all():
        row.revoked_at = now


# ---------- cookies ----------
def set_session_cookies(response: Response, access: str, refresh: str) -> None:
    common = dict(httponly=True, secure=config.COOKIE_SECURE, samesite=config.COOKIE_SAMESITE, domain=config.COOKIE_DOMAIN)
    response.set_cookie(ACCESS_COOKIE, access, max_age=config.ACCESS_TOKEN_MINUTES * 60, path="/", **common)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=config.REFRESH_TOKEN_DAYS * 86400, path="/", **common)


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/", domain=config.COOKIE_DOMAIN)
    response.delete_cookie(REFRESH_COOKIE, path="/", domain=config.COOKIE_DOMAIN)


def require_csrf_header(request: Request) -> None:
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing CSRF protection header.")


# ---------- current user ----------
def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing token")
    if creds is not None:
        token = creds.credentials
    else:
        token = request.cookies.get(ACCESS_COOKIE)
        if token:
            require_csrf_header(request)  # cookie auth only: bearer tokens are not sent automatically by browsers
    if not token:
        raise unauthorized
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        if payload.get("type") != "access":
            raise unauthorized
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    if user is None:
        raise unauthorized
    return user
