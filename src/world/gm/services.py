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

    from world.roster.models import RosterEntry
    from world.roster.models.applications import RosterApplication
    from world.stories.models import Story

DEFAULT_INVITE_DURATION_DAYS = 30

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
    """Soft-leave a membership. No-op if already left."""
    if membership.left_at is not None:
        return
    membership.left_at = timezone.now()
    membership.save(update_fields=["left_at"])


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
        )
        .select_related("character", "player_data__account")
        .distinct()
    )


@transaction.atomic
def approve_application_as_gm(gm: GMProfile, application: RosterApplication) -> None:
    """Approve a roster application on behalf of the overseeing GM.

    Verifies the application is in this GM's queue (i.e. GM owns a table
    hosting a story the applied-for character participates in). Then
    delegates to RosterApplication.approve().
    """
    queue = gm_application_queue(gm)
    if not queue.filter(pk=application.pk).exists():
        msg = "This application is not in your GM application queue."
        raise ValidationError(msg)
    application.approve(staff_player_data=gm.account.player_data)


@transaction.atomic
def deny_application_as_gm(
    gm: GMProfile,
    application: RosterApplication,
    review_notes: str = "",
) -> None:
    """Deny an application in the GM's queue."""
    queue = gm_application_queue(gm)
    if not queue.filter(pk=application.pk).exists():
        msg = "This application is not in your GM application queue."
        raise ValidationError(msg)
    application.deny(staff_player_data=gm.account.player_data, reason=review_notes)


@transaction.atomic
def surrender_character_story(gm: GMProfile, story: Story) -> None:
    """GM surrenders oversight of a story.

    Clears primary_table so the story becomes orphaned (character falls
    out of default visibility until another GM picks up oversight).
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
    """Create a GMRosterInvite for a roster character.

    Validates that the GM oversees the roster_entry (character has an
    active story at one of this GM's tables). Private invites should
    have invited_email set; public invites accept anyone with the code.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415

    # Verify GM oversees this entry
    oversees = RosterEntry.objects.filter(
        pk=roster_entry.pk,
        character_sheet__character__story_participations__is_active=True,
        character_sheet__character__story_participations__story__primary_table__gm=gm,
    ).exists()
    if not oversees:
        msg = "You do not oversee this character."
        raise ValidationError(msg)

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
def revoke_invite(gm: GMProfile, invite: GMRosterInvite) -> None:
    """Revoke an unclaimed invite by setting expires_at to now.

    Only the GM who created the invite can revoke it. Claimed invites
    cannot be revoked (too late).
    """
    if invite.created_by != gm:
        msg = "You did not create this invite."
        raise ValidationError(msg)
    if invite.is_claimed:
        msg = "Claimed invites cannot be revoked."
        raise ValidationError(msg)
    invite.expires_at = timezone.now()
    invite.save(update_fields=["expires_at"])


@transaction.atomic
def claim_invite(code: str, account: AccountDB) -> RosterApplication:
    """Claim a GM invite, creating a RosterApplication for the account.

    Validates:
    - Invite exists (code found)
    - Not already claimed
    - Not expired
    - Email matches for private invites (invited_email set)

    Marks the invite as claimed atomically. Creates a PlayerData for
    the account if none exists. Returns the new RosterApplication.
    """
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.gm.models import GMRosterInvite  # noqa: PLC0415
    from world.roster.models.applications import RosterApplication  # noqa: PLC0415

    try:
        invite = GMRosterInvite.objects.select_for_update().get(code=code)
    except GMRosterInvite.DoesNotExist as exc:
        msg = "Invalid invite code."
        raise ValidationError(msg) from exc

    if invite.is_claimed:
        msg = "This invite has already been claimed."
        raise ValidationError(msg)
    if invite.is_expired:
        msg = "This invite has expired."
        raise ValidationError(msg)

    if not invite.is_public and invite.invited_email:
        if not account.email or invite.invited_email.lower() != account.email.lower():
            msg = "This invite is private and does not match your account email."
            raise ValidationError(msg)

    # Mark claimed
    invite.claimed_at = timezone.now()
    invite.claimed_by = account
    invite.save(update_fields=["claimed_at", "claimed_by"])

    # Get or create the PlayerData record
    player_data, _ = PlayerData.objects.get_or_create(account=account)

    # Create the application
    return RosterApplication.objects.create(
        player_data=player_data,
        character=invite.roster_entry.character_sheet.character,
        application_text=f"Claiming invite from {invite.created_by.account.username}",
    )
