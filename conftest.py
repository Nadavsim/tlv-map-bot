# Its presence makes pytest add the project root to sys.path so tests can
# `from backend import db`, `from scripts.sync_places import ...`, etc.

import pytest


@pytest.fixture(autouse=True)
def _never_write_usage_stats_to_a_real_database(monkeypatch):
    """Request handlers write anonymous usage counters and unmatched-query
    rows (chat, and the location box). Left unmocked those reach whatever
    MONGODB_URI the developer's .env points at - production, by default.
    Stubbing the collection getters (not the functions) keeps tests of the
    real db functions working: a test that sets its own getter, or its own
    mock of the function, simply overrides this."""
    from unittest.mock import AsyncMock, MagicMock

    from backend import db

    fake_collection = MagicMock()
    fake_collection.update_one = AsyncMock()
    fake_collection.insert_one = AsyncMock()
    monkeypatch.setattr(db, "get_category_stats_collection", lambda: fake_collection)
    monkeypatch.setattr(db, "get_unmatched_queries_collection", lambda: fake_collection)


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
