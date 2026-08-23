from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.rate_limit import limiter


def test_login_is_rate_limited_per_ip(client: TestClient):
    """conftest.py disables the limiter for every other test (it would
    otherwise trip on the test suite's own repeated /auth/login calls) -
    re-enable it here just for this test to confirm it actually engages.
    """
    limiter.enabled = True
    try:
        last_status = None
        for _ in range(6):
            r = client.post("/auth/login", json={"email": "test@spend.com", "password": "wrong"})
            last_status = r.status_code
        assert last_status == 429
    finally:
        limiter.enabled = False
