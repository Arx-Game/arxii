"""The rule-policy file is only useful if every entry carries its reason."""

from pathlib import Path
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from sonar_profile import RULES_FILE, SonarError, load_policy


def test_shipped_policy_parses_and_every_disabled_rule_explains_itself() -> None:
    policy = load_policy()
    assert policy["organization"] == "arx-game"
    assert policy["project"] == "Arx-Game_arxii"
    assert policy["disabled"], "policy disables nothing - did the file get truncated?"
    for entry in policy["disabled"]:
        assert entry.get("why", "").strip(), f"{entry['rule']} has no rationale"


def test_rule_keys_are_unique() -> None:
    """A rule listed twice means two rationales disagree, and one of them is dead text."""
    keys = [entry["rule"] for entry in load_policy()["disabled"]]
    assert len(keys) == len(set(keys)), f"duplicate rule keys: {keys}"


def test_disabled_and_keep_do_not_overlap() -> None:
    """A rule cannot be both rejected and deliberately retained."""
    policy = load_policy()
    disabled = {entry["rule"] for entry in policy["disabled"]}
    kept = {entry["rule"] for entry in policy.get("keep", [])}
    assert not (disabled & kept), f"listed as both disabled and kept: {disabled & kept}"


def test_load_policy_rejects_a_rule_with_no_rationale(tmp_path, monkeypatch) -> None:
    """The guard has to actually fire - a silent pass here would let ceremony creep back."""
    bad = tmp_path / "sonar-rules.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "organization": "arx-game",
                "project": "Arx-Game_arxii",
                "profiles": {"py": "Arx II Python"},
                "disabled": [{"rule": "python:S1234", "why": "   "}],
            }
        )
    )
    monkeypatch.setattr("sonar_profile.RULES_FILE", bad)
    with pytest.raises(SonarError, match="no `why`"):
        load_policy()


def test_rules_file_points_at_the_repo_root_copy() -> None:
    assert RULES_FILE.name == "sonar-rules.yaml"
    assert RULES_FILE.exists()


def test_every_policy_rule_has_a_known_language_prefix() -> None:
    """The drift check resolves rule languages locally; an unknown prefix costs an API call.

    That fallback is correct but slow and flaky - one call per rule is what made a
    single ConnectionResetError fail every PR. This keeps the map honest as rules
    are added.
    """
    from sonar_profile import LANG_BY_REPO

    policy = load_policy()
    keys = [e["rule"] for e in policy["disabled"]] + [e["rule"] for e in policy.get("keep", [])]
    unknown = sorted({k.split(":", 1)[0] for k in keys} - set(LANG_BY_REPO))
    assert not unknown, (
        f"rule repositories with no entry in LANG_BY_REPO: {unknown}. "
        "Add them so the drift check does not fall back to one API call per rule."
    )


def test_no_duplicate_top_level_keys() -> None:
    """A repeated top-level key silently discards everything under the earlier one.

    yaml.safe_load resolves duplicates by keeping the LAST occurrence and raises
    nothing, so a policy section can stop existing without any error. That happened:
    a scripted edit in #3602 left two `false_positives:` keys, and the whole first
    block - a standing disposition plus its rationale - was dropped by the parser
    while still reading correctly in the file.
    """
    seen = [
        line.split(":", 1)[0]
        for line in RULES_FILE.read_text().splitlines()
        if line
        and not line[0].isspace()
        and not line.startswith("#")
        and line.rstrip().endswith(":")
    ]
    duplicates = sorted({key for key in seen if seen.count(key) > 1})
    assert not duplicates, (
        f"duplicate top-level keys in sonar-rules.yaml: {duplicates}. "
        "YAML keeps only the last, so the earlier section is silently ignored."
    )


def test_false_positive_entries_are_scoped_and_explained() -> None:
    """An instance disposition without a path or a reason cannot be reviewed."""
    for entry in load_policy().get("false_positives", []):
        assert entry.get("path"), (
            f"{entry['rule']} has no path; it would suppress the rule globally"
        )
        assert entry.get("why", "").strip(), f"{entry['rule']} has no rationale"
