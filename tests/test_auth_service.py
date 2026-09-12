import time

import jwt
import pytest

from backend.services import auth


@pytest.fixture(autouse=True)
def _fixed_jwt_secret(monkeypatch):
    monkeypatch.setattr(auth, "JWT_SECRET", "test-secret")


def test_access_token_round_trips_to_the_same_user_id():
    token = auth.create_access_token("user123")
    assert auth.decode_access_token(token) == "user123"


def test_refresh_token_round_trips_id_and_version():
    token = auth.create_refresh_token("user123", token_version=2)
    assert auth.decode_refresh_token(token) == ("user123", 2)


def test_decode_access_token_rejects_expired_token():
    payload = {"sub": "user123", "type": "access", "exp": int(time.time()) - 10}
    expired = jwt.encode(payload, "test-secret", algorithm="HS256")
    assert auth.decode_access_token(expired) is None


def test_decode_access_token_rejects_garbage():
    assert auth.decode_access_token("not-a-real-token") is None


def test_decode_access_token_rejects_wrong_secret():
    token = jwt.encode({"sub": "user123", "type": "access", "exp": int(time.time()) + 60}, "a-different-secret", algorithm="HS256")
    assert auth.decode_access_token(token) is None


def test_decode_access_token_rejects_a_refresh_token():
    # A refresh token should never also work as an access token, even though
    # both are signed with the same secret - the "type" claim is what
    # prevents a leaked refresh token (which shouldn't reach page JS at all)
    # from doubling as an access token.
    refresh = auth.create_refresh_token("user123", token_version=0)
    assert auth.decode_access_token(refresh) is None


def test_decode_refresh_token_rejects_an_access_token():
    access = auth.create_access_token("user123")
    assert auth.decode_refresh_token(access) is None


def test_verify_google_id_token_returns_none_on_invalid_token(monkeypatch):
    def fake_verify(*args, **kwargs):
        raise ValueError("Token used too late")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    assert auth.verify_google_id_token("bogus") is None


def test_verify_google_id_token_returns_claims_on_success(monkeypatch):
    claims = {"sub": "g-123", "email": "a@example.com", "name": "A", "picture": "https://example.com/p.jpg"}
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda *a, **k: claims)
    assert auth.verify_google_id_token("real-looking-token") == claims
