"""All configuration comes from environment variables (see .env.example). Nothing secret is hard-coded."""
import logging
import os

log = logging.getLogger("config")

DEV_SECRET = "dev-only-secret-do-not-use-in-production-0000"


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


ENV = os.getenv("ENV", "development").lower()
IS_PROD = ENV == "production"

SECRET_KEY = os.getenv("SECRET_KEY") or DEV_SECRET
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
PBKDF2_ITERATIONS = int(os.getenv("PBKDF2_ITERATIONS", "600000"))

# Cookies: httpOnly always. Secure + SameSite=Lax in production. The frontend and API must share a site
# (Vercel rewrite / nginx proxy to /api) so the cookie is first-party. See README "Deployment".
COOKIE_SECURE = _bool("COOKIE_SECURE", IS_PROD)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
TRUST_PROXY = _bool("TRUST_PROXY", False)  # honour X-Forwarded-For for rate limiting (set true behind Render/nginx)
ENABLE_DOCS = _bool("ENABLE_DOCS", not IS_PROD)
RUN_MIGRATIONS = _bool("RUN_MIGRATIONS", True)

BENCHMARK_SYMBOL = os.getenv("BENCHMARK_SYMBOL", "^NSEI")
RISK_FREE_RATE_PCT = float(os.getenv("RISK_FREE_RATE_PCT", "7.0"))
REFRESH_MIN_INTERVAL_SECONDS = int(os.getenv("REFRESH_MIN_INTERVAL_SECONDS", "30"))


def validate_for_production() -> None:
    """Fail fast instead of running a production server with development defaults."""
    if not IS_PROD:
        if SECRET_KEY == DEV_SECRET:
            log.warning("Using the development SECRET_KEY. Set SECRET_KEY before deploying.")
        return
    problems = []
    if SECRET_KEY == DEV_SECRET or len(SECRET_KEY) < 32:
        problems.append("SECRET_KEY must be set to a random value of at least 32 characters")
    if not os.getenv("DATABASE_URL"):
        problems.append("DATABASE_URL must be set (PostgreSQL recommended)")
    if not os.getenv("CORS_ORIGINS"):
        problems.append("CORS_ORIGINS must list your frontend origin(s)")
    if not COOKIE_SECURE:
        problems.append("COOKIE_SECURE must be true in production")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
