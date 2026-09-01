#!/usr/bin/env python3
"""Reconcile SonarCloud Quality Profiles with `sonar-rules.yaml`.

`sonar-project.properties` cannot turn a rule off in this project: SonarCloud
Automatic Analysis reads it for `sonar.exclusions` but ignores
`sonar.issue.ignore.multicriteria` entirely, so three such entries sat in the repo
for months while every rule they named kept firing (#3548). Custom Quality Profiles
are the mechanism that does work, and this script is how they stay reviewable —
the YAML file is the source of truth, SonarCloud is a projection of it.

    python tools/sonar_profile.py --check    # drift detection; CI runs this
    python tools/sonar_profile.py --apply    # push the YAML to SonarCloud

`--apply` needs SONAR_TOKEN (see src/.env). `--check` reads public endpoints and
works without one, so CI needs no secret to catch a rule being re-enabled by hand.

Profiles are COPIES of the built-in "Sonar way", not children: SonarCloud refuses
to deactivate a rule inherited from a parent. The cost is that new "Sonar way"
rules do not arrive on their own; `--check` reports that drift so it stays a
visible decision.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

SONAR_BASE = "https://sonarcloud.io/api"
BUILTIN_PARENT = "Sonar way"
RULES_FILE = Path(__file__).resolve().parent.parent / "sonar-rules.yaml"
HTTP_NO_CONTENT = 204


class SonarError(RuntimeError):
    """A SonarCloud API call failed."""


def _request(path: str, params: dict[str, str], *, post: bool = False) -> dict | None:
    """Call the SonarCloud API, returning parsed JSON (None for empty 204 bodies)."""
    token = os.environ.get("SONAR_TOKEN", "")
    encoded = urllib.parse.urlencode(params)
    if post:
        req = urllib.request.Request(  # noqa: S310 - fixed https host
            f"{SONAR_BASE}/{path}", data=encoded.encode(), method="POST"
        )
    else:
        req = urllib.request.Request(f"{SONAR_BASE}/{path}?{encoded}")  # noqa: S310
    if token:
        basic = base64.b64encode(f"{token}:".encode()).decode()
        req.add_header("Authorization", f"Basic {basic}")
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:400]
        msg = f"{path} -> HTTP {exc.code}: {detail}"
        raise SonarError(msg) from exc
    return json.loads(body) if body.strip() else None


def load_policy() -> dict:
    """Parse sonar-rules.yaml, failing loudly on a disabled rule with no rationale."""
    policy = yaml.safe_load(RULES_FILE.read_text())
    unexplained = [
        entry["rule"] for entry in policy["disabled"] if not (entry.get("why") or "").strip()
    ]
    if unexplained:
        msg = (
            f"{RULES_FILE.name}: these disabled rules have no `why`: {unexplained}. "
            "A rule turned off without a stated reason is indistinguishable from an oversight."
        )
        raise SonarError(msg)
    return policy


def rule_languages(rule_keys: list[str], organization: str) -> dict[str, str]:
    """Map each rule key to its SonarCloud language.

    Resolved from the API rather than parsed out of the key, because the repository
    prefix and the language are not the same thing: `pythonbugs:S2259` and
    `pythonenterprise:S8443` are both `py`, and `Web:...` is `web`.
    """
    languages: dict[str, str] = {}
    for key in rule_keys:
        data = _request("rules/show", {"organization": organization, "key": key})
        if data is None or "rule" not in data:
            msg = f"rule {key} not found on SonarCloud - is the key a typo?"
            raise SonarError(msg)
        languages[key] = data["rule"]["lang"]
    return languages


def profiles_for(organization: str, language: str) -> dict[str, dict]:
    """All quality profiles for one language, keyed by name."""
    data = _request("qualityprofiles/search", {"organization": organization, "language": language})
    return {p["name"]: p for p in (data or {}).get("profiles", [])}


def project_profile_names(organization: str, project: str) -> dict[str, str]:
    """The profile name each language currently uses ON THE PROJECT, keyed by language."""
    data = _request("qualityprofiles/search", {"organization": organization, "project": project})
    return {p["language"]: p["name"] for p in (data or {}).get("profiles", [])}


def is_rule_active(organization: str, profile_key: str, rule: str) -> bool:
    """Whether one rule is active in one profile."""
    data = _request(
        "rules/search",
        {
            "organization": organization,
            "qprofile": profile_key,
            "activation": "true",
            "rule_key": rule,
        },
    )
    return bool((data or {}).get("total", 0))


def apply_policy(policy: dict) -> int:
    """Create/refresh the profiles, deactivate the listed rules, bind them to the project."""
    org, project = policy["organization"], policy["project"]
    if not os.environ.get("SONAR_TOKEN"):
        print("--apply needs SONAR_TOKEN (see src/.env).", file=sys.stderr)
        return 2

    disabled = [entry["rule"] for entry in policy["disabled"]]
    languages = rule_languages(disabled, org)

    for language, profile_name in policy["profiles"].items():
        existing = profiles_for(org, language)
        if profile_name not in existing:
            parent = existing.get(BUILTIN_PARENT)
            if parent is None:
                msg = f"no built-in '{BUILTIN_PARENT}' profile for language {language}"
                raise SonarError(msg)
            _request(
                "qualityprofiles/copy",
                {"fromKey": parent["key"], "toName": profile_name},
                post=True,
            )
            print(f"  created {language}/{profile_name} (copy of {BUILTIN_PARENT})")
            existing = profiles_for(org, language)

        profile_key = existing[profile_name]["key"]
        for rule in [r for r in disabled if languages[r] == language]:
            if is_rule_active(org, profile_key, rule):
                _request(
                    "qualityprofiles/deactivate_rule",
                    {"key": profile_key, "rule": rule},
                    post=True,
                )
                print(f"  {language}: deactivated {rule}")

        _request(
            "qualityprofiles/add_project",
            {
                "organization": org,
                "language": language,
                "qualityProfile": profile_name,
                "project": project,
            },
            post=True,
        )
    print(f"applied: {len(disabled)} rules across {len(policy['profiles'])} profiles")
    return 0


def check_policy(policy: dict) -> int:
    """Report any divergence between the YAML and SonarCloud. Non-zero exit on drift."""
    org, project = policy["organization"], policy["project"]
    drift: list[str] = []

    bound = project_profile_names(org, project)
    disabled = [entry["rule"] for entry in policy["disabled"]]
    kept = [entry["rule"] for entry in policy.get("keep", [])]
    languages = rule_languages(disabled + kept, org)

    for language, profile_name in policy["profiles"].items():
        if bound.get(language) != profile_name:
            drift.append(
                f"{language}: project uses profile {bound.get(language)!r}, "
                f"expected {profile_name!r}"
            )
            continue
        profile = profiles_for(org, language).get(profile_name)
        if profile is None:
            drift.append(f"{language}: profile {profile_name!r} does not exist")
            continue
        drift.extend(
            f"{language}: {rule} is ACTIVE but sonar-rules.yaml disables it"
            for rule in disabled
            if languages[rule] == language and is_rule_active(org, profile["key"], rule)
        )
        drift.extend(
            f"{language}: {rule} is INACTIVE but sonar-rules.yaml keeps it"
            for rule in kept
            if languages[rule] == language and not is_rule_active(org, profile["key"], rule)
        )

    if drift:
        print("SonarCloud has drifted from sonar-rules.yaml:", file=sys.stderr)
        for line in drift:
            print(f"  - {line}", file=sys.stderr)
        print(
            "\nRun `python tools/sonar_profile.py --apply` to reconcile, or edit "
            "sonar-rules.yaml if the change was intended.",
            file=sys.stderr,
        )
        return 1
    print(
        f"sonar-rules.yaml matches SonarCloud: {len(disabled)} disabled, "
        f"{len(kept)} kept, {len(policy['profiles'])} profiles bound."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="fail on drift (CI)")
    group.add_argument("--apply", action="store_true", help="push the YAML to SonarCloud")
    args = parser.parse_args()
    try:
        policy = load_policy()
        return apply_policy(policy) if args.apply else check_policy(policy)
    except SonarError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
