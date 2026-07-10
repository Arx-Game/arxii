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

from world.gm.constants import GMLevel, GMTableStatus
from world.gm.models import (
    GMLevelChange,
    GMProfile,
    GMRewardConfig,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
    GMWeeklyRewardTracker,
)
from world.gm.types import CategoryFeedback, GMEvidenceSummary
from world.scenes.constants import PersonaType
from world.scenes.models import Persona

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
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
    return GMTableMembership.objects.create(table=table, persona=persona)


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
