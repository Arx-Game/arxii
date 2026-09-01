from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import sentry_constants


def test_unresolved_query_uses_an_absolute_range_not_statsperiod(monkeypatch):
    """statsPeriod filters on last-seen and caps at 90d, so it silently drops stale
    unresolved issues - observed 2026-09-01 reporting 1 open when 6 were."""
    captured = {}

    def _fake(path, *, params=None, **_kwargs):
        captured.update(path=path, params=params)
        return []

    monkeypatch.setattr(sentry_constants, "api_request", _fake)
    sentry_constants.fetch_unresolved_issues()

    assert "statsPeriod" not in captured["params"]
    assert captured["params"]["start"] == sentry_constants.EPOCH_START
    assert captured["params"]["query"] == "is:unresolved"


def test_warns_when_the_page_limit_is_hit(monkeypatch, capsys):
    monkeypatch.setattr(sentry_constants, "api_request", lambda *_a, **_k: [{}] * 5)
    sentry_constants.fetch_unresolved_issues(limit=5)
    assert "may be incomplete" in capsys.readouterr().err


def test_no_warning_below_the_page_limit(monkeypatch, capsys):
    monkeypatch.setattr(sentry_constants, "api_request", lambda *_a, **_k: [{}] * 4)
    sentry_constants.fetch_unresolved_issues(limit=5)
    assert capsys.readouterr().err == ""


def test_numeric_issue_id_passes_through_digits(monkeypatch):
    called = []
    monkeypatch.setattr(sentry_constants, "api_request", lambda *a, **_k: called.append(a))
    assert sentry_constants.numeric_issue_id(" 7690351599 ") == "7690351599"
    assert not called, "must not call the API for an already-numeric id"


def test_numeric_issue_id_translates_a_short_id(monkeypatch):
    """The bulk endpoint rejects short ids with "not a valid integer id" (seen live)."""
    monkeypatch.setattr(sentry_constants, "api_request", lambda *_a, **_k: {"groupId": "769"})
    assert sentry_constants.numeric_issue_id("ARX2-6") == "769"


def test_numeric_issue_id_raises_on_unknown_short_id(monkeypatch):
    monkeypatch.setattr(sentry_constants, "api_request", lambda *_a, **_k: None)
    with pytest.raises(sentry_constants.SentryAPIError, match="No Sentry issue found"):
        sentry_constants.numeric_issue_id("ARX2-999")
