"""Species cron tasks (#2846). Registered at server startup via the aggregator in
``world.game_clock.tasks.register_all_tasks``."""

from __future__ import annotations

from datetime import timedelta

from world.game_clock.task_registry import CronDefinition, CronPhase, register_task


def sun_reconcile_tick() -> None:
    """Re-reconcile sunlight exposure for everyone it could currently touch.

    Fixes the movement-only gap (#2846): a character standing still when the sun
    rises (or their condition escalating under sustained exposure) is picked up
    here rather than waiting for them to move. Two populations:

    1. Every unresolved Sunlight Exposure instance — escalation, phase changes,
       and shade/wardrobe drift all resolve through the same reconcile.
    2. Every sun-sensitive character (held sun-bane / sun-allergy distinction)
       standing in a sky-exposed room without the condition yet.

    Volume note: both sets are proportional to sun-sensitive PCs, not the grid.
    """
    from world.conditions.models import ConditionInstance, ConditionTemplate  # noqa: PLC0415
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415
    from world.species.factories import SUNLIGHT_EXPOSURE_NAME  # noqa: PLC0415
    from world.species.sun_constants import SUN_ALLERGY_TAG, SUN_BANE_TAG  # noqa: PLC0415

    seen: set[int] = set()
    template = ConditionTemplate.objects.filter(name=SUNLIGHT_EXPOSURE_NAME).first()
    if template is not None:
        for instance in ConditionInstance.objects.filter(
            condition=template, resolved_at__isnull=True
        ).select_related("target"):
            target = instance.target
            seen.add(target.pk)
            _reconcile_safely(target)
    holder_rows = CharacterDistinction.objects.filter(
        distinction__tags__slug__in=(SUN_BANE_TAG, SUN_ALLERGY_TAG),
    ).select_related("character")
    for row in holder_rows:
        character = row.character.character
        if character is None or character.pk in seen:
            continue
        seen.add(character.pk)
        _reconcile_safely(character)


def _reconcile_safely(character) -> None:
    """One character's reconcile; a bad row never aborts the sweep."""
    from world.species.services import reconcile_sun_exposure_safely  # noqa: PLC0415

    reconcile_sun_exposure_safely(character)


def register_all_tasks() -> None:
    """Register species cron tasks with the game-clock scheduler."""
    register_task(
        CronDefinition(
            task_key="species.sun_reconcile",
            callable=sun_reconcile_tick,
            interval=timedelta(minutes=5),
            phase=CronPhase.DRAIN,
            description=(
                "Reconcile sunlight exposure for sun-sensitive characters "
                "(stationary dawn pickup + sustained-exposure escalation, #2846)."
            ),
        )
    )
