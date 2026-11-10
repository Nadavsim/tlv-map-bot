import logging

import pytest

from backend.services import clientip


@pytest.fixture(autouse=True)
def _reset_seen():
    clientip._seen.clear()
    yield
    clientip._seen.clear()


@pytest.mark.parametrize(
    "value,expected",
    [
        ("8.8.8.8", "public"),
        ("2001:4860:4860::8888", "public"),
        ("10.0.0.4", "private"),
        ("192.168.1.20", "private"),
        ("172.16.5.5", "private"),
        ("127.0.0.1", "loopback"),
        ("::1", "loopback"),
        ("169.254.129.1", "link-local"),
        (" 8.8.8.8 ", "public"),
        ("testclient", "invalid"),
        ("", "none"),
        (None, "none"),
    ],
)
def test_classify_returns_only_the_kind_of_address(value, expected):
    assert clientip.classify(value) == expected


def test_each_shape_is_logged_once(caplog):
    with caplog.at_level(logging.INFO, logger=clientip.logger.name):
        for _ in range(5):
            clientip.observe("169.254.129.1", None)
        clientip.observe("8.8.8.8", None)
        clientip.observe("8.8.8.8", None)

    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 2
    assert "peer=link-local" in lines[0]
    assert "peer=public" in lines[1]


def test_a_non_public_peer_is_reported_as_a_possible_shared_bucket(caplog):
    with caplog.at_level(logging.INFO, logger=clientip.logger.name):
        clientip.observe("10.0.0.4", "8.8.4.4, 10.0.0.4")

    text = caplog.text
    assert "peer=private" in text
    assert "x-forwarded-for=present" in text
    assert "first-hop=public" in text
    assert "share one bucket" in text


def test_a_public_peer_is_reported_as_the_visitor(caplog):
    with caplog.at_level(logging.INFO, logger=clientip.logger.name):
        clientip.observe("8.8.4.4", None)

    assert "probably the visitor" in caplog.text


def test_no_address_is_ever_logged(caplog):
    with caplog.at_level(logging.DEBUG, logger=clientip.logger.name):
        clientip.observe("8.8.4.4", "1.1.1.1, 10.1.2.3")
        clientip.observe("10.9.8.7", "1.1.1.2")

    for fragment in ("8.8.4", "1.1.1", "10.1.2", "10.9.8"):
        assert fragment not in caplog.text


def test_the_number_of_logged_shapes_is_capped(caplog):
    with caplog.at_level(logging.INFO, logger=clientip.logger.name):
        kinds = ["8.8.8.8", "10.0.0.1", "127.0.0.1", "169.254.1.1", "bad", ""]
        for peer in kinds:
            for header in (None, "8.8.8.8", "10.0.0.1", "bad"):
                clientip.observe(peer, header)

    assert len(caplog.records) <= clientip._MAX_SHAPES


def test_a_failure_inside_the_diagnostic_never_propagates(monkeypatch):
    monkeypatch.setattr(clientip, "classify", lambda value: (_ for _ in ()).throw(RuntimeError("boom")))

    clientip.observe("8.8.8.8", None)  # must not raise


# --- rate_limit_key: who the per-IP limits count as one visitor ------------------


def test_a_public_peer_is_the_key_and_the_header_cannot_override_it():
    assert clientip.rate_limit_key("93.184.216.34", "8.8.8.8") == "93.184.216.34"


def test_behind_a_private_proxy_the_forwarded_client_is_the_key():
    assert clientip.rate_limit_key("169.254.130.1", "93.184.216.34:51234") == "93.184.216.34"


def test_the_rightmost_public_entry_wins_so_a_spoofed_left_entry_is_ignored():
    # The client claims 1.1.1.1; the proxy appended the address it really saw.
    assert clientip.rate_limit_key("10.0.0.5", "1.1.1.1, 93.184.216.34:443") == "93.184.216.34"


def test_private_entries_are_skipped_while_looking_for_a_public_one():
    assert clientip.rate_limit_key("10.0.0.5", "93.184.216.34, 10.1.1.1") == "93.184.216.34"


def test_ipv6_with_a_port_is_unwrapped():
    assert clientip.rate_limit_key("10.0.0.5", "[2606:4700:4700::1111]:443") == "2606:4700:4700::1111"


def test_with_nothing_usable_it_falls_back_to_the_peer():
    assert clientip.rate_limit_key("10.0.0.5", "garbage, 192.168.1.1") == "10.0.0.5"
    assert clientip.rate_limit_key(None, None) == "unknown"
