"""The protocol-key linter rejects the dead ``webclient/...`` spellings (#4418)."""

from lint_webclient_protocol_key import check_source


def test_dead_websocket_key_fails():
    assert len(check_source('session.protocol_key = "webclient/websocket"\n')) == 1


def test_dead_ajax_key_fails():
    assert len(check_source('keys = ["webclient/ajax"]\n')) == 1


def test_real_keys_pass():
    assert check_source('keys = {"websocket", "ajax/comet"}\n') == []


def test_docstring_and_comment_pass():
    source = '"""Never "webclient/websocket"."""\n# "webclient/websocket" is dead\n'
    assert check_source(source) == []


def test_suppression_passes():
    source = 'key = "webclient/websocket"  # noqa: WEBCLIENT_KEY proves a dead key is rejected\n'
    assert check_source(source) == []
