"""A one-off diagnostic: which address does the per-IP rate limit actually see?

The limiter keys on the connection's peer address. Behind Azure's front end
that may be the visitor, or a shared proxy address - in which case every
visitor shares one bucket. Nothing in the repo can say which, so the app logs
what the *kind* of address is.

It never logs an address, only a class (public / private / loopback / ...) and
whether an X-Forwarded-For header is present, once per distinct combination -
a handful of lines for the whole life of the process. The privacy policy says
the requesting address is held only briefly in memory to count requests; this
keeps that true.
"""

import ipaddress
import logging

logger = logging.getLogger(__name__)

_MAX_SHAPES = 20
_seen: set[tuple[str, str, str]] = set()


def classify(value: str | None) -> str:
    """The kind of address, never the address itself."""
    if not value or not value.strip():
        return "none"
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return "invalid"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_private:
        return "private"
    if ip.is_global:
        return "public"
    return "other"


def observe(peer: str | None, forwarded_for: str | None) -> None:
    """Logs the shape of this request's address information the first time that
    shape is seen. Safe to call on every request: it does nothing after the
    first of each kind, and never raises."""
    try:
        has_forwarded = bool(forwarded_for and forwarded_for.strip())
        first_hop = forwarded_for.split(",")[0] if has_forwarded else None
        shape = (
            classify(peer),
            "present" if has_forwarded else "absent",
            classify(first_hop) if has_forwarded else "-",
        )
        if shape in _seen or len(_seen) >= _MAX_SHAPES:
            return
        _seen.add(shape)
        peer_kind, header, forwarded_kind = shape
        if peer_kind == "public":
            verdict = "the rate limit sees a public address (probably the visitor)"
        elif header == "present" and forwarded_kind == "public":
            verdict = "the rate limit sees a non-public peer while the real client is in X-Forwarded-For: all visitors may share one bucket"
        else:
            verdict = "the rate limit sees a non-public peer: all visitors may share one bucket"
        logger.info("client-ip shape: peer=%s x-forwarded-for=%s first-hop=%s -> %s", peer_kind, header, forwarded_kind, verdict)
    except Exception:  # a diagnostic must never be able to break a request
        logger.debug("client-ip diagnostic failed", exc_info=True)
