"""The msg-frame linter rejects ``.msg(type=...)`` and ``.msg(kwargs=...)`` (#4774)."""

from lint_msg_frame_keywords import check_source


def test_the_shipped_bug_fails_on_both_keywords():
    source = 'session.msg(type="action_result", kwargs={"success": True})\n'
    assert [hit[2] for hit in check_source(source)] == ["type", "kwargs"]


def test_named_frame_passes():
    assert check_source('session.msg(action_result=((), {"success": True}))\n') == []


def test_dict_splat_frame_passes():
    assert check_source("obj.msg(**{NAME: ((), payload)})\n") == []


def test_other_calls_named_type_pass():
    assert check_source('Thing.objects.filter(type="x")\nsend(kwargs={})\n') == []


def test_suppression_passes():
    source = 'session.msg(type="x")  # noqa: MSG_FRAME a test fake proves the refusal\n'
    assert check_source(source) == []
