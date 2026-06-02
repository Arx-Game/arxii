from sonarcloud_constants import (
    effective_severity,
    file_path,
    is_security,
    is_skip_path,
    severity_tier,
)


def test_file_path_strips_project_prefix():
    assert file_path("Arx-Game_arxii:src/world/magic/services.py") == "src/world/magic/services.py"


def test_file_path_no_prefix_passthrough():
    assert file_path("src/foo.py") == "src/foo.py"


def test_is_skip_path_test_directory():
    assert is_skip_path("Arx-Game_arxii:src/world/magic/tests/test_services.py")


def test_is_skip_path_tests_py():
    assert is_skip_path("Arx-Game_arxii:src/world/roster/tests.py")


def test_is_skip_path_test_file_in_root():
    assert is_skip_path("Arx-Game_arxii:src/world/magic/tests/test_scar.py")


def test_is_skip_path_migrations():
    assert is_skip_path("Arx-Game_arxii:src/world/magic/migrations/0001_initial.py")


def test_is_skip_path_arx_cli():
    assert is_skip_path("Arx-Game_arxii:src/cli/arx.py")


def test_is_skip_path_normal_service_file():
    assert not is_skip_path("Arx-Game_arxii:src/world/magic/services.py")


def test_is_skip_path_normal_model_file():
    assert not is_skip_path("Arx-Game_arxii:src/world/roster/models.py")


def test_is_skip_path_works_without_project_prefix():
    assert is_skip_path("src/cli/arx.py")
    assert not is_skip_path("src/world/magic/services.py")


def test_effective_severity_prefers_impact_over_legacy():
    raw = {
        "severity": "MAJOR",
        "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "HIGH"}],
    }
    assert effective_severity(raw) == "HIGH"


def test_effective_severity_uses_legacy_when_no_impacts():
    raw = {"severity": "BLOCKER", "impacts": []}
    assert effective_severity(raw) == "BLOCKER"


def test_effective_severity_picks_highest_of_multiple_impacts():
    raw = {
        "severity": "MINOR",
        "impacts": [
            {"softwareQuality": "RELIABILITY", "severity": "MEDIUM"},
            {"softwareQuality": "MAINTAINABILITY", "severity": "HIGH"},
        ],
    }
    assert effective_severity(raw) == "HIGH"


def test_severity_tier_blocker_from_legacy():
    assert severity_tier({"severity": "BLOCKER", "impacts": []}) == "blocker"


def test_severity_tier_high_from_impact():
    raw = {
        "severity": "MAJOR",
        "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "HIGH"}],
    }
    assert severity_tier(raw) == "high"


def test_severity_tier_critical_legacy_maps_to_high():
    assert severity_tier({"severity": "CRITICAL", "impacts": []}) == "high"


def test_severity_tier_medium_returns_none():
    raw = {
        "severity": "MAJOR",
        "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "MEDIUM"}],
    }
    assert severity_tier(raw) is None


def test_severity_tier_low_returns_none():
    assert severity_tier({"severity": "MINOR", "impacts": []}) is None


def test_is_security_vulnerability_type():
    assert is_security({"type": "VULNERABILITY", "impacts": []})


def test_is_security_hotspot_type():
    assert is_security({"type": "SECURITY_HOTSPOT", "impacts": []})


def test_is_security_via_impact_quality():
    raw = {
        "type": "CODE_SMELL",
        "impacts": [{"softwareQuality": "SECURITY", "severity": "HIGH"}],
    }
    assert is_security(raw)


def test_is_security_false_for_maintainability_code_smell():
    raw = {
        "type": "CODE_SMELL",
        "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "HIGH"}],
    }
    assert not is_security(raw)
