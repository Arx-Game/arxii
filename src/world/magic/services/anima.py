"""Anima resource service functions for the magic system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.models import CharacterAnima
from world.magic.types.ritual import AnimaRegenTickSummary, RitualOutcome

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Scene


def deduct_anima(character: ObjectDB, effective_cost: int) -> int:
    """Deduct anima from character, returning the overburn deficit.

    Uses select_for_update inside transaction.atomic for race-condition
    safety, following the ActionPointPool.spend() pattern.
    Returns 0 if no overburn, positive int if life force is drawn.
    """
    if effective_cost <= 0:
        return 0

    with transaction.atomic():
        anima = CharacterAnima.objects.select_for_update().get(character=character)
        deficit = max(effective_cost - anima.current, 0)
        anima.current = max(anima.current - effective_cost, 0)
        anima.save(update_fields=["current"])
    return deficit


# ---------------------------------------------------------------------------
# Outcome-level constants (mirror Phase 6 conditions.services convention)
# ---------------------------------------------------------------------------
_CRIT_SUCCESS_LEVEL = 2
_SUCCESS_LEVEL = 1
_PARTIAL_LEVEL = 0


@transaction.atomic
def perform_anima_ritual(
    character_sheet: CharacterSheet,
    scene: Scene,
) -> RitualOutcome:
    """Perform the character's personalised anima ritual once per scene.

    Scope 6 §5.1. Outcome-tiered recovery budget: reduce Soulfray severity
    first at ritual_severity_cost_per_point per point, then refill anima
    with leftover budget. Crit always tops anima to max regardless.
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.conditions.models import ConditionInstance, ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import decay_condition_severity  # noqa: PLC0415
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415
    from world.magic.exceptions import (  # noqa: PLC0415
        CharacterEngagedForRitual,
        NoRitualConfigured,
        RitualAlreadyPerformedThisScene,
        RitualScenePrerequisiteFailed,
    )
    from world.magic.models.anima import AnimaRitualPerformance  # noqa: PLC0415
    from world.magic.models.soulfray import SoulfrayConfig  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    # OneToOne reverse accessor, not a simple attribute — getattr is correct here.
    ritual = getattr(character_sheet, "anima_ritual", None)  # noqa: GETATTR_LITERAL
    if ritual is None:
        raise NoRitualConfigured

    character = character_sheet.character

    if CharacterEngagement.objects.filter(character=character).exists():
        raise CharacterEngagedForRitual

    if not scene.is_active or not _scene_participant(scene, character):
        raise RitualScenePrerequisiteFailed

    if AnimaRitualPerformance.objects.filter(ritual=ritual, scene=scene).exists():
        raise RitualAlreadyPerformedThisScene

    check_result = perform_check(
        character,
        check_type=ritual.check_type,
        target_difficulty=ritual.target_difficulty,
    )
    outcome = check_result.outcome

    config = SoulfrayConfig.objects.first()
    budget = _budget_for_outcome(outcome, config)

    anima = CharacterAnima.objects.select_for_update().get(character=character)

    soulfray_template = ConditionTemplate.objects.get(name=SOULFRAY_CONDITION_NAME)
    soulfray_inst = (
        ConditionInstance.objects.select_for_update()
        .filter(target=character, condition=soulfray_template, resolved_at__isnull=True)
        .first()
    )

    severity_reduced = 0
    soulfray_resolved = False
    stage_after = None
    if soulfray_inst is not None:
        stage_after = soulfray_inst.current_stage
        while budget > 0 and soulfray_inst.severity > 0:
            decay_result = decay_condition_severity(soulfray_inst, amount=1)
            severity_reduced += 1
            budget -= config.ritual_severity_cost_per_point
            stage_after = decay_result.new_stage
            if decay_result.resolved:
                soulfray_resolved = True
                break

    anima_before = anima.current
    anima.current = min(anima.current + max(0, budget), anima.maximum)

    if int(outcome.success_level) >= _CRIT_SUCCESS_LEVEL:
        anima.current = anima.maximum

    anima.save(update_fields=["current"])
    anima_recovered = anima.current - anima_before

    performance = AnimaRitualPerformance.objects.create(
        ritual=ritual,
        scene=scene,
        was_successful=int(outcome.success_level) >= _SUCCESS_LEVEL,
        anima_recovered=anima_recovered,
        outcome=outcome,
        severity_reduced=severity_reduced,
        target_character=None,
    )

    return RitualOutcome(
        performance=performance,
        outcome=outcome,
        severity_reduced=severity_reduced,
        anima_recovered=anima_recovered,
        soulfray_stage_after=stage_after,
        soulfray_resolved=soulfray_resolved,
    )


def _budget_for_outcome(outcome: object, config: object) -> int:
    """Return the anima/severity budget for an outcome row."""
    level = int(outcome.success_level)  # type: ignore[union-attr]
    if level >= _CRIT_SUCCESS_LEVEL:
        return int(config.ritual_budget_critical_success)  # type: ignore[union-attr]
    if level >= _SUCCESS_LEVEL:
        return int(config.ritual_budget_success)  # type: ignore[union-attr]
    if level == _PARTIAL_LEVEL:
        return int(config.ritual_budget_partial)  # type: ignore[union-attr]
    return int(config.ritual_budget_failure)  # type: ignore[union-attr]


def _scene_participant(scene: Scene, character: ObjectDB) -> bool:
    """Return True when *character*'s account has a SceneParticipation in *scene*.

    Mirrors conditions.services._scene_participant — same roster-tenure path.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    try:
        entry = RosterEntry.objects.get(character_sheet_id=character.pk)
    except RosterEntry.DoesNotExist:
        return False
    tenure = entry.tenures.filter(end_date__isnull=True).first()
    if tenure is None:
        return False
    account_id = tenure.player_data.account_id
    return SceneParticipation.objects.filter(scene=scene, account_id=account_id).exists()


def anima_regen_tick() -> AnimaRegenTickSummary:
    """Scheduler entry point. Daily anima regen across all characters.

    Per spec §5.5. Skips engaged characters and characters whose active
    condition stages carry the blocking Property. Skip sets are bulk-
    fetched in 2 queries before the loop to avoid N+1.
    """
    from django.db.models import F  # noqa: PLC0415, I001
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.models.anima import AnimaConfig  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415
    from world.mechanics.models import Property  # noqa: PLC0415

    config = AnimaConfig.get_singleton()
    blocker = Property.objects.get(name=config.daily_regen_blocking_property_key)

    engaged_ids = set(
        CharacterEngagement.objects.values_list("character_id", flat=True),
    )
    blocked_ids = set(
        ConditionInstance.objects.filter(
            resolved_at__isnull=True,
            current_stage__properties=blocker,
        )
        .values_list("target_id", flat=True)
        .distinct(),
    )

    qs = CharacterAnima.objects.filter(
        current__lt=F("maximum"),
    ).select_related("character")

    examined = 0
    regenerated = 0
    engagement_blocked = 0
    condition_blocked = 0
    to_update = []

    for row in qs:
        examined += 1
        char_id = row.character_id
        if char_id in engaged_ids:
            engagement_blocked += 1
            continue
        if char_id in blocked_ids:
            condition_blocked += 1
            continue
        regen = (row.maximum * config.daily_regen_percent) // 100
        if regen <= 0:
            continue
        row.current = min(row.current + regen, row.maximum)
        to_update.append(row)
        regenerated += 1

    # Bulk update all at once
    if to_update:
        CharacterAnima.objects.bulk_update(to_update, ["current"], batch_size=1000)

    return AnimaRegenTickSummary(
        examined=examined,
        regenerated=regenerated,
        engagement_blocked=engagement_blocked,
        condition_blocked=condition_blocked,
    )
