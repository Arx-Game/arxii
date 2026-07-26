"""Idempotent deploy/test-DB seeds for the roster app (#2483, #2728).

Invoked by the Big Button seeder (``world.seeds.clusters``) — migrations are
ephemeral pre-production and must contain no data seeding (ADR-0013).
"""

from __future__ import annotations

from typing import NamedTuple

from world.roster.models import Roster
from world.roster.models.choices import ActivityRequirement, RosterType


class RosterSeedSpec(NamedTuple):
    """One shelf's seed defaults. Named fields — the three consecutive booleans
    (``is_active``/``is_public``/``allow_applications``) silently transposed when this
    was a bare positional tuple; a NamedTuple makes each spec self-documenting and
    keyword-constructible."""

    name: str
    description: str
    is_active: bool
    is_public: bool
    allow_applications: bool
    activity_requirement: str


_ROSTER_SEED: dict[str, RosterSeedSpec] = {
    RosterType.ACTIVE: RosterSeedSpec(
        name="Active Characters",
        description="Currently played characters.",
        is_active=True,
        is_public=True,
        allow_applications=False,
        activity_requirement=ActivityRequirement.HIGH,
    ),
    RosterType.AVAILABLE: RosterSeedSpec(
        name="Available Characters",
        description="Characters players may apply for.",
        is_active=True,
        is_public=True,
        allow_applications=True,
        activity_requirement=ActivityRequirement.NONE,
    ),
    RosterType.INACTIVE: RosterSeedSpec(
        name="Inactive Characters",
        description="Characters whose player has lapsed.",
        is_active=True,
        is_public=True,
        allow_applications=True,
        activity_requirement=ActivityRequirement.NONE,
    ),
    RosterType.PENDING: RosterSeedSpec(
        name="Pending Characters",
        description="Characters awaiting staff approval.",
        is_active=False,
        is_public=False,
        allow_applications=False,
        activity_requirement=ActivityRequirement.NONE,
    ),
    RosterType.RESTRICTED: RosterSeedSpec(
        name="Restricted Characters",
        description="Characters requiring special approval to play.",
        is_active=True,
        is_public=True,
        allow_applications=True,
        activity_requirement=ActivityRequirement.HIGH,
    ),
    RosterType.FROZEN: RosterSeedSpec(
        name="Frozen Characters",
        description="Characters set aside by their player during an OC swap.",
        is_active=True,
        is_public=False,
        allow_applications=False,
        activity_requirement=ActivityRequirement.NONE,
    ),
    RosterType.NPC: RosterSeedSpec(
        name="NPCs",
        description="Story and standing NPCs. Never claimable, never swept.",
        is_active=True,
        is_public=False,
        allow_applications=False,
        activity_requirement=ActivityRequirement.NONE,
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
        roster, _created = Roster.objects.get_or_create(
            roster_type=roster_type,
            defaults={
                "name": spec.name,
                "description": spec.description,
                "is_active": spec.is_active,
                "is_public": spec.is_public,
                "allow_applications": spec.allow_applications,
                "activity_requirement": spec.activity_requirement,
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
