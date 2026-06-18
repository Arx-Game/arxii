"""Staff-initiated GitHub issue filing from reports (#1164).

Staff can turn a player ``BugReport`` or an auto-captured ``SystemErrorReport`` into a
public GitHub issue. Nothing auto-files — a staff member reviews and confirms each one,
so this module's job is (a) build a *redacted draft* (known player names stripped) for
staff to edit, and (b) POST the staff-approved text to the GitHub REST API and record the
resulting issue on the report. The redaction is best-effort on the names we hold as
structured data; the staff edit pass before confirm is the real whitelist.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from django.conf import settings
import requests

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.player_submissions.models import BugReport, SystemErrorReport

_GITHUB_API = "https://api.github.com"
_REQUEST_TIMEOUT = 10
_REDACTED = "[redacted]"


class GitHubIssueError(Exception):
    """A GitHub issue could not be filed. Carries a safe, user-facing message.

    ``user_message`` is what the staff member sees — never a raw exception string or an
    API response body (which could leak the token or internal detail).
    """

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True)
class IssueDraft:
    """A redacted, staff-editable draft of the issue to file.

    ``stub_body`` is the one-click "sensitive / exploit — omit details" alternative: it
    withholds the report contents entirely, keeping only the internal back-reference.
    """

    title: str
    body: str
    stub_body: str


def redact_text(text: str, names: Iterable[str]) -> str:
    """Strip the given names from ``text`` (case-insensitive), best-effort.

    Only the names we hold as structured data are stripped here; staff catch anything
    else (other players, free-text specifics) in the edit pass before filing.
    """
    redacted = text
    for name in names:
        if name:
            redacted = re.sub(re.escape(name), _REDACTED, redacted, flags=re.IGNORECASE)
    return redacted


def _internal_ref(path: str) -> str:
    return f"{settings.SITE_URL}{path}"


def issue_draft_for_bug(report: BugReport) -> IssueDraft:
    """Redacted draft for a player bug report — reporter identity withheld."""
    names = [report.reporter_persona.name, report.reporter_account.username]
    description = redact_text(report.description, names)
    ref = _internal_ref(f"/staff/bug-reports/{report.pk}")
    body = (
        f"{description}\n\n"
        "---\n"
        "_Filed by staff from a player bug report. Reporter identity withheld; "
        f"see the internal staff tracker._\n\nInternal ref: {ref}"
    )
    stub_body = (
        "A player-reported bug. Details withheld (sensitive / possible exploit); "
        f"tracked internally.\n\nInternal ref: {ref}"
    )
    return IssueDraft(title=f"Player bug report #{report.pk}", body=body, stub_body=stub_body)


def issue_draft_for_error(report: SystemErrorReport) -> IssueDraft:
    """Redacted draft for an auto-captured error — traceback included, names stripped."""
    names = [report.actor_persona.name] if report.actor_persona_id is not None else []
    message = redact_text(report.message, names)
    traceback = redact_text(report.traceback, names)
    ref = _internal_ref(f"/staff/system-errors/{report.pk}")
    body = (
        f"**Exception:** `{report.exception_type}`\n"
        f"**Where:** {report.label}\n"
        f"**Occurrences:** {report.occurrence_count}\n\n"
        f"{message}\n\n"
        f"```\n{traceback}\n```\n\n"
        f"---\nInternal ref: {ref}"
    )
    stub_body = (
        f"An auto-captured `{report.exception_type}`. Details withheld; "
        f"tracked internally.\n\nInternal ref: {ref}"
    )
    return IssueDraft(
        title=f"{report.exception_type} in {report.label}",
        body=body,
        stub_body=stub_body,
    )


def create_github_issue(*, title: str, body: str, labels: list[str]) -> tuple[int, str]:
    """POST a single issue to the configured repo; return ``(number, html_url)``.

    Raises ``GitHubIssueError`` (never leaking internals) when the feature is unconfigured,
    the network call fails, or GitHub rejects the request.
    """
    token = settings.GITHUB_ISSUE_TOKEN
    repo = settings.GITHUB_ISSUE_REPO
    if not token:
        msg = "GitHub issue filing is not configured on this server."
        raise GitHubIssueError(msg)
    try:
        response = requests.post(
            f"{_GITHUB_API}/repos/{repo}/issues",
            json={"title": title, "body": body, "labels": labels},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=_REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        msg = "Could not reach GitHub to file the issue. Please try again."
        raise GitHubIssueError(msg) from exc
    if response.status_code != requests.codes.created:
        msg = f"GitHub rejected the issue (HTTP {response.status_code})."
        raise GitHubIssueError(msg)
    data = response.json()
    return data["number"], data["html_url"]


def file_issue_for_report(
    report: BugReport | SystemErrorReport,
    *,
    title: str,
    body: str,
    labels: list[str],
) -> None:
    """Create the issue and record its number + url on the report.

    Caller guarantees the report has not already been filed (idempotency lives at the
    action layer, which short-circuits when ``github_issue_url`` is already set).
    """
    number, url = create_github_issue(title=title, body=body, labels=labels)
    report.github_issue_number = number
    report.github_issue_url = url
    report.save(update_fields=["github_issue_number", "github_issue_url"])
