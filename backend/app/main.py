from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    analytics,
    anomalies,
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

app = FastAPI(
    title=settings.app_name,
    description="AI-powered procurement spend intelligence platform. "
    "Upload documents, classify spend, search semantically, chat with your data, detect anomalies and duplicates.",
    version="1.0.0",
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time-Ms"] = str(round(elapsed * 1000, 1))
    return response


def _check_secret_key():
    if settings.environment == "production" and settings.secret_key == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY is still set to the insecure default. "
            "Set a real SECRET_KEY environment variable before starting in production."
        )


@app.on_event("startup")
def startup():
    _check_secret_key()
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
