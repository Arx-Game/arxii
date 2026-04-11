"""Staff inbox aggregator service.

Reads from multiple submission sources (PlayerFeedback, BugReport,
PlayerReport, RosterApplication) and returns a unified list for staff
triage. Does not own any models — purely a view layer.
"""

from __future__ import annotations

from django.urls import reverse

from world.player_submissions.constants import SubmissionCategory, SubmissionStatus
from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport
from world.roster.models.applications import RosterApplication
from world.roster.models.choices import ApplicationStatus
from world.staff_inbox.types import InboxItem

#: Cap per-category slice in account history responses. This endpoint is a
#: summary view, not paginated — the frontend can link to per-type ViewSets
#: with filters for deeper exploration.
MAX_PER_CATEGORY = 100


def _resolve_identities(
    persona_ids: list[int],
) -> dict[int, tuple[str, int, str]]:
    """Batch-resolve identity summaries for a set of personas.

    Returns a dict mapping persona_id to (persona_name, player_number,
    account_username). Personas without an active tenure are mapped to
    (name, 0, "") so the caller can format them as degraded summaries.

    Uses two flat queries regardless of persona count, avoiding the N+1
    walk through Persona.get_identity_summary (persona -> character ->
    roster_entry -> current_tenure -> player_data -> account).
    """
    from world.roster.models.tenures import RosterTenure  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    if not persona_ids:
        return {}

    persona_rows = list(
        Persona.objects.filter(pk__in=persona_ids).values(
            "pk",
            "name",
            "character__roster_entry__pk",
        ),
    )

    entry_ids = [
        row["character__roster_entry__pk"]
        for row in persona_rows
        if row["character__roster_entry__pk"] is not None
    ]

    tenure_data: dict[int, tuple[int, str]] = {}
    if entry_ids:
        for tenure in RosterTenure.objects.filter(
            roster_entry_id__in=entry_ids,
            end_date__isnull=True,
        ).values(
            "roster_entry_id",
            "player_number",
            "player_data__account__username",
        ):
            tenure_data[tenure["roster_entry_id"]] = (
                tenure["player_number"],
                tenure["player_data__account__username"] or "",
            )

    result: dict[int, tuple[str, int, str]] = {}
    for row in persona_rows:
        entry_id = row["character__roster_entry__pk"]
        if entry_id is None or entry_id not in tenure_data:
            result[row["pk"]] = (row["name"], 0, "")
        else:
            player_num, account_name = tenure_data[entry_id]
            result[row["pk"]] = (row["name"], player_num, account_name)

    return result


def _format_summary(
    resolved: tuple[str, int, str],
    *,
    include_account: bool,
) -> str:
    """Format a resolved identity tuple into a display summary string."""
    name, player_num, account_name = resolved
    if player_num == 0:
        return name
    if include_account and account_name:
        return f"{name} (Player {player_num}, Account {account_name})"
    return f"{name} (Player {player_num})"


def _feedback_to_item(
    obj: PlayerFeedback,
    identities: dict[int, tuple[str, int, str]],
) -> InboxItem:
    return InboxItem(
        source_type=SubmissionCategory.PLAYER_FEEDBACK,
        source_pk=obj.pk,
        title=f"Feedback: {obj.description[:60]}",
        reporter_summary=_format_summary(
            identities[obj.reporter_persona_id],
            include_account=True,
        ),
        created_at=obj.created_at,
        status=obj.status,
        detail_url=reverse(
            "player_submissions:player-feedback-detail",
            args=[obj.pk],
        ),
    )


def _bug_to_item(
    obj: BugReport,
    identities: dict[int, tuple[str, int, str]],
) -> InboxItem:
    return InboxItem(
        source_type=SubmissionCategory.BUG_REPORT,
        source_pk=obj.pk,
        title=f"Bug: {obj.description[:60]}",
        reporter_summary=_format_summary(
            identities[obj.reporter_persona_id],
            include_account=True,
        ),
        created_at=obj.created_at,
        status=obj.status,
        detail_url=reverse(
            "player_submissions:bug-report-detail",
            args=[obj.pk],
        ),
    )


def _report_to_item(
    obj: PlayerReport,
    identities: dict[int, tuple[str, int, str]],
) -> InboxItem:
    reporter = _format_summary(
        identities[obj.reporter_persona_id],
        include_account=True,
    )
    reported = _format_summary(
        identities[obj.reported_persona_id],
        include_account=True,
    )
    return InboxItem(
        source_type=SubmissionCategory.PLAYER_REPORT,
        source_pk=obj.pk,
        title=f"Report: {reported}",
        reporter_summary=reporter,
        created_at=obj.created_at,
        status=obj.status,
        detail_url=reverse(
            "player_submissions:player-report-detail",
            args=[obj.pk],
        ),
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

    def _include(cat: str) -> bool:
        return categories is None or cat in categories

    feedback_qs: list[PlayerFeedback] = []
    bug_qs: list[BugReport] = []
    report_qs: list[PlayerReport] = []
    application_qs: list[RosterApplication] = []

    if _include(SubmissionCategory.PLAYER_FEEDBACK):
        feedback_qs = list(
            PlayerFeedback.objects.filter(
                status=SubmissionStatus.OPEN,
            ),
        )

    if _include(SubmissionCategory.BUG_REPORT):
        bug_qs = list(
            BugReport.objects.filter(
                status=SubmissionStatus.OPEN,
            ),
        )

    if _include(SubmissionCategory.PLAYER_REPORT):
        report_qs = list(
            PlayerReport.objects.filter(
                status=SubmissionStatus.OPEN,
            ),
        )

    if _include(SubmissionCategory.CHARACTER_APPLICATION):
        application_qs = list(
            RosterApplication.objects.filter(
                status=ApplicationStatus.PENDING,
            ).select_related("character", "player_data__account"),
        )

    persona_ids: set[int] = set()
    for fb in feedback_qs:
        persona_ids.add(fb.reporter_persona_id)
    for br in bug_qs:
        persona_ids.add(br.reporter_persona_id)
    for pr in report_qs:
        persona_ids.add(pr.reporter_persona_id)
        persona_ids.add(pr.reported_persona_id)
    identities = _resolve_identities(list(persona_ids))

    items: list[InboxItem] = []
    items.extend(_feedback_to_item(fb, identities) for fb in feedback_qs)
    items.extend(_bug_to_item(br, identities) for br in bug_qs)
    items.extend(_report_to_item(pr, identities) for pr in report_qs)
    items.extend(_application_to_item(app) for app in application_qs)

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

    Each category is capped at ``MAX_PER_CATEGORY`` items — this endpoint
    is a summary view, not a paginated list. The frontend should link to
    the per-type management ViewSet with a filter for deeper exploration.

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
        ).order_by("-created_at")[:MAX_PER_CATEGORY],
    )

    reports_submitted = list(
        PlayerReport.objects.filter(
            reporter_persona__character_id__in=character_ids,
        ).order_by("-created_at")[:MAX_PER_CATEGORY],
    )

    feedback = list(
        PlayerFeedback.objects.filter(
            reporter_persona__character_id__in=character_ids,
        ).order_by("-created_at")[:MAX_PER_CATEGORY],
    )

    bug_reports = list(
        BugReport.objects.filter(
            reporter_persona__character_id__in=character_ids,
        ).order_by("-created_at")[:MAX_PER_CATEGORY],
    )

    applications = list(
        RosterApplication.objects.filter(
            player_data__account_id=account_id,
        )
        .select_related("character", "player_data__account")
        .order_by("-applied_date")[:MAX_PER_CATEGORY],
    )

    persona_ids: set[int] = set()
    for r in reports_against:
        persona_ids.add(r.reporter_persona_id)
        persona_ids.add(r.reported_persona_id)
    for r in reports_submitted:
        persona_ids.add(r.reporter_persona_id)
        persona_ids.add(r.reported_persona_id)
    for f in feedback:
        persona_ids.add(f.reporter_persona_id)
    for b in bug_reports:
        persona_ids.add(b.reporter_persona_id)
    identities = _resolve_identities(list(persona_ids))

    return {
        "reports_against": [_report_to_item(r, identities) for r in reports_against],
        "reports_submitted": [_report_to_item(r, identities) for r in reports_submitted],
        "feedback": [_feedback_to_item(f, identities) for f in feedback],
        "bug_reports": [_bug_to_item(b, identities) for b in bug_reports],
        "character_applications": [_application_to_item(a) for a in applications],
    }
