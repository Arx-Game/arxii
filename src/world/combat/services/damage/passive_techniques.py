"""Passive techniques and their trigger handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import OpponentStatus, ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.services.damage.probing import increment_probing
from world.conditions.constants import Allegiance
from world.mechanics.effect_targets import technique_condition_bonuses

if TYPE_CHECKING:
    from world.magic.models import Technique


def _apply_passive_technique(
    technique: Technique,
    participant: CombatParticipant,
    encounter: CombatEncounter,
) -> None:
    """Apply a declared passive technique's authored conditions with NO dice roll.

    A passive IS a Technique with authored ``TechniqueAppliedCondition`` rows.
    Each row is applied at fixed scaling — ``effective_power=technique.intensity``
    and ``success_level=row.minimum_success_level`` — so no ``CheckResult`` is
    constructed and no offense roll happens (contrast ``CombatTechniqueResolver``,
    which is roll/damage-bound). Reuses ``bulk_apply_conditions`` so passives feed
    the exact same condition machinery as the focused path.

    Target resolution (v1):

    - ``SELF`` → the actor's own character.
    - ``ENEMY`` → every ACTIVE opponent's ``objectdb`` whose EFFECTIVE allegiance
      is not ALLY_OF_CASTER (#1584, #4091). An ALLY summon or a charmed NPC fights
      on the actor's side, so enemy-targeted AoE never lands on either; a TURNED
      or calmed (NEUTRAL) opponent is still the party's opponent for a passive —
      only a charmed/summoned ally is spared. Mirrors ``_resolve_condition_target``'s
      ENEMY branch, which returns ``opp.objectdb`` for an active opponent. Every
      opponent (including ephemeral CombatNPCs) is created with an ObjectDB by
      ``add_opponent``; the FK is only nulled if the ObjectDB is destroyed
      externally, so we skip opponents whose ``objectdb`` is None — matching the
      focused path's None-guard.
    - ``ALLY`` → every ACTIVE participant except the actor.

    When ``technique.combo_opening_probing`` is set, every such ACTIVE opponent
    gains that much probing (the combo-opening reward) via ``increment_probing`` —
    the combo-opening effect for ephemeral opponents regardless of conditions.
    """
    from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415
    from world.conditions.types import BulkConditionApplication  # noqa: PLC0415
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415
    from world.magic.services.condition_application import (  # noqa: PLC0415
        bonused_duration,
        bonused_severity,
    )
    from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

    actor = participant.character_sheet.character

    # Batch the opponent/ally queries ONCE before the row loop (no queries in loop).
    active_opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        ).select_related("objectdb")
    )
    allegiances = effective_allegiances(active_opponents)
    active_allies = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        .exclude(pk=participant.pk)
        .select_related("character_sheet__character")
    )

    # Combo-opening probing: granted to every opponent not fighting on the actor's
    # side, independent of any condition application (the combo-opening effect for
    # ephemeral opponents). A charmed/summoned ally is on the actor's side, so
    # probing it is meaningless (#1584); a turned or calmed opponent still gets it.
    if technique.combo_opening_probing:
        for opp in active_opponents:
            if allegiances[opp.pk] != Allegiance.ALLY_OF_CASTER:
                increment_probing(opp, technique.combo_opening_probing)

    # resolve_round prefetches ``..._passive__condition_applications__condition`` so
    # this ``.all()`` reads the prefetch cache (no per-passive query in the resolution
    # loop). Standalone callers fall back to lazy loads. Do NOT add ``.select_related``
    # here — it forces a fresh query and bypasses the prefetch cache.
    rows = list(technique.condition_applications.all())
    if not rows:
        return

    # The actor's condition severity and duration modifiers (#4822), worked out once for the
    # passive however many rows and targets it has.
    severity_bonus, duration_bonus = technique_condition_bonuses(
        participant.character_sheet, technique
    )
    applications: list[BulkConditionApplication] = []
    for row in rows:
        severity = row.compute_severity(
            effective_power=technique.intensity,
            success_level=row.minimum_success_level,
        )
        duration = row.compute_duration_rounds(
            effective_power=technique.intensity,
            success_level=row.minimum_success_level,
        )
        severity = bonused_severity(severity, severity_bonus)
        duration = bonused_duration(duration, duration_bonus)

        if row.target_kind == ConditionTargetKind.SELF:
            targets = [actor]
        elif row.target_kind == ConditionTargetKind.ENEMY:
            targets = [
                opp.objectdb
                for opp in active_opponents
                if allegiances[opp.pk] != Allegiance.ALLY_OF_CASTER and opp.objectdb is not None
            ]
        elif row.target_kind == ConditionTargetKind.ALLY:
            targets = [ally.character_sheet.character for ally in active_allies]
        else:
            targets = []

        applications.extend(
            BulkConditionApplication(
                target=target,
                template=row.condition,
                severity=severity,
                duration_rounds=duration,
                stack_count=row.stack_count,
            )
            for target in targets
        )

    if not applications:
        return

    bulk_apply_conditions(
        applications,
        source_character=actor,
        source_technique=technique,
        source_description=f"passive: {technique.name}",
    )


def _refresh_participant_trigger_handlers(encounter: CombatEncounter) -> None:
    """Make passive-installed reactive triggers visible within the same round.

    ``_resolve_passive_actions`` may install reactive conditions (e.g. DEFEND's
    Shielded) on allies. Installing a reactive condition creates ``Trigger`` rows
    and calls ``TriggerHandler.on_trigger_added`` → ``invalidate``, which defers the
    cache reset to ``transaction.on_commit``. But ``resolve_round`` runs the whole
    round inside one ``@transaction.atomic`` block, so that ``on_commit`` callback
    does not fire until *after* this round's damage resolution — meaning the new
    triggers would be invisible to the very NPC attack they are meant to mitigate.

    Synchronously refresh each active participant's character trigger handler so the
    freshly ``bulk_create``d rows (already visible in this transaction) are loaded
    before ``_resolve_actions`` runs. The deferred ``on_commit(_reset)`` remains
    intact as the cross-transaction/rollback safety net.
    """
    participants = CombatParticipant.objects.filter(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    ).select_related("character_sheet__character")
    for participant in participants:
        character = participant.character_sheet.character
        handler = character.trigger_handler
        if handler is not None:
            handler.refresh()


def _resolve_passive_actions(
    encounter: CombatEncounter,
    pc_actions: dict[int, CombatRoundAction],
) -> None:
    """Apply every declared passive on every PC action before focused resolution.

    Runs before ``_resolve_actions`` so defensive/buff passives land before any
    focused or NPC action resolves this round.
    """
    for action in pc_actions.values():
        for passive in (
            action.physical_passive,
            action.social_passive,
            action.mental_passive,
        ):
            if passive is not None:
                _apply_passive_technique(passive, action.participant, encounter)
