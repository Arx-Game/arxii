from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from sentry_digest import DIGEST_MARKER, find_open_digest, make_body, make_title


def _issue(
    issue_id: str = "7690351599",
    short_id: str = "ARXII-1A",
    level: str = "error",
    count: str = "41",
    user_count: int = 3,
) -> dict:
    return {
        "id": issue_id,
        "shortId": short_id,
        "level": level,
        "count": count,
        "userCount": user_count,
        "firstSeen": "2026-08-28T11:02:13.000000Z",
        "lastSeen": "2026-09-01T04:19:55.000000Z",
        # Fields the digest must never surface into a public issue:
        "title": "TypeError: 'NoneType' object is not subscriptable",
        "culprit": "world.room_features.vault_services in deposit",
        "metadata": {"value": "'NoneType' object is not subscriptable"},
    }


def test_title_counts_issues():
    assert "2 unresolved issues" in make_title([_issue(), _issue(issue_id="2")])


def test_title_singular_for_one():
    assert "1 unresolved issue in" in make_title([_issue()])


def test_body_links_each_issue_by_short_id():
    body = make_body([_issue()])
    assert DIGEST_MARKER in body
    assert "[ARXII-1A](https://sentry.io/organizations/arx2/issues/7690351599/)" in body


def test_body_carries_counts_and_dates():
    body = make_body([_issue()])
    assert "| error | 41 | 3 | 2026-08-28 | 2026-09-01 |" in body


def test_body_never_leaks_message_or_culprit():
    """Public repo: the digest is a pointer, never a reproduction (see module docstring)."""
    body = make_body([_issue()])
    for leaked in ("TypeError", "NoneType", "vault_services", "subscriptable", "deposit"):
        assert leaked not in body


def test_body_falls_back_to_numeric_id_without_short_id():
    raw = _issue()
    del raw["shortId"]
    assert "[7690351599](" in make_body([raw])


def _stub_gh(payload: str):
    def _run(*_args, **_kwargs) -> str:
        return payload

    return _run


def test_find_open_digest_matches_marker(monkeypatch):
    payload = (
        '[{"number": 11, "body": "unrelated"}, '
        f'{{"number": 42, "body": "{DIGEST_MARKER}\\nrows"}}]'
    )
    monkeypatch.setattr("sentry_digest._gh", _stub_gh(payload))
    assert find_open_digest() == 42


def test_find_open_digest_none_when_no_marker(monkeypatch):
    monkeypatch.setattr("sentry_digest._gh", _stub_gh('[{"number": 11, "body": "other"}]'))
    assert find_open_digest() is None
