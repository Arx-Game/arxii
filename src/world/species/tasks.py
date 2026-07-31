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
            _observe_hazard_safely(instance)
    holder_rows = CharacterDistinction.objects.filter(
        distinction__tags__slug__in=(SUN_BANE_TAG, SUN_ALLERGY_TAG),
    ).select_related("character")
    for row in holder_rows:
        character = row.character.character
        if character is None or character.pk in seen:
            continue
        seen.add(character.pk)
        _reconcile_safely(character)


def _observe_hazard_safely(instance) -> None:
    """One sweep observation on a damaging sunlight instance: count damage, AFK-flee.

    The observation layer is hazard-generic (``world.conditions.hazard_prompt``);
    this supplies the sun-specific refuge behavior and thresholds.
    """
    from world.conditions.hazard_prompt import observe_hazard  # noqa: PLC0415
    from world.species.sun_constants import (  # noqa: PLC0415
        AUTO_FLEE_AFTER_DAMAGE_OBSERVATIONS,
        BURNING_SEVERITY_THRESHOLD,
    )
    from world.species.sun_refuge import flee_to_sun_refuge  # noqa: PLC0415

    if instance.resolved_at is not None:
        return
    if instance.severity < BURNING_SEVERITY_THRESHOLD:
        return
    target = instance.target
    observe_hazard(
        instance,
        flee=lambda: flee_to_sun_refuge(target),
        auto_flee_after=AUTO_FLEE_AFTER_DAMAGE_OBSERVATIONS,
    )


def _reconcile_safely(character) -> None:
    """One character's reconcile; a bad row never aborts the sweep."""
    from world.species.services import reconcile_sun_exposure_safely  # noqa: PLC0415

    reconcile_sun_exposure_safely(character)


def moon_reconcile_tick() -> None:
    """Roll moon-control windows for every moon-bound character (#2845).

    Sibling of ``sun_reconcile_tick``: sweeps holders of any ``moon-bound``
    tagged distinction and runs their control-check window. All gating (night,
    sky exposure, pull threshold, tier exemption, already-Berserk) lives in
    ``reconcile_moon_pull`` — the sweep is deliberately dumb. Volume is
    proportional to moon-bound PCs, not the grid.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415
    from world.species.moon_constants import (  # noqa: PLC0415
        CANI_SPECIES_NAME,
        MOON_BOUND_TAG,
    )
    from world.species.moon_sensitivity import (  # noqa: PLC0415
        reconcile_cani_unease_safely,
        reconcile_moon_pull_safely,
    )

    seen: set[int] = set()
    holder_rows = CharacterDistinction.objects.filter(
        distinction__tags__slug=MOON_BOUND_TAG,
    ).select_related("character")
    for row in holder_rows:
        character = row.character.character
        if character is None or character.pk in seen:
            continue
        seen.add(character.pk)
        reconcile_moon_pull_safely(character)
    # Cani unease (ruled 2026-07-31): the umbrella subspecies feels the open
    # night moon — a flavor condition + one-time message, applied/removed here.
    cani_sheets = CharacterSheet.objects.filter(
        species__name=CANI_SPECIES_NAME,
    ) | CharacterSheet.objects.filter(species__parent__name=CANI_SPECIES_NAME)
    for sheet in cani_sheets:
        character = sheet.character
        if character is None or character.pk in seen:
            continue
        seen.add(character.pk)
        reconcile_cani_unease_safely(character)


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
    register_task(
        CronDefinition(
            task_key="species.moon_reconcile",
            callable=moon_reconcile_tick,
            interval=timedelta(minutes=5),
            phase=CronPhase.DRAIN,
            description=(
                "Moon control-check windows for moon-bound characters "
                "(forced shift + Berserk on failure, #2845)."
            ),
        )
    )
