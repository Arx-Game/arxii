"""Shared Sentry Web API access for the digest and resolve tools.

Read access needs ``SENTRY_AUTH_TOKEN`` carrying ``org:read``, ``project:read``,
``event:read`` and ``event:write`` (the last for resolving). Mint it as an
**internal integration** token (Settings -> Developer Settings, permission
*Issue & Event: Read & Write*) or a user auth token - *not* an organization auth
token (``sntrys_``), whose fixed release-management scopes 403 on every issue
endpoint. This is a different credential from the ``SENTRY_DSN`` in
``src/server/conf/settings.py``, which is write-only ingest and reads nothing back.
See ``docs/operations/sentry-triage.md``.
"""

from datetime import UTC, datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SENTRY_ORG = "arx2"
# Numeric project id from the Sentry issue-stream URL (?project=...). The org
# issues endpoint accepts numeric ids, so no slug lookup is needed.
SENTRY_PROJECT_ID = "4511905661386752"
SENTRY_BASE = "https://sentry.io/api/0"
# Comfortably predates the project; the API rejects an empty statsPeriod, so an
# absolute range is the only way to ask for "all unresolved, ever".
EPOCH_START = "2020-01-01T00:00:00"
GH_REPO = "Arx-Game/arxii"

TOKEN_ENV = "SENTRY_AUTH_TOKEN"  # noqa: S105 - env var name, not a credential


class SentryAuthError(RuntimeError):
    """Raised when no Sentry auth token is configured."""


class SentryAPIError(RuntimeError):
    """Raised when the Sentry API rejects a call, carrying its own explanation."""


def _token() -> str:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        msg = (
            f"{TOKEN_ENV} is not set. Create an internal-integration or user auth "
            f"token with scopes org:read, project:read, event:read, event:write "
            f"(NOT an org auth token - see docs/operations/sentry-triage.md)."
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
    try:
        with urllib.request.urlopen(request) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        # Sentry puts the actual reason in the body ("Value ARX2-6 is not a valid
        # integer id"); a bare HTTPError traceback hides it.
        detail = exc.read().decode(errors="replace").strip()
        msg = f"Sentry API {exc.code} on {method} {path}: {detail}"
        raise SentryAPIError(msg) from None
    return json.loads(raw) if raw else None


def fetch_unresolved_issues(limit: int = 100) -> list[dict]:
    """Return every unresolved Sentry issue for the project, newest activity first.

    Queried over an absolute date range rather than ``statsPeriod``, deliberately.
    ``statsPeriod`` filters on last-seen and caps at 90d, so any window silently
    drops issues that stopped firing but were never resolved - the digest would
    report "1 unresolved" while five older ones sat open (observed 2026-09-01 with
    the 14d default). An unresolved issue is unresolved however stale it is.
    """
    issues = (
        api_request(
            f"/organizations/{SENTRY_ORG}/issues/",
            params={
                "query": "is:unresolved",
                "project": SENTRY_PROJECT_ID,
                "start": EPOCH_START,
                "end": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S"),
                "limit": limit,
            },
        )
        or []
    )
    if len(issues) >= limit:
        print(
            f"WARNING: hit the {limit}-issue page limit - the digest may be incomplete.",
            file=sys.stderr,
        )
    return issues


def issue_url(issue_id: str) -> str:
    """Permalink to a single Sentry issue."""
    return f"https://sentry.io/organizations/{SENTRY_ORG}/issues/{issue_id}/"


def numeric_issue_id(identifier: str) -> str:
    """Translate a short id (``ARX2-6``) to the numeric id the API needs.

    The bulk issues endpoint accepts *only* numeric ids - it rejects a short id
    with "Value ARX2-6 is not a valid integer id" - but short ids are what the
    digest shows and what a human reads off the Sentry UI, so accept both.
    """
    identifier = identifier.strip()
    if identifier.isdigit():
        return identifier
    found = api_request(f"/organizations/{SENTRY_ORG}/shortids/{identifier}/")
    if not found or not found.get("groupId"):
        msg = f"No Sentry issue found for short id {identifier!r}."
        raise SentryAPIError(msg)
    return str(found["groupId"])
