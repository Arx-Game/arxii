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


def get_account_submission_history(
    account_id: int,
) -> dict[str, list[InboxItem]]:
    """Return all submissions related to an account.

    Walks the persona -> character -> tenure -> account chain to find:
    - Reports against any character this account has played
    - Reports submitted while this account was playing
    - Feedback and bug reports submitted
    - Character applications

    Returns a dict with keys: reports_against, reports_submitted,
    feedback, bug_reports, character_applications.
    """
    from world.roster.models.tenures import RosterTenure  # noqa: PLC0415

    # Characters this account has ever played (any tenure, active or ended)
    character_ids = list(
        RosterTenure.objects.filter(
            player_data__account_id=account_id,
        ).values_list("roster_entry__character_id", flat=True),
    )

    reports_against = list(
        PlayerReport.objects.filter(
            reported_persona__character_id__in=character_ids,
        )
        .select_related(
            "reporter_persona__character",
            "reported_persona__character",
        )
        .order_by("-created_at"),
    )

    reports_submitted = list(
        PlayerReport.objects.filter(
            reporter_persona__character_id__in=character_ids,
        )
        .select_related(
            "reporter_persona__character",
            "reported_persona__character",
        )
        .order_by("-created_at"),
    )

    feedback = list(
        PlayerFeedback.objects.filter(
            reporter_persona__character_id__in=character_ids,
        )
        .select_related("reporter_persona__character")
        .order_by("-created_at"),
    )

    bug_reports = list(
        BugReport.objects.filter(
            reporter_persona__character_id__in=character_ids,
        )
        .select_related("reporter_persona__character")
        .order_by("-created_at"),
    )

    applications = list(
        RosterApplication.objects.filter(
            player_data__account_id=account_id,
        )
        .select_related("character", "player_data__account")
        .order_by("-applied_date"),
    )

    return {
        "reports_against": [_report_to_item(r) for r in reports_against],
        "reports_submitted": [_report_to_item(r) for r in reports_submitted],
        "feedback": [_feedback_to_item(f) for f in feedback],
        "bug_reports": [_bug_to_item(b) for b in bug_reports],
        "character_applications": [_application_to_item(a) for a in applications],
    }
