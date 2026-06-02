import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from sonarcloud_sync import SC_KEY_MARKER, make_body, make_title, parse_sc_keys


def _raw(  # noqa: PLR0913
    key: str = "AY123",
    rule: str = "python:S3776",
    message: str = "Refactor this function to reduce its Cognitive Complexity.",
    component: str = "Arx-Game_arxii:src/world/magic/services.py",
    line: int = 145,
    severity: str = "CRITICAL",
    impacts: list | None = None,
    issue_type: str = "CODE_SMELL",
) -> dict:
    return {
        "key": key,
        "rule": rule,
        "message": message,
        "component": component,
        "line": line,
        "severity": severity,
        "impacts": impacts
        if impacts is not None
        else [{"softwareQuality": "MAINTAINABILITY", "severity": "HIGH"}],
        "type": issue_type,
    }


def test_make_title_contains_tier_rule_file_line():
    title = make_title(_raw())
    assert "[sonarcloud:high]" in title
    assert "python:S3776" in title
    assert "services.py:145" in title


def test_make_title_blocker_tier():
    title = make_title(_raw(severity="BLOCKER", impacts=[]))
    assert "[sonarcloud:blocker]" in title


def test_make_title_capped_at_120_chars():
    raw = _raw(message="x" * 200, component="Arx-Game_arxii:src/" + "long/" * 20 + "file.py")
    assert len(make_title(raw)) <= 120


def test_make_body_contains_sc_key_marker():
    body = make_body(_raw(key="AY999"))
    assert f"{SC_KEY_MARKER} AY999 -->" in body


def test_make_body_contains_sonarcloud_link_with_key():
    body = make_body(_raw(key="AY999"))
    assert "https://sonarcloud.io/project/issues" in body
    assert "AY999" in body


def test_make_body_shows_file_and_line():
    body = make_body(_raw(component="Arx-Game_arxii:src/flows/engine.py", line=42))
    assert "src/flows/engine.py" in body
    assert "42" in body


def test_make_body_shows_rule():
    body = make_body(_raw(rule="python:S3776"))
    assert "python:S3776" in body


def test_parse_sc_keys_extracts_single_key():
    gh_json = json.dumps([{"body": "<!-- sc: AY123 -->\nsome text"}])
    assert parse_sc_keys(gh_json) == {"AY123"}


def test_parse_sc_keys_extracts_multiple_keys():
    gh_json = json.dumps(
        [
            {"body": "<!-- sc: AY123 -->\n"},
            {"body": "<!-- sc: AY456 -->\n"},
        ]
    )
    assert parse_sc_keys(gh_json) == {"AY123", "AY456"}


def test_parse_sc_keys_ignores_issues_without_marker():
    gh_json = json.dumps([{"body": "Regular issue body, no marker."}])
    assert parse_sc_keys(gh_json) == set()


def test_parse_sc_keys_handles_null_body():
    gh_json = json.dumps([{"body": None}])
    assert parse_sc_keys(gh_json) == set()


def test_parse_sc_keys_empty_list():
    assert parse_sc_keys("[]") == set()
