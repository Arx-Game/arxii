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
