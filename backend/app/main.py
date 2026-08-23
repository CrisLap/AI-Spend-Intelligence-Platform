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


@app.on_event("startup")
def startup():
    _check_required_config()
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "version": "1.0.0", "environment": settings.environment}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(documents.router)
app.include_router(classification.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(anomalies.router)
app.include_router(duplicates.router)
app.include_router(analytics.router)
app.include_router(feedback.router)
app.include_router(cost_saving.router)
app.include_router(assistant.router)
