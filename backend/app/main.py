from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import (
    analytics,
    anomalies,
    assistant,
    auth,
    chat,
    classification,
    connectors,
    cost_saving,
    documents,
    duplicates,
    feedback,
    search,
    users,
)
from app.core.config import settings
from app.core.database import Base, engine
from app.core.rate_limit import limiter

app = FastAPI(
    title=settings.app_name,
    description="AI-powered procurement spend intelligence platform. "
    "Upload documents, classify spend, search semantically, chat with your data, detect anomalies and duplicates.",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-UI-Language"],
)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time-Ms"] = str(round(elapsed * 1000, 1))
    return response


# The Swagger/ReDoc pages load scripts and styles from a CDN, so a strict CSP
# would break them; they are exempt from the CSP header only.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if not request.url.path.startswith(_DOCS_PATHS):
        # A pure JSON API never needs to load or embed anything.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _check_required_config():
    if settings.environment != "production":
        return
    if settings.secret_key == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY is still set to the insecure default. "
            "Set a real SECRET_KEY environment variable before starting in production."
        )
    if "localhost" in settings.database_url or "@postgres:" in settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is still pointing at a local/dev database default. "
            "Set a real DATABASE_URL environment variable before starting in production."
        )
    # Recomputed from settings.cors_origins directly (not the module-level
    # `origins` above, which is fixed at import time) so this check reflects
    # whatever CORS_ORIGINS actually is at startup.
    cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if not cors_origins or all("localhost" in o or "127.0.0.1" in o for o in cors_origins):
        raise RuntimeError(
            "CORS_ORIGINS is still set to the localhost-only default. "
            "Set a real CORS_ORIGINS environment variable (the deployed frontend's "
            "origin) before starting in production."
        )


@app.on_event("startup")
def startup():
    _check_required_config()
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    # Deliberately minimal: this is public (keep-alive pings, load balancer
    # probes), so it doesn't disclose the version or environment.
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(documents.router)
app.include_router(connectors.router)
app.include_router(classification.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(anomalies.router)
app.include_router(duplicates.router)
app.include_router(analytics.router)
app.include_router(feedback.router)
app.include_router(cost_saving.router)
app.include_router(assistant.router)
