"""Declaring a joust and resolving its passes."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from actions.errors import ActionDispatchError
from world.combat import services as _svc
from world.combat.constants import (
    ENTITY_TYPE_PC,
    JOUST_DECISIVE_MARGIN,
    ActionCategory,
    CombatManeuver,
    EncounterType,
)
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.services.equipment.equipped_weapon import (
    _equipped_weapon_archetype,
    effective_weapon_profile,
)
from world.combat.services.techniques.technique_resolver import CombatTechniqueResolver
from world.combat.types import ActionOutcome
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.checks.types import CheckResult
    from world.magic.models import Technique


_JOUST_PARTICIPANT_COUNT = 2  # jousts are strictly 1v1 DUEL encounters


def declare_joust(
    participant: CombatParticipant,
    technique: Technique,
) -> CombatRoundAction:
    """Declare a joust — a mounted, lance-armed opposed pass (#1843).

    Only declarable in a DUEL encounter with exactly two participants where
    BOTH duelists currently hold the Mounted condition and have a
    LANCE-archetype weapon equipped. Resolution
    (``_resolve_joust_pass``, dispatched from ``_resolve_pc_action`` once both
    sides have declared JOUST) rolls one opposed weapon-attack check per side
    and grades the outcome by the success_level gap into
    ``JOUST_DECISIVE_MARGIN``/``JOUST_NARROW_MARGIN`` bands.

    Raises ValueError with clear messages for validation failures.
    """
    from world.companions.mount_content import MOUNTED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import has_condition  # noqa: PLC0415
    from world.items.constants import GearArchetype  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter
    if not can_act(participant.character_sheet):
        msg = "Cannot joust: character is dead or incapacitated."
        raise ValueError(msg)
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot joust: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)
    if encounter.encounter_type != EncounterType.DUEL:
        msg = "Cannot joust: only valid in a duel."
        raise ValueError(msg)

    other = (
        CombatParticipant.objects.filter(encounter=encounter)
        .exclude(pk=participant.pk)
        .select_related("character_sheet")
        .first()
    )
    if other is None or encounter.participants.count() != _JOUST_PARTICIPANT_COUNT:
        msg = "Cannot joust: requires exactly two duelists."
        raise ValueError(msg)

    mounted_template = ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
    for combatant in (participant, other):
        if not has_condition(combatant.character_sheet.character, mounted_template):
            msg = "Cannot joust: both duelists must be mounted."
            raise ValueError(msg)
        if _equipped_weapon_archetype(combatant.character_sheet.character) != GearArchetype.LANCE:
            msg = "Cannot joust: both duelists must wield a lance."
            raise ValueError(msg)

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": technique,
            "focused_category": technique.action_category,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": None,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.JOUST,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": False,
        },
    )
    return action


def _joust_offense_check(participant: CombatParticipant, action: CombatRoundAction) -> CheckResult:
    """Roll one side's JOUST offense check via the shared CombatTechniqueResolver seam.

    Reuses ``CombatTechniqueResolver._roll_check`` so EFFORT/PULL/bond bonuses
    and the LANCE_UNMOUNTED_PENALTY gate all compose exactly as they would for
    a normal attack (both jousters are validated Mounted+LANCE at declare
    time, so the unmounted-lance penalty never actually fires here).
    """
    from world.magic.services.magic_skills import resolve_cast_check  # noqa: PLC0415

    technique = action.focused_action
    if technique.action_template is None:
        raise ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
    cast_check = resolve_cast_check(participant.character_sheet.character, technique)
    if cast_check is None:
        raise ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
    resolver = CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=0,
        fatigue_category=action.focused_category or ActionCategory.PHYSICAL,
        offense_check_type=cast_check.check_type,
        offense_check_fn=None,
        offense_extra_traits=cast_check.extra_traits,
    )
    return resolver._roll_check()  # noqa: SLF001 - same-module reuse of the shared roll seam


def _resolve_joust_pass(
    participant: CombatParticipant,
    action: CombatRoundAction,
    other: CombatParticipant,
    other_action: CombatRoundAction,
) -> None:
    """Resolve a JOUST's single opposed pass — grades by the success_level gap (#1843).

    decisive gap (>= JOUST_DECISIVE_MARGIN): loser takes the winner's lance
    weapon damage x2 + the Unhorsed condition, which force-dismounts them.
    narrow gap (>= JOUST_NARROW_MARGIN, < decisive): loser takes the winner's
    lance weapon damage x1, keeps the saddle. Tie (gap 0): both jarred, no
    damage. Damage is applied to the loser's mirror CombatOpponent via
    ``apply_damage_to_opponent`` — the same non-bypassing pipeline every
    normal duel attack already uses (defenses/soak/non-lethal PvP capping,
    ADR-0023, all fire unchanged).
    """
    from world.companions.mount_content import UNHORSED_CONDITION_NAME  # noqa: PLC0415
    from world.companions.services import MountError, dismount_companion  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    check_a = _joust_offense_check(participant, action)
    check_b = _joust_offense_check(other, other_action)
    gap = check_a.success_level - check_b.success_level

    if gap == 0:
        return  # tie — both jarred, no damage

    winner, loser = (participant, other) if gap > 0 else (other, participant)
    margin = abs(gap)
    # A lost pass is a missed attack (#4858): it builds the loser's intensity, as any miss.
    from world.combat.services.techniques.intensity import (  # noqa: PLC0415
        record_miss_intensity,
    )

    record_miss_intensity(loser)

    weapon = effective_weapon_profile(winner.character_sheet.character)
    base_damage = weapon.damage if weapon is not None else 0
    from world.conditions.services import scaled_outgoing_damage  # noqa: PLC0415

    # The winner's own damage-dealt rows (#4742), for the weapon's type (untyped = Physical).
    base_damage = scaled_outgoing_damage(
        winner.character_sheet.character,
        base_damage,
        weapon.damage_type if weapon is not None else None,
    )

    loser_mirror = CombatOpponent.objects.filter(
        encounter=participant.encounter, mirrors_participant=loser
    ).first()
    if loser_mirror is None:
        return

    if margin >= JOUST_DECISIVE_MARGIN:
        _svc.apply_damage_to_opponent(
            loser_mirror,
            base_damage * 2,
            damage_type=weapon.damage_type if weapon is not None else None,
            source_sheet=winner.character_sheet,
        )
        unhorsed = ConditionTemplate.get_by_name(UNHORSED_CONDITION_NAME)
        apply_condition(
            loser.character_sheet.character,
            unhorsed,
            source_character=winner.character_sheet.character,
        )
        with contextlib.suppress(MountError):
            # Not actually mounted somehow — nothing to dismount.
            dismount_companion(loser.character_sheet)
    else:
        _svc.apply_damage_to_opponent(
            loser_mirror,
            base_damage,
            damage_type=weapon.damage_type if weapon is not None else None,
            source_sheet=winner.character_sheet,
        )


def _resolve_joust(participant: CombatParticipant, action: CombatRoundAction) -> ActionOutcome:
    """Dispatch a declared JOUST maneuver — resolves once both duelists have declared it.

    Deterministic single-resolution: only the lower-pk participant's call
    actually runs ``_resolve_joust_pass`` (avoids a schema field just to
    memoize "already resolved this round" — the higher-pk participant's own
    ``_resolve_pc_action`` pass is a no-op once its partner's pass already
    applied both sides' outcomes).
    """
    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))
    outcome.participant_id = participant.pk

    other = (
        CombatParticipant.objects.filter(encounter=participant.encounter)
        .exclude(pk=participant.pk)
        .select_related("character_sheet")
        .first()
    )
    if other is not None:
        other_action = CombatRoundAction.objects.filter(
            participant=other, round_number=action.round_number
        ).first()
        if (
            other_action is not None
            and other_action.maneuver == CombatManeuver.JOUST
            and participant.pk <= other.pk
        ):
            _resolve_joust_pass(participant, action, other, other_action)

    return outcome
