"""Seed content for the areas app (#1889)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ensure_cleanup_content():
    """Seed CLEANUP project-kind config. Returns the resonance, or None.

    Content-repo-owned rows are looked up, never invented (#2698/ADR-0168):
    ``Affinity`` and ``Resonance`` are both in ``CONTENT_MODELS``, so this
    function may not create them. When the resonance is absent the config that
    hangs off it is still seeded — the award and contribution methods are
    mechanical config, not content — and the caller gets ``None``.

    Before #2890 this ``get_or_create``d an Affinity named "Celestial" and a
    Resonance named "Hope". "Hope" is not one of the twenty-four canonical
    resonances, so had this function ever been wired into a seed cluster it would
    have invented a resonance and shipped it as lore on the next export.

    Idempotent — safe to call multiple times.
    """
    from world.magic.models.affinity import Affinity, Resonance  # noqa: PLC0415
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.models import (  # noqa: PLC0415
        ContributionMethod,
        ProjectKindResonanceAward,
    )
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    celestial = authored_or_sample(
        Affinity,
        {"description": "The celestial affinity — light, hope, civic virtue."},
        name="Celestial",
    )
    resonance = None
    if celestial is not None:
        resonance = authored_or_sample(
            Resonance,
            {
                "affinity": celestial,
                "description": "The resonance of hope and public service.",
            },
            name="Hope",
        )

    # ProjectKindResonanceAward — config, so seeded regardless of the resonance.
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


def ensure_area_elevation_content():
    """Seed one PLACEHOLDER ``AreaElevationRequirement`` row for NEIGHBORHOOD (#696 gap 3).

    Mechanical config, not authored content - magnitudes are staff-tunable, not
    canon lore, so this is a plain ``update_or_create`` (no ``authored_or_sample``
    gate). ``min_held_buildings=0`` on purpose: BUILDING is ``AreaLevel``'s floor, so
    a BUILDING-level area (the only area that elevates *into* NEIGHBORHOOD) can never
    itself have BUILDING-level descendants to hold - the held-buildings threshold only
    becomes meaningful at higher tiers (WARD+), which are unseeded PLACEHOLDER rows
    for a later authoring pass.

    Idempotent - safe to call multiple times.
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import AreaElevationRequirement  # noqa: PLC0415

    row, _ = AreaElevationRequirement.objects.update_or_create(
        to_level=AreaLevel.NEIGHBORHOOD,
        defaults={
            "min_held_buildings": 0,
            "min_order_stat": 0,
            "cost_coppers": 1000,
        },
    )
    logger.info("Area elevation requirement for NEIGHBORHOOD ensured.")
    return row
