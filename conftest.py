# Its presence makes pytest add the project root to sys.path so tests can
# `from backend import db`, `from scripts.sync_places import ...`, etc.

import pytest


@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """FastAPI's TestClient sends every request from the same fake
    "testclient" host, so without this the rate limiter's in-memory bucket
    accumulates across the whole pytest session (not per-test) - fine today
    with a handful of /api/chat tests, but a flaky-test time bomb as the
    suite grows toward the 20/minute limit."""
    from backend.app import limiter

    limiter.enabled = False
    yield
    limiter.enabled = True
