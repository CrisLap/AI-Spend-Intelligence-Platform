"""Pytest conftest: SQLite file-based for all tests."""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import User

# Speed up tests by reducing Ollama timeout (no server in CI/local)
settings.ollama_timeout = 1

_db_path = os.path.join(tempfile.gettempdir(), "spendintel_test.db")
if os.path.exists(_db_path):
    os.remove(_db_path)
engine = create_engine(f"sqlite:///{_db_path}", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
TestSessionLocal = sessionmaker(bind=engine)

_seed = TestSessionLocal()
if not _seed.query(User).filter(User.email == "test@spend.com").first():
    _seed.add(User(
        email="test@spend.com", hashed_password=hash_password("test123"),
        full_name="Test User", role="admin",
    ))
    _seed.commit()
_seed.close()


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db() -> Session:
    s = TestSessionLocal()
    yield s
    s.close()


@pytest.fixture
def token(client: TestClient) -> str:
    r = client.post("/auth/login", json={"email": "test@spend.com", "password": "test123"})
    return r.json()["access_token"]


@pytest.fixture
def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
