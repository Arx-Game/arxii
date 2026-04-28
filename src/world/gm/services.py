"""GM system service functions for tables and memberships."""

from __future__ import annotations

from datetime import datetime, timedelta
import secrets
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from world.gm.constants import GMTableStatus
from world.gm.models import GMProfile, GMRosterInvite, GMTable, GMTableMembership
from world.scenes.constants import PersonaType
from world.scenes.models import Persona

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.roster.models import RosterEntry
    from world.roster.models.applications import RosterApplication
    from world.stories.models import Story

DEFAULT_INVITE_DURATION_DAYS = 30


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
    story.primary_table = None
    story.save(update_fields=["primary_table"])


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
