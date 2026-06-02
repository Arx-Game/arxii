from pathlib import PurePosixPath

SONAR_ORG = "arx-game"
SONAR_PROJECT = "Arx-Game_arxii"
GH_REPO = "Arx-Game/arxii"
SONAR_BASE = "https://sonarcloud.io/api"

# Impact severity from highest to lowest (covers both new and legacy taxonomy)
SEVERITY_ORDER: dict[str, int] = {
    "BLOCKER": 5,
    "HIGH": 4,
    "CRITICAL": 4,
    "MEDIUM": 3,
    "MAJOR": 3,
    "LOW": 2,
    "MINOR": 2,
    "INFO": 1,
}


def file_path(component: str) -> str:
    """Extract the file path from a SonarCloud component key (drops 'Project:' prefix)."""
    return component.split(":", 1)[1] if ":" in component else component


def is_skip_path(component: str) -> bool:
    """Return True if this component should never produce a GitHub issue."""
    path_str = file_path(component)
    path = PurePosixPath(path_str)
    return (
        "tests" in path.parts
        or path.name == "tests.py"
        or path.name.startswith("test_")
        or "migrations" in path.parts
        or path_str == "src/cli/arx.py"
    )


def effective_severity(raw: dict) -> str:
    """Return the single highest-severity label, checking impacts then legacy field."""
    candidates = [i.get("severity", "INFO") for i in raw.get("impacts", [])]
    candidates.append(raw.get("severity", "INFO"))
    return max(candidates, key=lambda s: SEVERITY_ORDER.get(s, 0))


def severity_tier(raw: dict) -> str | None:
    """Return 'blocker', 'high', or None (below threshold — do not create issue)."""
    sev = effective_severity(raw)
    if sev == "BLOCKER":
        return "blocker"
    if sev in ("HIGH", "CRITICAL"):
        return "high"
    return None


def is_security(raw: dict) -> bool:
    """Return True if this is a security-type finding (excluded from public issues)."""
    return raw.get("type") in ("VULNERABILITY", "SECURITY_HOTSPOT") or any(
        i.get("softwareQuality") == "SECURITY" for i in raw.get("impacts", [])
    )
