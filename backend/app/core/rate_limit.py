from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Keyed by client IP (not by user id): the auth endpoints this also
# protects run before a user is authenticated, so IP is the only key
# available everywhere it's needed.
#
# In-memory storage: acceptable for this app's current single-instance
# deployment (Render free tier runs one instance, per README). If this
# ever runs multi-instance, pass a Redis-backed `storage_uri=` here so
# limits are shared across processes instead of reset per-instance.
limiter = Limiter(key_func=get_remote_address)
