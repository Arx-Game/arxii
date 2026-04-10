"""Staff inbox aggregator service.

Reads from multiple submission sources (PlayerFeedback, BugReport,
PlayerReport, RosterApplication) and returns a unified list for staff
triage. Does not own any models — purely a view layer.
"""

from __future__ import annotations

from world.player_submissions.constants import SubmissionCategory, SubmissionStatus
from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport
from world.roster.models.applications import RosterApplication
from world.roster.models.choices import ApplicationStatus
from world.staff_inbox.types import InboxItem


def _feedback_to_item(obj: PlayerFeedback) -> InboxItem:
    return InboxItem(
        source_type=SubmissionCategory.PLAYER_FEEDBACK,
        source_pk=obj.pk,
        title=f"Feedback: {obj.description[:60]}",
        reporter_summary=obj.reporter_persona.get_identity_summary(
            include_account=True,
        ),
        created_at=obj.created_at,
        status=obj.status,
        detail_url=f"/api/player-submissions/feedback/{obj.pk}/",
    )


def _bug_to_item(obj: BugReport) -> InboxItem:
    return InboxItem(
        source_type=SubmissionCategory.BUG_REPORT,
        source_pk=obj.pk,
        title=f"Bug: {obj.description[:60]}",
        reporter_summary=obj.reporter_persona.get_identity_summary(
            include_account=True,
        ),
        created_at=obj.created_at,
        status=obj.status,
        detail_url=f"/api/player-submissions/bug-reports/{obj.pk}/",
    )


def _report_to_item(obj: PlayerReport) -> InboxItem:
    reporter = obj.reporter_persona.get_identity_summary(include_account=True)
    reported = obj.reported_persona.get_identity_summary(include_account=True)
    return InboxItem(
        source_type=SubmissionCategory.PLAYER_REPORT,
        source_pk=obj.pk,
        title=f"Report: {reported}",
        reporter_summary=reporter,
        created_at=obj.created_at,
        status=obj.status,
        detail_url=f"/api/player-submissions/player-reports/{obj.pk}/",
    )


def _application_to_item(obj: RosterApplication) -> InboxItem:
    return InboxItem(
        source_type=SubmissionCategory.CHARACTER_APPLICATION,
        source_pk=obj.pk,
        title=f"Application: {obj.character.db_key}",
        reporter_summary=f"Applicant: {obj.player_data.account.username}",
        created_at=obj.applied_date,
        status=obj.status,
        detail_url=f"/api/roster/applications/{obj.pk}/",
    )


def get_staff_inbox(
    *,
    categories: list[str] | None = None,
) -> list[InboxItem]:
    """Aggregate open items from all submission sources.

    Args:
        categories: Optional list of source_type strings (matching
            SubmissionCategory values) to include. If None, all
            categories are included.

    Returns:
        List of InboxItem sorted by created_at descending.
    """
    items: list[InboxItem] = []

    def _include(cat: str) -> bool:
        return categories is None or cat in categories

    if _include(SubmissionCategory.PLAYER_FEEDBACK):
        items.extend(
            _feedback_to_item(fb)
            for fb in PlayerFeedback.objects.filter(
                status=SubmissionStatus.OPEN,
            ).select_related("reporter_persona__character")
        )

    if _include(SubmissionCategory.BUG_REPORT):
        items.extend(
            _bug_to_item(br)
            for br in BugReport.objects.filter(
                status=SubmissionStatus.OPEN,
            ).select_related("reporter_persona__character")
        )

    if _include(SubmissionCategory.PLAYER_REPORT):
        items.extend(
            _report_to_item(pr)
            for pr in PlayerReport.objects.filter(
                status=SubmissionStatus.OPEN,
            ).select_related(
                "reporter_persona__character",
                "reported_persona__character",
            )
        )

    if _include(SubmissionCategory.CHARACTER_APPLICATION):
        items.extend(
            _application_to_item(app)
            for app in RosterApplication.objects.filter(
                status=ApplicationStatus.PENDING,
            ).select_related("character", "player_data__account")
        )

    items.sort(key=lambda i: i.created_at, reverse=True)
    return items
