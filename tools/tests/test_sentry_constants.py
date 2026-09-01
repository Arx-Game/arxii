from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

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
