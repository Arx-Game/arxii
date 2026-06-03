from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from sonarcloud_triage import matches_path, matches_rule


def _raw(
    rule: str = "python:S2068",
    component: str = "Arx-Game_arxii:src/world/roster/tests/test_auth.py",
) -> dict:
    return {"rule": rule, "component": component}


def test_matches_rule_exact_match():
    assert matches_rule(_raw(rule="python:S2068"), "python:S2068")


def test_matches_rule_no_match():
    assert not matches_rule(_raw(rule="python:S3776"), "python:S2068")


def test_matches_rule_none_matches_all():
    assert matches_rule(_raw(), None)


def test_matches_path_glob_tests_dir():
    raw = _raw(component="Arx-Game_arxii:src/world/roster/tests/test_auth.py")
    assert matches_path(raw, "*/tests/*")


def test_matches_path_glob_no_match():
    raw = _raw(component="Arx-Game_arxii:src/world/roster/services.py")
    assert not matches_path(raw, "*/tests/*")


def test_matches_path_none_matches_all():
    assert matches_path(_raw(), None)


def test_matches_path_empty_string_matches_all():
    assert matches_path(_raw(), "")
