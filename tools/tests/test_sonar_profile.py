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
