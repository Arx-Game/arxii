"""Idempotent deploy/test-DB seeds for the roster app (#2483).

Invoked by the Big Button seeder (``world.seeds.clusters``) — migrations are
ephemeral pre-production and must contain no data seeding (ADR-0013).
"""

from __future__ import annotations


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
