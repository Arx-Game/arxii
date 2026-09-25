"""Deterministic tests for the authenticated Telnet soak harness."""

import argparse

import pytest
from telnet_idle_soak import TelnetEvents, bounded_seconds, config_id, revision


def test_telnet_negotiation_is_counted_without_retaining_payload() -> None:
    events = TelnetEvents()
    replies = events.consume(bytes((255, 253, 1)) + bytes((255, 241)) + b"wire payload")

    assert replies == [bytes((255, 252, 1))]
    assert events.control_frames == 2
    assert events.keepalive_frames == 1
    assert events.application_bytes == len(b"wire payload")
    assert events._pending == b""


def test_split_iac_commands_are_reassembled_across_reads() -> None:
    events = TelnetEvents()
    assert events.consume(b"prompt" + bytes((255,))) == []
    assert events.consume(bytes((253, 1))) == [bytes((255, 252, 1))]
    assert events.application_bytes == len(b"prompt")


def test_split_subnegotiation_end_is_reassembled_across_reads() -> None:
    events = TelnetEvents()
    events.consume(bytes((255, 250, 24)) + b"negotiation" + bytes((255,)))
    events.consume(bytes((240,)))

    assert events.control_frames == 2
    assert events.application_bytes == 0


def test_post_auth_reset_preserves_parser_state_but_clears_counters() -> None:
    events = TelnetEvents()
    events.consume(bytes((255, 250, 24)) + b"login prompt" + bytes((255,)))
    events.reset_counters()
    events.consume(bytes((240, 255, 241)) + b"idle text")

    assert events.control_frames == 2
    assert events.keepalive_frames == 1
    assert events.application_bytes == len(b"idle text")


def test_telnet_subnegotiation_and_escaped_iac_are_not_application_text() -> None:
    events = TelnetEvents()
    events.consume(bytes((255, 250, 24)) + b"negotiation data" + bytes((255, 240)))
    events.consume(bytes((255, 255)) + b"ready")

    assert events.control_frames == 2
    assert events.application_bytes == len(b"ready") + 1


def test_duration_is_hard_bounded() -> None:
    assert bounded_seconds("600") == 600
    with pytest.raises(argparse.ArgumentTypeError):
        bounded_seconds("3601")
    with pytest.raises(argparse.ArgumentTypeError):
        bounded_seconds("0")


def test_config_id_is_stable_and_order_independent() -> None:
    first = config_id({"port": 4003, "tls": True})
    second = config_id({"tls": True, "port": 4003})
    assert first == second
    assert len(first) == 16


def test_revision_uses_explicit_deployment_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVENESS_DEPLOYMENT_REVISION", "remote-sha")
    assert revision() == "remote-sha"
