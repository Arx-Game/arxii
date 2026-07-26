"""Idempotent deploy/test-DB seeds for the roster app (#2483, #2728).

Invoked by the Big Button seeder (``world.seeds.clusters``) — migrations are
ephemeral pre-production and must contain no data seeding (ADR-0013).
"""

from __future__ import annotations

from world.roster.models import Roster
from world.roster.models.choices import ActivityRequirement, RosterType

# roster_type -> (display name, description, is_active, is_public,
#                 allow_applications, activity_requirement)
_ROSTER_SEED: dict[str, tuple[str, str, bool, bool, bool, str]] = {
    RosterType.ACTIVE: (
        "Active Characters",
        "Currently played characters.",
        True,
        True,
        False,
        ActivityRequirement.HIGH,
    ),
    RosterType.AVAILABLE: (
        "Available Characters",
        "Characters players may apply for.",
        True,
        True,
        True,
        ActivityRequirement.NONE,
    ),
    RosterType.INACTIVE: (
        "Inactive Characters",
        "Characters whose player has lapsed.",
        True,
        True,
        True,
        ActivityRequirement.NONE,
    ),
    RosterType.PENDING: (
        "Pending Characters",
        "Characters awaiting staff approval.",
        False,
        False,
        False,
        ActivityRequirement.NONE,
    ),
    RosterType.RESTRICTED: (
        "Restricted Characters",
        "Characters requiring special approval to play.",
        True,
        True,
        True,
        ActivityRequirement.HIGH,
    ),
    RosterType.FROZEN: (
        "Frozen Characters",
        "Characters set aside by their player during an OC swap.",
        True,
        False,
        False,
        ActivityRequirement.NONE,
    ),
    RosterType.NPC: (
        "NPCs",
        "Story and standing NPCs. Never claimable, never swept.",
        True,
        False,
        False,
        ActivityRequirement.NONE,
    ),
}


def ensure_rosters() -> dict[str, Roster]:
    """Create every roster shelf exactly once. Idempotent.

    Two seed paths previously created "Active"/"Available" and "Active
    Characters"/"Available Characters" as separate rows, while Inactive,
    Frozen and Restricted were never created at all. This is the single
    source (#2728).

    Returns a mapping of ``RosterType`` value to ``Roster``.
    """
    rosters: dict[str, Roster] = {}
    for roster_type, spec in _ROSTER_SEED.items():
        name, description, is_active, is_public, allow_applications, requirement = spec
        roster, _created = Roster.objects.get_or_create(
            roster_type=roster_type,
            defaults={
                "name": name,
                "description": description,
                "is_active": is_active,
                "is_public": is_public,
                "allow_applications": allow_applications,
                "activity_requirement": requirement,
            },
        )
        rosters[roster_type] = roster
    return rosters


def seed_invite_trust_category() -> None:
    """Seed the INVITE TrustCategory for game invite eligibility (#2483).

    ``world.roster.services.invite_services._inviter_meets_trust_threshold``
    looks up this category by name ("INVITE") with a BASIC minimum level.
    Without this row, every invite-creation attempt raises PermissionError
    (the category lookup returns UNTRUSTED when absent). Idempotent via
    ``update_or_create``.
    """
    from world.stories.models import TrustCategory  # noqa: PLC0415

    TrustCategory.objects.update_or_create(
        name="INVITE",
        defaults={
            "display_name": "Game Invites",
            "description": "Can send game invites to friends",
            "is_active": True,
        },
    )
