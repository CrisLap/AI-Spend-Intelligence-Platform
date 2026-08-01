from __future__ import annotations

import pytest

from app.core.config import settings
from app.main import _check_secret_key


def test_startup_rejects_default_secret_key_in_production():
    original_env, original_key = settings.environment, settings.secret_key
    settings.environment = "production"
    settings.secret_key = "change-me-in-production"
    try:
        with pytest.raises(RuntimeError):
            _check_secret_key()
    finally:
        settings.environment, settings.secret_key = original_env, original_key


def test_startup_allows_custom_secret_key_in_production():
    original_env, original_key = settings.environment, settings.secret_key
    settings.environment = "production"
    settings.secret_key = "a-real-random-secret"
    try:
        _check_secret_key()  # should not raise
    finally:
        settings.environment, settings.secret_key = original_env, original_key
