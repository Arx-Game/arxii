"""Shared Sentry Web API access for the digest and resolve tools.

Read access needs a Sentry *organization* auth token in ``SENTRY_AUTH_TOKEN``
(scopes: ``org:read``, ``project:read``, ``event:read``, and ``event:write`` for
resolving). This is deliberately a different credential from the ``SENTRY_DSN``
in ``src/server/conf/settings.py`` — the DSN is write-only ingest and cannot read
anything back.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

SENTRY_ORG = "arx2"
# Numeric project id from the Sentry issue-stream URL (?project=...). The org
# issues endpoint accepts numeric ids, so no slug lookup is needed.
SENTRY_PROJECT_ID = "4511905661386752"
SENTRY_BASE = "https://sentry.io/api/0"
GH_REPO = "Arx-Game/arxii"

TOKEN_ENV = "SENTRY_AUTH_TOKEN"  # noqa: S105 - env var name, not a credential


class SentryAuthError(RuntimeError):
    """Raised when no Sentry auth token is configured."""


def _token() -> str:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        msg = (
            f"{TOKEN_ENV} is not set. Create an organization auth token at "
            f"https://sentry.io/settings/{SENTRY_ORG}/auth-tokens/ with scopes "
            f"org:read, project:read, event:read, event:write."
        )
        raise SentryAuthError(msg)
    return token


def api_request(
    path: str,
    *,
    params: dict | None = None,
    method: str = "GET",
    body: dict | None = None,
):
    """Call the Sentry Web API and return the decoded JSON response."""
    url = f"{SENTRY_BASE}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    request.add_header("Authorization", f"Bearer {_token()}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request) as resp:  # noqa: S310
        raw = resp.read()
    return json.loads(raw) if raw else None


def fetch_unresolved_issues(limit: int = 100) -> list[dict]:
    """Return currently unresolved Sentry issues for the project, newest activity first."""
    return (
        api_request(
            f"/organizations/{SENTRY_ORG}/issues/",
            params={
                "query": "is:unresolved",
                "project": SENTRY_PROJECT_ID,
                "statsPeriod": "14d",
                "limit": limit,
            },
        )
        or []
    )


def issue_url(issue_id: str) -> str:
    """Permalink to a single Sentry issue."""
    return f"https://sentry.io/organizations/{SENTRY_ORG}/issues/{issue_id}/"
