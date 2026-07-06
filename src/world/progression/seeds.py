"""Idempotent deploy/test-DB seeds for the progression app.

Invoked by `tools/build_schema.py` (and callable at deploy time) in place of
a former RunPython seed migration — migrations are ephemeral pre-production
and must contain no data seeding (ADR-0013).
"""

from __future__ import annotations


def seed_social_engagement_kudos_category() -> None:
    """Seed the social_engagement KudosSourceCategory.

    Used by SceneActionRequest accepts. Fresh deploys need this row to exist
    before any scene-action-accept flow runs. Idempotent via update_or_create.
    """
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    KudosSourceCategory.objects.update_or_create(
        name="social_engagement",
        defaults={
            "display_name": "Social Engagement",
            "description": "Awarded for accepting another character's scene action request.",
            "default_amount": 1,
            "is_active": True,
            "staff_only": False,
        },
    )


def seed_pose_kudos_category() -> None:
    """Seed the pose_kudos KudosSourceCategory (#2026).

    ``world.progression.reaction_kinds._get_pose_kudos_category`` self-heals via
    ``get_or_create`` the first time anyone acclaims a pose, but that means the row
    (and its default_amount) simply doesn't exist until the first acclaim ever
    happens — nothing surfaces it up front (e.g. to admin/game-ops tooling that
    lists categories before any award has fired). Values mirror that helper's
    defaults exactly. Idempotent via update_or_create.
    """
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    KudosSourceCategory.objects.update_or_create(
        name="pose_kudos",
        defaults={
            "display_name": "Pose Kudos",
            "description": "A player acclaimed one of your poses.",
            "default_amount": 1,
            "is_active": True,
            "staff_only": False,
        },
    )


def seed_spread_assist_kudos_category() -> None:
    """Seed the spread_assist KudosSourceCategory (#2026).

    ``world.societies.reaction_kinds._get_spread_assist_kudos_category`` self-heals
    via ``get_or_create`` at scene-close settlement. Values mirror that helper's
    defaults exactly. Idempotent via update_or_create.
    """
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    KudosSourceCategory.objects.update_or_create(
        name="spread_assist",
        defaults={
            "display_name": "Telling Acclaim",
            "description": "You acclaimed a tale someone told, helping it spread.",
            "default_amount": 1,
            "is_active": True,
            "staff_only": False,
        },
    )


def seed_relationship_writeup_kudos_category() -> None:
    """Seed the relationship_writeup KudosSourceCategory (#2026).

    ``world.relationships.services.give_writeup_kudos`` does a plain ``.get()`` on
    this category (no self-heal) — when it's missing, the commendation row is still
    recorded but no kudos are awarded (silent no-op, only a warning log). Name and
    amount must match ``RELATIONSHIP_WRITEUP_KUDOS_CATEGORY`` / ``WRITEUP_KUDOS_AMOUNT``
    in ``world.relationships.constants`` exactly. Idempotent via update_or_create.
    """
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415
    from world.relationships.constants import (  # noqa: PLC0415
        RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
        WRITEUP_KUDOS_AMOUNT,
    )

    KudosSourceCategory.objects.update_or_create(
        name=RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
        defaults={
            "display_name": "Writeup Commended",
            "description": (
                "Another character commended a relationship writeup written about them."
            ),
            "default_amount": WRITEUP_KUDOS_AMOUNT,
            "is_active": True,
            "staff_only": False,
        },
    )


def seed_xp_kudos_claim_category() -> None:
    """Seed the 'xp' KudosClaimCategory — convert kudos to account XP (#2026).

    Without at least one active ``KudosClaimCategory`` row, ``ClaimKudosAction`` /
    ``claim_kudos_for_xp`` have nothing to claim against and the claim UI (web +
    telnet ``kudos``) is dead on a fresh DB. Rate mirrors the shape already
    exercised in ``world.progression.tests.test_kudos``
    (``KudosClaimCategoryFactory(kudos_cost=10, reward_amount=5)``): 10 kudos ->
    5 XP, a meaningful-but-not-trivial conversion given the reaction kinds above
    grant 1 kudos per acclaim. Idempotent via update_or_create.
    """
    from world.progression.models import KudosClaimCategory  # noqa: PLC0415

    KudosClaimCategory.objects.update_or_create(
        name="xp",
        defaults={
            "display_name": "Convert to XP",
            "description": "Convert kudos points to experience points.",
            "kudos_cost": 10,
            "reward_amount": 5,
            "is_active": True,
        },
    )


def seed_kudos_content() -> None:
    """Seed every kudos source/claim category the kudos economy needs (#2026).

    Without this, ``grant_social_engagement_kudos`` (weekly good-sport grant) and
    ``give_writeup_kudos`` (relationship-writeup commend) both silently no-op on a
    fresh DB — their category lookups raise ``DoesNotExist``, caught and logged as
    a warning rather than awarding anything — and the kudos-claim UI has no
    ``KudosClaimCategory`` to offer. Registered as the "kudos" cluster in
    ``world.seeds.clusters``.
    """
    seed_social_engagement_kudos_category()
    seed_pose_kudos_category()
    seed_spread_assist_kudos_category()
    seed_relationship_writeup_kudos_category()
    seed_xp_kudos_claim_category()
