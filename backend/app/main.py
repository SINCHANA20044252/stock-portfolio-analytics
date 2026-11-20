import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .routers import assistant, auth, data, goals, market, portfolio, settings, transactions

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate_for_production()
    if config.RUN_MIGRATIONS:
        from .migrate import run_migrations
        run_migrations()  # creates / upgrades tables and keeps existing data
    yield


app = FastAPI(
    title="Portfolio Tracker API",
    description="Educational project. Not investment advice.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if config.ENABLE_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if config.ENABLE_DOCS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,  # explicit list, never "*" because cookies are used
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Protection"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path not in ("/docs", "/openapi.json"):
        response.headers.setdefault("Cache-Control", "no-store")  # financial data should not sit in caches
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong on the server."}, status_code=500)


@app.get("/health")
def health():
    return {"status": "ok"}


for r in (auth.router, transactions.router, portfolio.router, market.router, goals.router, data.router, assistant.router, settings.router):
    app.include_router(r)
