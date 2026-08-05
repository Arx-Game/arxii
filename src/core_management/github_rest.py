"""Shared authenticated client for the GitHub REST API (#3018).

One HTTP client, not two: both ``content_session.py`` (opening the row-export
session's pull request) and ``world/player_submissions/github_issues.py``
(staff-filed bug/error issues) route their calls through ``github_request``
here rather than each hand-rolling ``requests`` calls with their own auth
headers.

Error messages never carry the response body - only the HTTP status code.
GitHub error bodies can echo back request details (including a private repo
name), and callers surface these messages verbatim in admin flashes and API
error responses.
"""

from __future__ import annotations

from django.conf import settings
import requests

_GITHUB_API = "https://api.github.com"
_REQUEST_TIMEOUT = 10
_METHOD_GET = "GET"
_METHOD_POST = "POST"


class GitHubRestError(Exception):
    """A GitHub REST call failed. Message carries the status code only, never the body."""


def _auth_token() -> str:
    """Return the configured GitHub token, or empty string if unset.

    settings.GITHUB_ISSUE_TOKEN already falls back to the GH_TOKEN env var at
    settings-load time (see server/conf/settings.py), so no separate lookup
    is needed here.
    """
    return settings.GITHUB_ISSUE_TOKEN


def github_request(method: str, path: str, *, payload: dict | None = None) -> dict | list:
    """One authenticated call to api.github.com; raises GitHubRestError.

    Token from settings.GITHUB_ISSUE_TOKEN (falls back to GH_TOKEN in settings);
    headers Bearer + application/vnd.github+json + X-GitHub-Api-Version
    2022-11-28; timeout 10s; non-2xx raises with the status code ONLY (the
    body may echo a private repo name and error text travels into admin
    flashes).
    """
    token = _auth_token()
    if not token:
        raise GitHubRestError(
            "GitHub is not configured on this server (set GITHUB_ISSUE_TOKEN or GH_TOKEN)."
        )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{_GITHUB_API}{path}"
    try:
        if method == _METHOD_GET:
            response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
        elif method == _METHOD_POST:
            response = requests.post(url, json=payload, headers=headers, timeout=_REQUEST_TIMEOUT)
        else:
            raise GitHubRestError(f"Unsupported GitHub REST method: {method}")
    except requests.RequestException as exc:
        raise GitHubRestError("Could not reach GitHub.") from exc
    if not (200 <= response.status_code < 300):
        raise GitHubRestError(f"GitHub REST call failed (HTTP {response.status_code}).")
    return response.json()
