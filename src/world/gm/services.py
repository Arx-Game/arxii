"""GM system service functions for tables and memberships."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import secrets
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from world.gm.constants import (
    GMLevel,
    GMTableStatus,
    TableRequestKind,
    TableRequestStatus,
)
from world.gm.models import (
    CatalogSuggestion,
    GMLevelChange,
    GMProfile,
    GMRewardConfig,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
    GMWeeklyRewardTracker,
    SituationKind,
)
from world.gm.types import CategoryFeedback, GMEvidenceSummary
from world.scenes.constants import PersonaType
from world.scenes.models import Persona

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.accounts.models import AccountDB

    from evennia_extensions.models import PlayerData
    from world.character_sheets.models import CharacterSheet
    from world.distinctions.models import CharacterDistinction, Distinction
    from world.gm.models import TableUpdateRequest
    from world.progression.models import XPTransaction
    from world.roster.models import RosterEntry
    from world.roster.models.applications import RosterApplication
    from world.stories.models import Story

DEFAULT_INVITE_DURATION_DAYS = 30

logger = logging.getLogger(__name__)


def touch_gm_activity(gm_profile: GMProfile) -> None:
    """Stamp ``GMProfile.last_active_at`` to now (#2004).

    Single seam (no signal, ADR-0009) called from every GM-verb service so a
    GM's activity is tracked for idle-table detection. Idempotent and cheap
    (one ``update_fields`` write); safe to call repeatedly.
    """
    gm_profile.last_active_at = timezone.now()
    gm_profile.save(update_fields=["last_active_at"])


def get_notification_target_for_gm(gm_profile: GMProfile) -> CharacterSheet | None:
    """Resolve the CharacterSheet to use as the notification recipient for a GM.

    Walks GMProfile -> account -> primary ObjectDB character -> CharacterSheet
    (via the sheet_data OneToOne reverse relation) -> primary_persona's character_sheet.

    Returns None if the GM's account has no character with a CharacterSheet, so
    callers can skip the notification gracefully.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.scenes.constants import PersonaType as _PersonaType  # noqa: PLC0415

    account = gm_profile.account
    # Find a character owned by this account that has a sheet with a PRIMARY persona.
    # We take the first match — GMs are expected to have at least one played character.
    return (
        CharacterSheet.objects.filter(
            character__db_account=account,
            personas__persona_type=_PersonaType.PRIMARY,
        )
        .select_related("character")
        .first()
    )


TEMPORARY_PERSONA_REJECTION = (
    "A temporary persona cannot join a GM table — use a primary or established persona."
)


@transaction.atomic
def create_table(gm: GMProfile, name: str, description: str = "") -> GMTable:
    """Create a new GM table owned by the given GM."""
    return GMTable.objects.create(gm=gm, name=name, description=description)


@transaction.atomic
def archive_table(table: GMTable) -> None:
    """Mark a table archived. Sets archived_at timestamp."""
    # TODO: Archiving a table leaves PENDING applications for characters at
    # this table invisible to the GM queue (filtered out by status=ACTIVE).
    # Those applications become orphaned PENDING rows. A follow-up should
    # either auto-deny them with a "table archived" reason or route them to
    # a staff override queue.
    if table.status == GMTableStatus.ARCHIVED:
        return
    table.status = GMTableStatus.ARCHIVED
    table.archived_at = timezone.now()
    table.save(update_fields=["status", "archived_at"])


@transaction.atomic
def transfer_ownership(table: GMTable, new_gm: GMProfile) -> None:
    """Reassign a table to a different GM. Staff-only action."""
    table.gm = new_gm
    table.save(update_fields=["gm"])


# Staff-tunable threshold (days) for idle-table detection (#2004).
# A GMTable whose GM's last_active_at is older than this is "idle".
IDLE_TABLE_THRESHOLD_DAYS = 14


def idle_tables(threshold_days: int = IDLE_TABLE_THRESHOLD_DAYS) -> QuerySet[GMTable]:
    """ACTIVE tables whose GM's ``last_active_at`` is older than the threshold (#2004).

    Returns tables whose GM has never been active (``last_active_at IS NULL``)
    or whose last activity predates the cutoff. Used by the StaffWorkloadView
    idle-tables section and the weekly cron summary.
    """
    cutoff = timezone.now() - timedelta(days=threshold_days)
    return (
        GMTable.objects.filter(status=GMTableStatus.ACTIVE)
        .select_related("gm__account")
        .filter(Q(gm__last_active_at__lt=cutoff) | Q(gm__last_active_at__isnull=True))
    )


@transaction.atomic
def join_table(table: GMTable, persona: Persona) -> GMTableMembership:
    """Add a persona to a table. Idempotent — returns existing active
    membership if one exists. Rejects TEMPORARY personas.
    """
    if persona.persona_type == PersonaType.TEMPORARY:
        raise ValidationError(TEMPORARY_PERSONA_REJECTION)
    existing = GMTableMembership.objects.filter(
        table=table,
        persona=persona,
        left_at__isnull=True,
    ).first()
    if existing:
        return existing
    membership = GMTableMembership.objects.create(table=table, persona=persona)
    # Auto-clear looking-for-table flag when a player joins a table (#2431)
    _clear_looking_for_table_on_join(persona)
    return membership


def _clear_looking_for_table_on_join(persona: Persona) -> None:
    """Clear the looking-for-table flag for the persona's player (#2431).

    Walks persona → character_sheet → roster_entry → current_tenure → player_data.
    No-op if any link is missing or the flag is already False.
    """
    try:
        sheet = persona.character_sheet
        if sheet is None:
            return
        roster_entry = sheet.roster_entry
    except Exception:  # noqa: BLE001 — RelatedObjectDoesNotExist or AttributeError
        return
    if roster_entry is None:
        return
    tenure = roster_entry.current_tenure
    if tenure is None:
        return
    player_data = tenure.player_data
    if player_data is None or not player_data.looking_for_table:
        return
    set_looking_for_table(player_data, looking=False)


def set_looking_for_table(player_data: PlayerData, looking: bool) -> None:
    """Set or clear the looking-for-table flag on a player's profile (#2431).

    When setting, stamps ``looking_for_table_set_at`` for GM browse sorting.
    When clearing, nulls the timestamp.
    """
    player_data.looking_for_table = looking
    player_data.looking_for_table_set_at = timezone.now() if looking else None
    player_data.save(update_fields=["looking_for_table", "looking_for_table_set_at"])


@transaction.atomic
def leave_table(membership: GMTableMembership) -> None:
    """Soft-leave a membership. No-op if already left.

    Side effects:
    - GMTableMembership.left_at set to now (deactivates the membership).
    - Any CHARACTER-scope Story owned by this persona's character_sheet whose
      primary_table matches the leaving table is detached (primary_table=None).
      Story history and participations are preserved; the story enters
      'seeking GM' state.
    - GROUP-scope stories at the table are not affected — those stories belong
      to the table, not to the individual member.
    """
    if membership.left_at is not None:
        return
    membership.left_at = timezone.now()
    membership.save(update_fields=["left_at"])

    # Auto-detach CHARACTER-scope stories owned by this persona's character.
    # Imported inside the function to avoid circular imports between gm and stories.
    from world.stories.constants import StoryScope  # noqa: PLC0415
    from world.stories.models import Story  # noqa: PLC0415
    from world.stories.services.tables import detach_story_from_table  # noqa: PLC0415

    sheet = membership.persona.character_sheet
    stories_to_detach = Story.objects.filter(
        scope=StoryScope.CHARACTER,
        character_sheet=sheet,
        primary_table=membership.table,
    )
    for story in stories_to_detach:
        detach_story_from_table(story=story)


@transaction.atomic
def soft_leave_memberships_for_retired_persona(persona: Persona) -> int:
    """Future integration hook: called when a persona is retired.

    TODO: No production caller wired yet. When the persona retirement
    flow is implemented (likely as a service in world.scenes), it must
    call this to soft-leave any active table memberships. Without this,
    retired personas will retain active GM table memberships.

    Sets left_at on all active memberships for that persona. Returns
    the count of memberships closed.
    """
    now = timezone.now()
    count = 0
    for m in GMTableMembership.objects.filter(persona=persona, left_at__isnull=True):
        m.left_at = now
        m.save(update_fields=["left_at"])
        count += 1
    return count


def gm_application_queue(gm: GMProfile) -> QuerySet[RosterApplication]:
    """Pending applications for characters at tables this GM owns.

    Derived from: application.character → story_participations → story.primary_table.gm
    Only pending applications are included.
    """
    from world.roster.models.applications import RosterApplication  # noqa: PLC0415
    from world.roster.models.choices import ApplicationStatus  # noqa: PLC0415

    return (
        RosterApplication.objects.filter(
            status=ApplicationStatus.PENDING,
            character__story_participations__is_active=True,
            character__story_participations__story__primary_table__gm=gm,
            character__story_participations__story__primary_table__status=(GMTableStatus.ACTIVE),
        )
        .select_related("character", "player_data__account")
        .distinct()
    )


@transaction.atomic
def approve_application_as_gm(gm: GMProfile, application: RosterApplication) -> None:
    """Approve a roster application on behalf of the overseeing GM.

    Caller (serializer) must validate queue membership and PENDING status.
    """
    application.approve(staff_player_data=gm.account.player_data)


@transaction.atomic
def deny_application_as_gm(
    gm: GMProfile,
    application: RosterApplication,
    review_notes: str = "",
) -> None:
    """Deny an application on behalf of the overseeing GM.

    Caller (serializer) must validate queue membership and PENDING status.
    """
    application.deny(staff_player_data=gm.account.player_data, reason=review_notes)


@transaction.atomic
def surrender_character_story(gm: GMProfile, story: Story) -> None:
    """GM surrenders oversight of a story.

    Clears the Story's ``primary_table`` so the story becomes orphaned.

    Semantics:
    - The Story's ``primary_table`` is set to None.
    - Existing ``StoryParticipation`` records remain ACTIVE — the character
      is still in the story, there's simply no one overseeing it.
    - ``actively_overseen()`` will exclude the character from default
      visibility until oversight is re-established.
    - There is currently no "pick up orphan story" service. Staff or
      another GM must manually set ``primary_table`` again (tracked as
      follow-up work).

    Validation lives here because no API endpoint/serializer exists yet.
    When an endpoint is added, move the oversight check into the serializer.
    """
    if story.primary_table is None or story.primary_table.gm != gm:
        msg = "You do not oversee this story."
        raise ValidationError(msg)
    touch_gm_activity(gm)
    story.primary_table = None
    story.save(update_fields=["primary_table"])
    _notify_surrender(story, gm)


def _notify_surrender(story: Story, gm: GMProfile) -> None:
    """Best-effort narrative SYSTEM message to the affected player (#2004).

    Notifies the story's character_sheet owner that their GM has surrendered
    oversight. Skips gracefully when no character_sheet is resolvable (GROUP/
    GLOBAL stories have no single affected player).
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    character_sheet = story.character_sheet
    if character_sheet is None:
        return
    try:
        send_narrative_message(
            recipients=[character_sheet],
            body=(
                f"Your GM has surrendered oversight of your story "
                f"'{story.title}'. It is now seeking a new GM."
            ),
            category=NarrativeCategory.SYSTEM,
            sender_account=gm.account,
            related_story=story,
        )
    except Exception:
        import logging  # noqa: PLC0415

        logging.getLogger(__name__).exception("surrender notification failed")


@transaction.atomic
def create_invite(
    gm: GMProfile,
    roster_entry: RosterEntry,
    is_public: bool = False,
    invited_email: str = "",
    expires_at: datetime | None = None,
) -> GMRosterInvite:
    """Create a GMRosterInvite. Callers must validate GM oversight."""
    if expires_at is None:
        expires_at = timezone.now() + timedelta(days=DEFAULT_INVITE_DURATION_DAYS)
    return GMRosterInvite.objects.create(
        roster_entry=roster_entry,
        created_by=gm,
        code=secrets.token_urlsafe(48),
        expires_at=expires_at,
        is_public=is_public,
        invited_email=invited_email,
    )


@transaction.atomic
def revoke_invite(invite: GMRosterInvite) -> None:
    """Revoke an invite by setting expires_at to now.

    Caller must validate that the invite is revocable (not claimed) and
    that the requester is authorized.
    """
    invite.expires_at = timezone.now()
    invite.save(update_fields=["expires_at"])


@transaction.atomic
def claim_invite(invite: GMRosterInvite, account: AccountDB) -> RosterApplication:
    """Mark an invite claimed and create (or reuse) a RosterApplication.

    Caller must validate invite usability (existence, not claimed, not
    expired, email match for private invites). Reuses a PENDING
    application for the same (player_data, character) if one exists,
    annotating its text with a claim note; never reuses a finalized
    application — the caller must validate that case too if they care.
    """
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.roster.models.applications import RosterApplication  # noqa: PLC0415

    invite.claimed_at = timezone.now()
    invite.claimed_by = account
    invite.save(update_fields=["claimed_at", "claimed_by"])

    player_data, _ = PlayerData.objects.get_or_create(account=account)
    character = invite.roster_entry.character_sheet.character

    # Use get_or_create to race-safely handle duplicate applications —
    # RosterApplication has unique_together on (player_data, character).
    app, created = RosterApplication.objects.get_or_create(
        player_data=player_data,
        character=character,
        defaults={
            "application_text": f"Claiming invite from {invite.created_by.account.username}",
        },
    )
    if not created:
        app.application_text = (
            app.application_text or ""
        ) + f"\n[Claimed invite from {invite.created_by.account.username}]"
        app.save(update_fields=["application_text"])
    return app


@transaction.atomic
def promote_gm(
    profile: GMProfile,
    new_level: str,
    *,
    changed_by: AccountDB,
    reason: str,
) -> GMLevelChange:
    """Set profile.level (promotion OR demotion), writing the audit row.

    Programmer-error guards only (validation lives in the serializer):
    raises ValueError if new_level == profile.level or new_level not in
    GMLevel.values.
    """
    if new_level not in GMLevel.values:
        msg = f"{new_level!r} is not a valid GMLevel; expected one of {GMLevel.values}."
        raise ValueError(msg)
    if new_level == profile.level:
        msg = f"profile is already at level {new_level!r}; promote_gm requires a level change."
        raise ValueError(msg)

    old_level = profile.level
    profile.level = new_level
    profile.save(update_fields=["level", "updated_at"])

    return GMLevelChange.objects.create(
        profile=profile,
        old_level=old_level,
        new_level=new_level,
        changed_by=changed_by,
        reason=reason,
    )


def gm_evidence_summary(profile: GMProfile) -> GMEvidenceSummary:
    """Aggregate a GM's track record for staff reviewing a level change.

    Each aggregate below is a single ORM query (no queries in loops).
    Imported lazily to avoid a top-level gm -> stories dependency.
    """
    from django.db.models import Avg, Count  # noqa: PLC0415

    from world.stories.models import (  # noqa: PLC0415
        BeatCompletion,
        Story,
        TrustCategoryFeedbackRating,
    )
    from world.stories.types import StoryStatus  # noqa: PLC0415

    stories_running = Story.objects.filter(
        primary_table__gm=profile,
        primary_table__status=GMTableStatus.ACTIVE,
        status=StoryStatus.ACTIVE,
    ).count()

    beats_completed_by_risk = {
        row["beat__risk"]: row["n"]
        for row in (
            BeatCompletion.objects.filter(
                beat__episode__chapter__story__primary_table__gm=profile,
            )
            .values("beat__risk")
            .annotate(n=Count("id"))
        )
    }

    feedback_by_category = [
        CategoryFeedback(
            category_name=row["trust_category__name"],
            average_rating=row["avg"],
            rating_count=row["n"],
        )
        for row in (
            TrustCategoryFeedbackRating.objects.filter(
                feedback__story__primary_table__gm=profile,
            )
            .values("trust_category__name")
            .annotate(avg=Avg("rating"), n=Count("id"))
        )
    ]

    return GMEvidenceSummary(
        profile_id=profile.pk,
        level=profile.level,
        approved_at=profile.approved_at,
        last_active_at=profile.last_active_at,
        stories_running=stories_running,
        beats_completed_by_risk=beats_completed_by_risk,
        feedback_by_category=feedback_by_category,
        level_changes=list(profile.level_changes.select_related("changed_by").all()[:20]),
    )


def submit_catalog_suggestion(
    account: AccountDB,
    *,
    proposal_kind: str,
    proposal_text: str,
    situation_kind: SituationKind | None = None,
) -> CatalogSuggestion:
    """Create a ``CatalogSuggestion`` row, routed to the staff inbox (#2127).

    Pure creation -- no live catalog row is ever touched here (Decision 7/8).
    Staff accepts a suggestion by hand-authoring the real catalog row(s)
    separately (e.g. in admin); this function never does that itself.
    """
    return CatalogSuggestion.objects.create(
        submitted_by=account,
        situation_kind=situation_kind,
        proposal_kind=proposal_kind,
        proposal_text=proposal_text,
    )


def _get_or_reset_weekly_reward_tracker(gm_profile: GMProfile) -> GMWeeklyRewardTracker:
    """Get this GM's weekly reward tracker, resetting it if the game week has changed.

    Mirrors ``world.journals.services._get_or_reset_weekly_tracker``. Must be
    called inside an open transaction — uses ``select_for_update()``.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    current_week = get_current_game_week()
    tracker, created = GMWeeklyRewardTracker.objects.select_for_update().get_or_create(
        gm_profile=gm_profile,
        defaults={"game_week": current_week},
    )
    if not created and tracker.needs_reset(current_week):
        tracker.reset_week(current_week)
    return tracker


def _do_award_gm_story_reward(
    *,
    gm_profile: GMProfile,
    players_served: int,
    per_player_xp: int,
    event_cap: int,
    description: str,
) -> XPTransaction | None:
    """Compute and grant the weekly-capped GM Story Reward award (#2123).

    ``raw = min(per_player_xp * players_served, event_cap)`` — the event's own
    cap. That amount is then further truncated by whatever headroom remains
    under ``GMRewardConfig.weekly_reward_cap`` for this GM this game week.
    Returns ``None`` (a no-op, not an error) when there's nothing to award —
    zero/negative players_served or per_player_xp, or the weekly cap is
    already exhausted.
    """
    if players_served <= 0 or per_player_xp <= 0:
        return None
    raw = min(per_player_xp * players_served, event_cap)
    if raw <= 0:
        return None

    from world.progression.services.awards import award_xp  # noqa: PLC0415
    from world.progression.types import ProgressionReason  # noqa: PLC0415

    config = GMRewardConfig.load()
    with transaction.atomic():
        tracker = _get_or_reset_weekly_reward_tracker(gm_profile)
        remaining = config.weekly_reward_cap - tracker.xp_awarded_this_week
        amount = min(raw, remaining)
        if amount <= 0:
            logger.info(
                "GM weekly reward cap reached for gm_profile=%s; award skipped.",
                gm_profile.pk,
            )
            return None

        transaction_row = award_xp(
            account=gm_profile.account,
            amount=amount,
            reason=ProgressionReason.GM_STORY_REWARD,
            description=description,
        )
        tracker.xp_awarded_this_week += amount
        tracker.save(update_fields=["xp_awarded_this_week"])

    return transaction_row


def award_gm_story_reward(
    *,
    gm_profile: GMProfile,
    players_served: int,
    per_player_xp: int,
    event_cap: int,
    description: str,
) -> XPTransaction | None:
    """Award GM Story Reward XP to ``gm_profile.account`` (#2123).

    The single choke point every award convergence point calls: a GM-marked
    beat, a resolved episode, a completed story, and a positive story-feedback
    rating all route through here. Reads ``GMRewardConfig`` for the weekly
    ceiling; per-player-xp/event_cap are passed by the caller (already sourced
    from the same config row for the specific event kind).

    Failure isolation: never raises. A bug here must never abort the host
    operation (beat marking, episode resolution, story completion, feedback
    submission) that triggered the award — mirrors the log-and-continue
    pattern already used by ``_notify_surrender`` in this module.
    """
    try:
        return _do_award_gm_story_reward(
            gm_profile=gm_profile,
            players_served=players_served,
            per_player_xp=per_player_xp,
            event_cap=event_cap,
            description=description,
        )
    except Exception:
        logger.exception(
            "award_gm_story_reward failed for gm_profile=%s; award skipped.",
            gm_profile.pk,
        )
        return None


# ---------------------------------------------------------------------------
# Table update requests (#2631) — player proposes, GM vetoes, nobody authors.
# ---------------------------------------------------------------------------


class TableRequestError(Exception):
    """A table update request operation was invalid.

    ``user_message`` is safe to surface to the player/GM.
    """

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.user_message = msg


def _notify_sheet(sheet: CharacterSheet, body: str, sender: AccountDB | None = None) -> None:
    """Send a narrative message to one character sheet."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    send_narrative_message(
        recipients=[sheet],
        body=body,
        category=NarrativeCategory.ABILITY,
        sender_account=sender,
    )


def _require_active_membership(membership: GMTableMembership) -> None:
    if membership.left_at is not None:
        msg = "That table membership has ended — rejoin a table to submit updates."
        raise TableRequestError(msg)


def submit_profile_text_request(
    membership: GMTableMembership,
    *,
    field: str,
    proposed_text: str,
    reasoning: str,
) -> TableUpdateRequest:
    """Submit a profile prose rewrite for the table GM's sign-off (#2631).

    Args:
        membership: The player's active table membership.
        field: A ``character_sheets.ProfileTextField`` value.
        proposed_text: The full replacement text (player-written).
        reasoning: The player's Reason: text.

    Returns:
        The PENDING request.
    """
    from world.character_sheets.types import ProfileTextField  # noqa: PLC0415
    from world.gm.models import ProfileTextRequestDetails, TableUpdateRequest  # noqa: PLC0415

    _require_active_membership(membership)
    if field not in ProfileTextField.values:
        msg = f"{field!r} is not an updatable profile field."
        raise TableRequestError(msg)
    if not proposed_text.strip() or not reasoning.strip():
        msg = "Both the new text and a reason are required."
        raise TableRequestError(msg)

    with transaction.atomic():
        request = TableUpdateRequest.objects.create(
            membership=membership,
            kind=TableRequestKind.PROFILE_TEXT,
            player_reasoning=reasoning,
        )
        ProfileTextRequestDetails.objects.create(
            request=request,
            field=field,
            proposed_text=proposed_text,
        )
    return request


def submit_distinction_change_request(  # noqa: PLR0913
    membership: GMTableMembership,
    *,
    action: str,
    reasoning: str,
    distinction: Distinction | None = None,
    character_distinction: CharacterDistinction | None = None,
    rank: int = 1,
) -> TableUpdateRequest:
    """Submit a distinction add/rank-up/remove for the table GM's sign-off (#2631).

    Args:
        membership: The player's active table membership.
        action: A ``DistinctionChangeAction`` value.
        reasoning: The player's Reason: text.
        distinction: For ADD — the catalog distinction.
        character_distinction: For REMOVE — the held row (must belong to the
            membership's character).
        rank: Target rank for ADD (absolute).

    Returns:
        The PENDING request.
    """
    from world.gm.models import (  # noqa: PLC0415
        DistinctionChangeRequestDetails,
        TableUpdateRequest,
    )

    _require_active_membership(membership)
    if not reasoning.strip():
        msg = "A reason is required."
        raise TableRequestError(msg)
    sheet = membership.persona.character_sheet
    if character_distinction is not None and character_distinction.character_id != sheet.pk:
        msg = "That distinction belongs to a different character."
        raise TableRequestError(msg)

    with transaction.atomic():
        request = TableUpdateRequest.objects.create(
            membership=membership,
            kind=TableRequestKind.DISTINCTION_CHANGE,
            player_reasoning=reasoning,
        )
        details = DistinctionChangeRequestDetails(
            request=request,
            action=action,
            distinction=distinction,
            character_distinction=character_distinction,
            rank=rank,
        )
        details.full_clean()
        details.save()
    return request


def withdraw_table_update_request(request: TableUpdateRequest) -> None:
    """Withdraw a PENDING request (player-initiated)."""
    if request.status != TableRequestStatus.PENDING:
        msg = "Only a pending request can be withdrawn."
        raise TableRequestError(msg)
    request.status = TableRequestStatus.WITHDRAWN
    request.resolved_at = timezone.now()
    request.save(update_fields=["status", "resolved_at"])


def signoff_table_update_request(
    request: TableUpdateRequest,
    gm_profile: GMProfile,
    *,
    approve: bool,
    notes: str = "",
) -> TableUpdateRequest:
    """Approve or reject a PENDING request — the GM's yes/no judgment call (#2631).

    Only the table's GM (or staff via their own GMProfile) may sign off.
    Rejection notifies the player with the notes. Approval branches by kind:

    - PROFILE_TEXT: applies the rewrite immediately through
      ``update_profile_text`` (zero cost — nothing to accept) → COMPLETED.
    - DISTINCTION_CHANGE: creates a ``DistinctionChangeAuthorization`` (which
      notifies the player) → APPROVED; the player accepts to spend and apply.

    Returns:
        The updated request.
    """
    from world.character_sheets.services import update_profile_text  # noqa: PLC0415
    from world.distinctions.services import (  # noqa: PLC0415
        create_distinction_change_authorization,
    )

    is_table_gm = request.membership.table.gm_id == gm_profile.pk
    if not is_table_gm and not gm_profile.account.is_staff:
        msg = "Only the table's GM may sign off on this request."
        raise TableRequestError(msg)
    if request.status != TableRequestStatus.PENDING:
        msg = "This request has already been resolved."
        raise TableRequestError(msg)

    sheet = request.membership.persona.character_sheet
    now = timezone.now()

    if not approve:
        request.status = TableRequestStatus.REJECTED
        request.gm_notes = notes
        request.resolved_by = gm_profile
        request.resolved_at = now
        request.save(update_fields=["status", "gm_notes", "resolved_by", "resolved_at"])
        note_suffix = f" Notes: {notes}" if notes else ""
        _notify_sheet(
            sheet,
            f"Your {request.get_kind_display()} update request was declined.{note_suffix}",
            sender=gm_profile.account,
        )
        return request

    with transaction.atomic():
        if request.kind == TableRequestKind.PROFILE_TEXT:
            details = request.profile_text_details
            version = update_profile_text(
                sheet.true_profile,
                details.field,
                details.proposed_text,
            )
            details.applied_version = version
            details.save(update_fields=["applied_version"])
            request.status = TableRequestStatus.COMPLETED
            request.completed_at = now
        else:
            details = request.distinction_details
            auth = create_distinction_change_authorization(
                sheet,
                action=details.action,
                distinction=details.distinction,
                character_distinction=details.character_distinction,
                authorized_by=gm_profile.account,
                reason=request.player_reasoning,
                rank=details.rank,
            )
            details.authorization = auth
            details.save(update_fields=["authorization"])
            request.status = TableRequestStatus.APPROVED
        request.gm_notes = notes
        request.resolved_by = gm_profile
        request.resolved_at = now
        request.save(
            update_fields=["status", "gm_notes", "resolved_by", "resolved_at", "completed_at"]
        )

    if request.kind == TableRequestKind.PROFILE_TEXT:
        _notify_sheet(
            sheet,
            f"Your {request.get_kind_display()} update was approved and applied.",
            sender=gm_profile.account,
        )
    return request


def mark_requests_completed_for_authorization(authorization: object) -> int:
    """Flip APPROVED requests linked to a consumed authorization to COMPLETED.

    Called by the accept action after ``spend_xp_on_distinction_unlock``
    succeeds — the explicit, no-signals completion sync (ADR-0009).

    Returns:
        The number of requests completed.
    """
    from world.gm.models import TableUpdateRequest  # noqa: PLC0415

    now = timezone.now()
    requests = TableUpdateRequest.objects.filter(
        status=TableRequestStatus.APPROVED,
        distinction_details__authorization=authorization,
    )
    count = 0
    for request in requests:
        # Instance saves, not queryset.update() — bulk update would leave the
        # SharedMemoryModel identity-map instances stale.
        request.status = TableRequestStatus.COMPLETED
        request.completed_at = now
        request.save(update_fields=["status", "completed_at"])
        count += 1
    return count
