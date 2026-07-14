"""Seed content for the areas app (#1889)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ensure_cleanup_content() -> None:
    """Seed CLEANUP project kind content.

    Creates resonance award, contribution methods, and celestial resonance.
    Idempotent — safe to call multiple times.
    """
    from world.magic.models.affinity import Affinity, Resonance  # noqa: PLC0415
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.models import (  # noqa: PLC0415
        ContributionMethod,
        ProjectKindResonanceAward,
    )

    # Celestial resonance for the project FK (self-contained, get-or-create).
    celestial, _ = Affinity.objects.get_or_create(
        name="Celestial",
        defaults={"description": "The celestial affinity — light, hope, civic virtue."},
    )
    resonance, _ = Resonance.objects.get_or_create(
        name="Hope",
        defaults={
            "affinity": celestial,
            "description": "The resonance of hope and public service.",
        },
    )

    # ProjectKindResonanceAward — celestial resonance per contribution.
    ProjectKindResonanceAward.objects.update_or_create(
        kind=ProjectKind.CLEANUP,
        defaults={"resonance_award_amount": 5},
    )

    # ContributionMethod rows for CLEANUP (check-based ways to contribute).
    from world.checks.models import CheckType  # noqa: PLC0415

    check_type = CheckType.objects.first()
    if check_type is not None:
        ContributionMethod.objects.update_or_create(
            kind=ProjectKind.CLEANUP,
            name="Sweep Streets",
            defaults={
                "description": "Clean the streets and gutters of the neighborhood.",
                "check_type": check_type,
                "ap_cost": 1,
                "progress_on_success": 10,
                "is_active": True,
            },
        )
        ContributionMethod.objects.update_or_create(
            kind=ProjectKind.CLEANUP,
            name="Repair Facades",
            defaults={
                "description": "Fix broken facades and public fixtures.",
                "check_type": check_type,
                "ap_cost": 2,
                "progress_on_success": 15,
                "is_active": True,
            },
        )

    logger.info("CLEANUP seed content ensured.")
    return resonance
