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
    """A GitHub REST call failed. Message carries the status code only, never the body.

    ``status_code`` is None for a transport-level failure (could not reach GitHub at
    all) and set for any other failure (unexpected status, non-JSON body) - callers
    that need to tell those apart (to reproduce a pre-existing message, say) can
    branch on it without parsing the message text.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _auth_token() -> str:
    """Return the configured GitHub token, or empty string if unset.

    settings.GITHUB_ISSUE_TOKEN already falls back to the GH_TOKEN env var at
    settings-load time (see server/conf/settings.py), so no separate lookup
    is needed here.
    """
    return settings.GITHUB_ISSUE_TOKEN


def github_request(
    method: str,
    path: str,
    *,
    payload: dict | None = None,
    expected_status: int | None = None,
) -> dict | list:
    """One authenticated call to api.github.com; raises GitHubRestError.

    Token from settings.GITHUB_ISSUE_TOKEN (falls back to GH_TOKEN in settings);
    headers Bearer + application/vnd.github+json + X-GitHub-Api-Version
    2022-11-28; timeout 10s. By default any 2xx status is a success; pass
    ``expected_status`` to require an exact status code instead (GitHub's
    issue-creation endpoint, for instance, only ever succeeds with 201).
    Non-success and a non-JSON success body both raise with the status code
    ONLY (the body may echo a private repo name and error text travels into
    admin flashes).
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
    if expected_status is not None:
        succeeded = response.status_code == expected_status
    else:
        succeeded = 200 <= response.status_code < 300
    if not succeeded:
        raise GitHubRestError(
            f"GitHub REST call failed (HTTP {response.status_code}).",
            status_code=response.status_code,
        )
    try:
        return response.json()
    except ValueError as exc:
        raise GitHubRestError(
            f"GitHub returned a non-JSON response (HTTP {response.status_code}).",
            status_code=response.status_code,
        ) from exc
