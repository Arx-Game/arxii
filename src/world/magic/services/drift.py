"""Carried-drift services (#4732).

A character carrying resonance in affinities other than the one she acts with is
pulled off her own magic. ``drift_for`` measures that pull against the acting aura's
dominant affinity; ``check_resonance_focus`` runs once per cast, before the cast's
modifiers are gathered, and on a failed focus roll applies (or deepens) the authored
conflict condition, whose own check modifier then reaches the same cast's roll.
Every number lives in ``DriftConfig``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.magic.models.drift import DriftConfig
from world.magic.types.drift import DriftReading, FocusOutcome

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance, Technique

# A pair with no authored AffinityInteraction row counts at full weight.
_UNAUTHORED_PAIR_WEIGHT = Decimal(1)


def get_drift_config() -> DriftConfig:
    """Get-or-create the drift config singleton (pk=1)."""
    cfg = DriftConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = DriftConfig.objects.get_or_create(pk=1)
    return cfg


def drift_for(sheet: CharacterSheet) -> DriftReading:
    """The off-aura drift ``sheet``'s character carries against the aura she acts with.

    The dominant affinity is the acting aura's (an active alternate self's affinity
    while one is worn). Her balances in that affinity are her main balance; every
    other balance counts as drift, weighted by the authored
    ``AffinityInteraction.conflict_weight`` of (its affinity, the dominant one). The
    threshold is ``max(threshold_floor, threshold_percent of the main balance)``;
    drift strictly past it is one step, plus one per further ``severity_step``.
    A character with no aura to measure against reads zero.
    """
    from world.magic.models import AffinityInteraction  # noqa: PLC0415
    from world.magic.services.acting_aura import acting_aura  # noqa: PLC0415

    aura = acting_aura(sheet)
    dominant = aura.dominant_affinity if aura is not None else None
    if dominant is None:
        return DriftReading(drift=0, threshold=0, steps_past=0, dominant_affinity=None)

    cfg = get_drift_config()
    main = 0
    weighted_drift = Decimal(0)
    for row in sheet.character.resonances.all():
        affinity = row.resonance.affinity
        if affinity.pk == dominant.pk:
            main += row.balance
            continue
        interaction = AffinityInteraction.objects.interaction_for(affinity, dominant)
        weight = interaction.conflict_weight if interaction is not None else _UNAUTHORED_PAIR_WEIGHT
        weighted_drift += row.balance * weight

    drift = int(weighted_drift)
    threshold = max(cfg.threshold_floor, main * cfg.threshold_percent // 100)
    steps_past = 0
    if drift > threshold:
        steps_past = 1 + (drift - threshold - 1) // cfg.severity_step
    return DriftReading(
        drift=drift, threshold=threshold, steps_past=steps_past, dominant_affinity=dominant
    )


def check_resonance_focus(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - rolls, conditions and messages take the character
    technique: Technique,
    *,
    pulled_resonance: Resonance | None = None,
) -> FocusOutcome | None:
    """Roll the caster's focus against her carried drift, once per cast.

    ``use_technique`` calls it for every cast, after anima is deducted and before
    ``resolve_fn`` gathers the cast's check modifiers, so a condition applied here
    reaches the same cast's roll. A pull is part of its cast, not a roll of its own:
    ``pulled_resonance`` is the resonance this cast pulls, which the caller names
    (the declared cast pull's, or the combat round's committed pull); None means
    the cast pulls nothing. Working it outside her dominant affinity adds
    ``off_aura_pull_steps``.

    Returns None, rolling nothing, when the config's focus check type or conflict
    condition is unset (the Required content dashboard lists both) or when there are
    no steps. On a failed roll (success level below 1) the conflict condition is
    applied at ``steps + (1 - success_level)`` severity, so a worse roll never costs
    less; if she already holds it, its severity advances by one instead.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        apply_condition,
        get_condition_instance,
    )
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

    cfg = get_drift_config()
    if cfg.focus_check_type_id is None or cfg.conflict_condition_id is None:
        return None
    try:
        sheet = character.sheet_data
    except ObjectDoesNotExist:
        return None
    reading = drift_for(sheet)
    if reading.dominant_affinity is None:
        return None
    steps = reading.steps_past
    if (
        pulled_resonance is not None
        and pulled_resonance.affinity_id != reading.dominant_affinity.pk
    ):
        steps += cfg.off_aura_pull_steps
    if steps <= 0:
        return None

    difficulty = cfg.focus_base_difficulty + steps * cfg.focus_difficulty_per_step
    character.msg(
        f"Focus check: you are carrying drift past your threshold against your "
        f"{reading.dominant_affinity.name} aura."
    )
    result = perform_check_with_modifiers(
        character,
        cfg.focus_check_type,
        difficulty,
        extra_traits=activity_skill_terms(MagicActivity.KEEPING_FOCUS),
    )
    success_level = result.success_level
    if success_level >= 1:
        return FocusOutcome(success_level=success_level, steps=steps, applied_severity=0)

    condition = cfg.conflict_condition
    existing = get_condition_instance(character, condition)
    if existing is not None:
        applied = 1
        advance_condition_severity(existing, applied)
    else:
        applied = steps + (1 - success_level)
        apply_condition(
            character,
            condition,
            severity=applied,
            source_technique=technique,
        )
    character.msg(f"You lose your focus as you work {technique.name}: {condition.name}.")
    return FocusOutcome(success_level=success_level, steps=steps, applied_severity=applied)
