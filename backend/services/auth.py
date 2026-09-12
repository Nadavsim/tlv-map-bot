import os
import time

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")

# Short enough that a stolen access token (held only in browser memory, never
# persisted) is worth little; long enough that the app isn't refreshing on
# every request. Nothing in this app calls a protected endpoint yet, so this
# lifetime doesn't matter functionally today - it matters once favorites/
# ratings land and start requiring it.
ACCESS_TOKEN_TTL_SECONDS = 15 * 60
# Long-lived on purpose - this is what actually keeps someone "signed in"
# across visits. Held only in an httpOnly/Secure/SameSite=Strict cookie,
# never readable by page JS.
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60

# A single reused Request() instance per Google's own recommendation - it
# caches Google's public signing keys instead of refetching them on every
# verification call.
_google_request = google_requests.Request()


def verify_google_id_token(credential: str) -> dict | None:
    """Verifies a Google ID token's signature, expiry, and audience (must
    match our own Client ID - without this check, a token issued for a
    completely different Google app would also pass). Returns the token's
    claims (sub/email/name/picture) on success, None on any failure -
    callers don't need to know or care *why* a token was rejected."""
    try:
        return id_token.verify_oauth2_token(credential, _google_request, GOOGLE_CLIENT_ID)
    except ValueError:
        return None


def create_access_token(user_id: str) -> str:
    payload = {"sub": user_id, "type": "access", "exp": int(time.time()) + ACCESS_TOKEN_TTL_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def create_refresh_token(user_id: str, token_version: int) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "ver": token_version,
        "exp": int(time.time()) + REFRESH_TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> str | None:
    """Returns the user id, or None if the token is missing, expired,
    malformed, or not actually an access token (the "type" check stops a
    refresh token - which a client should never expose to page JS anyway -
    from also working as an access token if one leaked)."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "access":
        return None
    return payload["sub"]


def decode_refresh_token(token: str) -> tuple[str, int] | None:
    """Returns (user_id, token_version), or None. token_version still has to
    be checked by the caller against the user's current stored value -
    decoding successfully only proves the token is well-formed and
    unexpired, not that it hasn't been revoked by a sign-out since."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "refresh":
        return None
    return payload["sub"], payload["ver"]
