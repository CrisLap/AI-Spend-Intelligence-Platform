from __future__ import annotations

import pytest

from app.core.config import settings
from app.main import _check_required_config


def test_startup_rejects_default_secret_key_in_production():
    original_env, original_key = settings.environment, settings.secret_key
    settings.environment = "production"
    settings.secret_key = "change-me-in-production"
    try:
        with pytest.raises(RuntimeError):
            _check_required_config()
    finally:
        settings.environment, settings.secret_key = original_env, original_key


def test_startup_rejects_default_database_url_in_production():
    original_env, original_key, original_db = settings.environment, settings.secret_key, settings.database_url
    settings.environment = "production"
    settings.secret_key = "a-real-random-secret"
    settings.database_url = "postgresql://spenduser:spendpass@localhost:5432/spendintel"
    try:
        with pytest.raises(RuntimeError):
            _check_required_config()
    finally:
        settings.environment, settings.secret_key, settings.database_url = original_env, original_key, original_db


def test_startup_allows_custom_config_in_production():
    original_env, original_key, original_db, original_cors = (
        settings.environment, settings.secret_key, settings.database_url, settings.cors_origins,
    )
    settings.environment = "production"
    settings.secret_key = "a-real-random-secret"
    settings.database_url = "postgresql://user:pass@neon.example.com:5432/spendintel"
    settings.cors_origins = "https://app.example.com"
    try:
        _check_required_config()  # should not raise
    finally:
        settings.environment, settings.secret_key, settings.database_url, settings.cors_origins = (
            original_env, original_key, original_db, original_cors,
        )


def test_startup_rejects_default_cors_origins_in_production():
    original_env, original_key, original_db, original_cors = (
        settings.environment, settings.secret_key, settings.database_url, settings.cors_origins,
    )
    settings.environment = "production"
    settings.secret_key = "a-real-random-secret"
    settings.database_url = "postgresql://user:pass@neon.example.com:5432/spendintel"
    settings.cors_origins = "http://localhost:5173,http://localhost:3000"
    try:
        with pytest.raises(RuntimeError):
            _check_required_config()
    finally:
        settings.environment, settings.secret_key, settings.database_url, settings.cors_origins = (
            original_env, original_key, original_db, original_cors,
        )


def test_startup_rejects_empty_cors_origins_in_production():
    original_env, original_key, original_db, original_cors = (
        settings.environment, settings.secret_key, settings.database_url, settings.cors_origins,
    )
    settings.environment = "production"
    settings.secret_key = "a-real-random-secret"
    settings.database_url = "postgresql://user:pass@neon.example.com:5432/spendintel"
    settings.cors_origins = ""
    try:
        with pytest.raises(RuntimeError):
            _check_required_config()
    finally:
        settings.environment, settings.secret_key, settings.database_url, settings.cors_origins = (
            original_env, original_key, original_db, original_cors,
        )


def test_startup_skips_checks_outside_production():
    original_env, original_key = settings.environment, settings.secret_key
    settings.environment = "development"
    settings.secret_key = "change-me-in-production"
    try:
        _check_required_config()  # should not raise outside production
    finally:
        settings.environment, settings.secret_key = original_env, original_key
