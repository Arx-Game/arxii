"""Staff inbox aggregator service.

Reads from multiple submission sources (PlayerFeedback, BugReport,
PlayerReport, RosterApplication) and returns a unified list for staff
triage. Does not own any models — purely a view layer.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from world.gm.constants import GMApplicationStatus
from world.gm.models import GMApplication
from world.player_submissions.constants import SubmissionCategory, SubmissionStatus
from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport
from world.roster.models.applications import RosterApplication
from world.roster.models.choices import ApplicationStatus
from world.staff_inbox.types import InboxItem

#: Cap per-category slice in account history responses. This endpoint is a
#: summary view, not paginated — the frontend can link to per-type ViewSets
#: with filters for deeper exploration.
MAX_PER_CATEGORY = 100


def _reporter_summary(persona_name: str, account_username: str) -> str:
    return f"{persona_name} (Account {account_username})"


def _feedback_to_item(obj: PlayerFeedback) -> InboxItem:
    return InboxItem(
        source_type=SubmissionCategory.PLAYER_FEEDBACK,
        source_pk=obj.pk,
        title=f"Feedback: {obj.description[:60]}",
        reporter_summary=_reporter_summary(
            obj.reporter_persona.name,
            obj.reporter_account.username,
        ),
        created_at=obj.created_at,
        status=obj.status,
        detail_url=reverse(
            "player_submissions:player-feedback-detail",
            args=[obj.pk],
        ),
    )


def _bug_to_item(obj: BugReport) -> InboxItem:
    return InboxItem(
        source_type=SubmissionCategory.BUG_REPORT,
        source_pk=obj.pk,
        title=f"Bug: {obj.description[:60]}",
        reporter_summary=_reporter_summary(
            obj.reporter_persona.name,
            obj.reporter_account.username,
        ),
        created_at=obj.created_at,
        status=obj.status,
        detail_url=reverse(
            "player_submissions:bug-report-detail",
            args=[obj.pk],
        ),
    )


def _report_to_item(obj: PlayerReport) -> InboxItem:
    reported = _reporter_summary(
        obj.reported_persona.name,
        obj.reported_account.username,
    )
    return InboxItem(
        source_type=SubmissionCategory.PLAYER_REPORT,
        source_pk=obj.pk,
        title=f"Report: {reported}",
        reporter_summary=_reporter_summary(
            obj.reporter_persona.name,
            obj.reporter_account.username,
        ),
        created_at=obj.created_at,
        status=obj.status,
        detail_url=reverse(
            "player_submissions:player-report-detail",
            args=[obj.pk],
        ),
    )


def _application_to_item(obj: RosterApplication) -> InboxItem:
    # TODO: Switch to `reverse("roster:application-detail", args=[obj.pk])`
    # once the roster app exposes a RosterApplicationViewSet. Right now
    # the roster urls.py does not register an applications route, so the
    # URL is hardcoded to match the future endpoint shape.
    return InboxItem(
        source_type=SubmissionCategory.CHARACTER_APPLICATION,
        source_pk=obj.pk,
        title=f"Application: {obj.character.db_key}",
        reporter_summary=f"Applicant: {obj.player_data.account.username}",
        created_at=obj.applied_date,
        status=obj.status,
        detail_url=f"/api/roster/applications/{obj.pk}/",
    )


def _gm_application_to_item(obj: GMApplication) -> InboxItem:
    return InboxItem(
        source_type=SubmissionCategory.GM_APPLICATION,
        source_pk=obj.pk,
        title=f"GM Application: {obj.account.username}",
        reporter_summary=f"Applicant: {obj.account.username}",
        created_at=obj.created_at,
        status=obj.status,
        detail_url=f"/api/gm/applications/{obj.pk}/",
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

    def _include(cat: str) -> bool:
        return categories is None or cat in categories

    items: list[InboxItem] = []

    if _include(SubmissionCategory.PLAYER_FEEDBACK):
        feedback_qs = PlayerFeedback.objects.filter(
            status=SubmissionStatus.OPEN,
        ).select_related(
            "reporter_account",
            "reporter_persona__character",
        )
        items.extend(_feedback_to_item(fb) for fb in feedback_qs)

    if _include(SubmissionCategory.BUG_REPORT):
        bug_qs = BugReport.objects.filter(
            status=SubmissionStatus.OPEN,
        ).select_related(
            "reporter_account",
            "reporter_persona__character",
        )
        items.extend(_bug_to_item(br) for br in bug_qs)

    if _include(SubmissionCategory.PLAYER_REPORT):
        report_qs = PlayerReport.objects.filter(
            status=SubmissionStatus.OPEN,
        ).select_related(
            "reporter_account",
            "reported_account",
            "reporter_persona__character",
            "reported_persona__character",
        )
        items.extend(_report_to_item(pr) for pr in report_qs)

    if _include(SubmissionCategory.CHARACTER_APPLICATION):
        application_qs = RosterApplication.objects.filter(
            status=ApplicationStatus.PENDING,
        ).select_related("character", "player_data__account")
        items.extend(_application_to_item(app) for app in application_qs)

    if _include(SubmissionCategory.GM_APPLICATION):
        gm_app_qs = GMApplication.objects.filter(
            status=GMApplicationStatus.PENDING,
        ).select_related("account")
        items.extend(_gm_application_to_item(app) for app in gm_app_qs)

    items.sort(key=lambda i: i.created_at, reverse=True)
    return items


def get_account_submission_history(
    account_id: int,
) -> dict[str, dict[str, Any]]:
    """Return all submissions related to an account.

    Uses the directly-stored ``reporter_account`` and ``reported_account``
    FKs — no walking the persona/tenure chain. Each category is capped at
    ``MAX_PER_CATEGORY`` items with a ``truncated`` flag and a ``total``
    count, so staff can see the scale at a glance and know when to drill
    into the per-type management ViewSet for deeper exploration.

    Returns a dict with keys: reports_against, reports_submitted,
    feedback, bug_reports, character_applications. Each value is a dict
    of the shape ``{"items": [...], "total": int, "truncated": bool}``.
    """
    reports_against_qs = (
        PlayerReport.objects.filter(reported_account_id=account_id)
        .select_related(
            "reporter_account",
            "reported_account",
            "reporter_persona__character",
            "reported_persona__character",
        )
        .order_by("-created_at")
    )
    reports_against_total = reports_against_qs.count()
    reports_against = list(reports_against_qs[:MAX_PER_CATEGORY])

    reports_submitted_qs = (
        PlayerReport.objects.filter(reporter_account_id=account_id)
        .select_related(
            "reporter_account",
            "reported_account",
            "reporter_persona__character",
            "reported_persona__character",
        )
        .order_by("-created_at")
    )
    reports_submitted_total = reports_submitted_qs.count()
    reports_submitted = list(reports_submitted_qs[:MAX_PER_CATEGORY])

    feedback_qs = (
        PlayerFeedback.objects.filter(reporter_account_id=account_id)
        .select_related(
            "reporter_account",
            "reporter_persona__character",
        )
        .order_by("-created_at")
    )
    feedback_total = feedback_qs.count()
    feedback = list(feedback_qs[:MAX_PER_CATEGORY])

    bug_reports_qs = (
        BugReport.objects.filter(reporter_account_id=account_id)
        .select_related(
            "reporter_account",
            "reporter_persona__character",
        )
        .order_by("-created_at")
    )
    bug_reports_total = bug_reports_qs.count()
    bug_reports = list(bug_reports_qs[:MAX_PER_CATEGORY])

    applications_qs = (
        RosterApplication.objects.filter(
            player_data__account_id=account_id,
        )
        .select_related("character", "player_data__account")
        .order_by("-applied_date")
    )
    applications_total = applications_qs.count()
    applications = list(applications_qs[:MAX_PER_CATEGORY])

    def _wrap(items: list[InboxItem], total: int) -> dict[str, Any]:
        return {
            "items": items,
            "total": total,
            "truncated": total > MAX_PER_CATEGORY,
        }

    return {
        "reports_against": _wrap(
            [_report_to_item(r) for r in reports_against],
            reports_against_total,
        ),
        "reports_submitted": _wrap(
            [_report_to_item(r) for r in reports_submitted],
            reports_submitted_total,
        ),
        "feedback": _wrap(
            [_feedback_to_item(f) for f in feedback],
            feedback_total,
        ),
        "bug_reports": _wrap(
            [_bug_to_item(b) for b in bug_reports],
            bug_reports_total,
        ),
        "character_applications": _wrap(
            [_application_to_item(a) for a in applications],
            applications_total,
        ),
    }
