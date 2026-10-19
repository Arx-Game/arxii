"""The msg-beside-push linter flags an untargeted ``.msg`` next to a structured push (#4418)."""

from lint_msg_beside_push import check_source


def test_bare_msg_beside_push_fails():
    source = """
def f(c, payload):
    _send_to_objects([c], payload)
    c.msg("text")
"""
    assert len(check_source(source)) == 1


def test_msg_with_session_passes():
    source = """
def f(c, payload):
    _send_to_objects([c], payload)
    c.msg("text", session=non_web_sessions(c))
"""
    assert check_source(source) == []


def test_msg_without_a_push_passes():
    assert check_source("def f(c):\n    c.msg('text')\n") == []


def test_send_text_to_non_web_passes():
    source = """
def f(c, payload):
    _send_to_objects([c], payload)
    send_text_to_non_web(c, "text")
"""
    assert check_source(source) == []


def test_suppression_passes():
    source = """
def f(c, payload):
    _send_to_objects([c], payload)
    c.msg("text")  # noqa: MSG_BESIDE_PUSH no row was pushed on this branch
"""
    assert check_source(source) == []
