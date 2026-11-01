"""Resolving an NPC attack."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from flows.constants import EventName
from flows.events.payloads import AttackPreResolvePayload
from world.checks.constants import ModifierSourceKind
from world.checks.services import level_opposition
from world.checks.types import ModifierContribution
from world.combat import services as _svc
from world.combat.constants import StrikeDelivery, TargetingMode, wind_penalty
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    ThreatPoolEntry,
)
from world.combat.services.combos.combo_outcome import _damage_multiplier_for_success
from world.combat.services.npc.defense_roll import defense_result_line, record_defense_roll
from world.combat.services.npc.npc_movement import strike_pool_key
from world.combat.services.npc.npc_targeting import _set_npc_action_targets
from world.combat.services.npc.windup import _declare_windup_attack
from world.combat.services.reactions import (
    choose_dodge,
    covered_place,
    dodge_roll_active,
    land_dodge,
    pay_for_dodge,
    reaction_penalty,
    record_reaction,
)
from world.combat.types import DefenseResult, ParticipantDamageResult
from world.conditions.services import spend_contributing_conditions
from world.covenants.constants import DefenseStyle
from world.covenants.defense import NpcHitDefense, defense_style_for, npc_hit_defense
from world.covenants.style_fit import style_fit_for_defense

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.checks.models import CheckType
    from world.checks.types import CheckResult, ExtraTraitTerm
    from world.scenes.models import Interaction

    PerformCheckFn = Callable[..., CheckResult]


def _execute_npc_attack(  # noqa: PLR0913
    *,
    opponent: CombatOpponent,
    eligible: list[ThreatPoolEntry],
    encounter: CombatEncounter,
    target_pool: list,
    targeting_participants: bool,
    rotation: int,
    threat_map: dict[int, int] | None,
    shield_participant_ids: set[int] | None,
    actions: list[CombatOpponentAction],
    pools: dict[tuple[str, bool], list] | None = None,
) -> bool:
    """Execute one NPC attack, appending to *actions* or declaring a windup.

    Picks a weighted-random threat entry; if it has ``windup_rounds > 0``
    declares a pending windup attack (no immediate row). Otherwise creates a
    ``CombatOpponentAction`` row and sets its targets.

    ``pools`` (#4607) narrows the pool to the targets the CHOSEN entry can strike this
    round, keyed by ``strike_pool_key`` (``reachable_pools``: a wind-up only from where
    the opponent stands, else after moving); the caller passes only entries with someone
    in reach. Returns True when a wind-up was declared.

    Args:
        opponent: The attacking ``CombatOpponent``.
        eligible: Eligible (off-cooldown) threat pool entries.
        encounter: The active ``CombatEncounter``.
        target_pool: The resolved target pool for this round.
        targeting_participants: Whether targeting uses participants.
        rotation: The attack index within the round (for rotation logic).
        threat_map: Optional threat-map for target selection.
        shield_participant_ids: Optional set of shield-bearing participant IDs.
        actions: The accumulator list to append created actions to.
        pools: Optional reachable targets per ``strike_pool_key`` (see above).
    """
    weights = [e.weight for e in eligible]
    chosen = random.choices(eligible, weights=weights, k=1)[0]  # noqa: S311 # NOSONAR game RNG, not crypto
    if pools is not None:
        target_pool = pools.get(strike_pool_key(chosen)) or target_pool

    # Telegraphed wind-up (#2637 design 2-3): a windup_rounds entry commits
    # to a PendingOpponentAttack instead of a same-round CombatOpponentAction.
    # No CombatOpponentAction row exists for this attack until it matures.
    if chosen.windup_rounds > 0:
        _declare_windup_attack(
            opponent,
            chosen,
            encounter,
            target_pool,
            targeting_participants=targeting_participants,
            rotation=rotation,
            threat_map=threat_map,
            shield_participant_ids=shield_participant_ids,
        )
        return True

    action = CombatOpponentAction.objects.create(
        opponent=opponent,
        round_number=encounter.round_number,
        threat_entry=chosen,
    )
    _set_npc_action_targets(
        action,
        chosen,
        target_pool,
        targeting_participants=targeting_participants,
        rotation=rotation,
        threat_map=threat_map,
        shield_participant_ids=shield_participant_ids,
    )
    actions.append(action)
    return False


def _npc_hit_defense(  # noqa: PLR0913
    opponent_action: CombatOpponentAction,
    participant: CombatParticipant,
    check_type: CheckType,
    *,
    target_difficulty: int,
    extra_modifiers: int,
    perform_check_fn: PerformCheckFn,
    extra_traits: tuple[ExtraTraitTerm, ...] = (),
) -> NpcHitDefense | None:
    """The barrier or mitigation defense this blow meets, or None (#4759)."""
    character = participant.character_sheet.character
    style = defense_style_for(character).style
    if style not in (DefenseStyle.BARRIER, DefenseStyle.GEAR_SOAK):
        return None
    return NpcHitDefense(
        defender=character,
        style=style,
        attacker_level=opponent_action.opponent.level,
        defender_level=participant.character_sheet.current_level,
        check_type=check_type,
        target_difficulty=target_difficulty,
        extra_modifiers=extra_modifiers,
        perform_check_fn=perform_check_fn,
        extra_traits=extra_traits,
    )


def _missile_wind_contribution(
    opponent_action: CombatOpponentAction, participant: CombatParticipant
) -> ModifierContribution | None:
    """The wind's penalty on a PC's defense against an NPC's missile, or None (#1555).

    Only MISSILE-delivered threat entries with a defense roll are affected; flat
    base_damage entries (no defense_check_type) never reach the defense roll.
    """
    room = participant.encounter.room
    if opponent_action.threat_entry.delivery != StrikeDelivery.MISSILE or room is None:
        return None
    from world.locations.constants import StatKey  # noqa: PLC0415
    from world.locations.services import felt_exposure  # noqa: PLC0415

    wind_mod = wind_penalty(felt_exposure(room, stat_key=StatKey.WIND))
    if not wind_mod:
        return None
    return ModifierContribution(
        source_kind=ModifierSourceKind.SCENE,
        source_label="Wind",
        value=-wind_mod,
    )


def resolve_npc_attack(
    opponent_action: CombatOpponentAction,
    participant: CombatParticipant,
    check_type: CheckType,
    *,
    perform_check_fn: PerformCheckFn | None = None,
    interaction_factory: Callable[[], Interaction] | None = None,
) -> DefenseResult:
    """Resolve one NPC attack against one PC via a defensive check.

    The PC rolls ``perform_check`` against the NPC's attack. The success
    level determines a damage multiplier applied to the threat entry's
    ``base_damage``.

    #2536 slice 3 Task 6: this is the ONLY defense-check site in v1 that
    threads a ``SituationContext`` with ``attacker`` populated
    (``opponent_action.opponent``) into ``perform_check`` — making
    CHECK_BONUS/TIER_FLOOR/BOTCH_IMMUNITY situational perks, including
    ``Situation.ATTACKER_AFFINITY``-gated ones, live on the defender's roll.

    Args:
        opponent_action: The NPC's chosen action for the round.
        participant: The targeted PC.
        check_type: The CheckType matching the attack's category.
        perform_check_fn: Optional callable override for testing. Defaults
            to ``world.checks.services.perform_check``.
        interaction_factory: The NPC action's Narrator ACTION interaction (#4884). Given,
            the defender's roll is recorded on it as a ``ConsequenceOutcome`` with its
            breakdown (``world.combat.services.npc.defense_roll``).

    Returns:
        A ``DefenseResult`` containing the check outcome and damage applied.
    """
    if perform_check_fn is None:
        from world.checks.services import perform_check as perform_check_fn  # noqa: PLC0415

    character = participant.character_sheet.character
    room = character.location

    # --- ATTACK_PRE_RESOLVE (cancellable) ---
    pre_payload = AttackPreResolvePayload(
        attacker=opponent_action.opponent,
        targets=[character],
        weapon=None,
        action=opponent_action,
    )
    if room is not None:
        stack = _svc.emit_event(
            EventName.ATTACK_PRE_RESOLVE,
            pre_payload,
            location=room,
        )
        if stack.was_cancelled():
            return DefenseResult(
                success_level=0,
                damage_multiplier=0.0,
                final_damage=0,
                damage_result=ParticipantDamageResult(
                    damage_dealt=0,
                    health_after=0,
                    knockout_eligible=False,
                    death_eligible=False,
                    permanent_wound_eligible=False,
                ),
            )

    # Route the defensive check through the shared modifier seam so it honors
    # every character-side source — fashion (perception-relative, scene-derived),
    # covenant-role / equipment-walk, persistent CharacterModifiers, and
    # conditions — exactly as the offense roll does (#750, #512). The perceiving
    # society is derived from the encounter's scene; ``collect_check_modifiers``
    # self-limits (a fashion bonus only lands when ``check_type`` has a scoped
    # modifier_target and the scene's society has a matching in-vogue style).
    # Bond combat bonus (#2021): relationship co-combatant passive.
    from world.relationships.services import bond_combat_bonus  # noqa: PLC0415

    bond_contributions = bond_combat_bonus(
        participant.character_sheet,
        participant.encounter,
    )

    # Wind-as-mechanic (#1555) symmetry: the same gale that ruins a PC's missile shot
    # ruins an NPC's.
    wind = _missile_wind_contribution(opponent_action, participant)
    if wind is not None:
        bond_contributions = [*bond_contributions, wind]

    # The defender's style skill (#4884) counts while every worn armor kind and every
    # held vow is on their combat style. The defense type applies either way.
    style_fit = style_fit_for_defense(character)
    style_traits = tuple(style_fit.extra_traits(check_type))
    breakdown = _svc.collect_check_modifiers(
        participant.character_sheet,
        check_type,
        scene=participant.encounter.scene,
        extra_contributions=bond_contributions,
        extra_traits=style_traits,
    )

    # #2536 slice 3 Task 6: thread the defense-side situation context so
    # CHECK_BONUS/TIER_FLOOR/BOTCH_IMMUNITY situational perks can fire on the
    # PC's defensive roll — the one context where the SUBJECT is not the
    # aggressor, so `target` stays None and `attacker` carries the NPC's
    # opponent row instead (the ATTACKER_AFFINITY evaluator's data source).
    # Mirrors the offense sites' sheet + CombatRoundContext construction
    # (services.py:435-448) with `holder`/`subject` both the defender's own
    # sheet, matching `_resolve_social_check`'s pattern above.
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    defender_sheet = participant.character_sheet
    situation_ctx = SituationContext(
        holder=defender_sheet,
        subject=defender_sheet,
        target=None,
        resolution=CombatRoundContext(participant),
        attacker=opponent_action.opponent,
    )
    # #2707: the PC defends here, so it's the ATTACKING NPC's level (and its
    # aspect match on this defense check) that sets the difficulty -- the
    # inverse of the offense/penetration sites, where the difficulty is
    # sourced from the side being acted upon.
    from world.combat.stat_mapping import DEFENSE_STAT  # noqa: PLC0415

    difficulty = level_opposition(
        check_type,
        level=opponent_action.opponent.level,
        character=opponent_action.opponent.objectdb,
    )
    # The automatic dodge (#4676): a capability that dodges adds its value to this
    # roll, costs anima or fatigue, and each reaction already made this round takes
    # a step off. A place-covering attack is escaped only by landing outside it.
    covered = covered_place(opponent_action, participant)
    dodge = choose_dodge(participant, covered_position=covered)
    dodge_modifier = 0
    if dodge is not None and pay_for_dodge(participant, dodge):
        dodge_modifier = dodge.source.value - reaction_penalty(participant)
        record_reaction(participant)
    else:
        dodge = None
    result: CheckResult = perform_check_fn(
        character,
        check_type,
        target_difficulty=difficulty,
        extra_modifiers=breakdown.extra_modifiers_total + dodge_modifier,
        situation_ctx=situation_ctx,
        stat_override=DEFENSE_STAT,
        extra_traits=style_traits,
    )
    spend_contributing_conditions(breakdown)
    moved_out = dodge is not None and land_dodge(participant, dodge, result.success_level)

    multiplier = _damage_multiplier_for_success(result.success_level)
    if covered is not None and moved_out:
        multiplier = 0.0  # she left the covered place before it landed
    # damage_multiplier is a Decimal field (authored per-opponent scaling);
    # damage_scale (#2637, the wind-up downgrade ladder) is a plain float —
    # apply them in two steps so Decimal never multiplies directly against a
    # float (TypeError).
    base_damage = int(
        opponent_action.threat_entry.base_damage * opponent_action.opponent.damage_multiplier
    )
    base_damage = int(base_damage * opponent_action.damage_scale)
    # The attacker's own damage-dealt rows (#4742): a smoke-form NPC's steel barely lands.
    from world.conditions.services import scaled_outgoing_damage  # noqa: PLC0415

    base_damage = scaled_outgoing_damage(
        opponent_action.opponent.objectdb, base_damage, opponent_action.threat_entry.damage_type
    )
    final_damage = math.floor(base_damage * multiplier)

    # The defender's defense style (#4759) decides what the blow meets below: a
    # barrier's ward rolls this same check before it absorbs, and a mitigation
    # defender's armor leaks against a much higher-level attacker. Evasion is the
    # dodge above; no style is the behavior before #4759.
    hit_defense = _npc_hit_defense(
        opponent_action,
        participant,
        check_type,
        target_difficulty=difficulty,
        extra_modifiers=breakdown.extra_modifiers_total,
        perform_check_fn=perform_check_fn,
        extra_traits=style_traits,
    )
    with dodge_roll_active(), npc_hit_defense(hit_defense):
        damage_result = _svc.apply_damage_to_participant(
            participant,
            final_damage,
            damage_type=opponent_action.threat_entry.damage_type,
            source=opponent_action.opponent,
            on_hit_pool=opponent_action.threat_entry.on_hit_consequence_pool,
            delivery=opponent_action.threat_entry.delivery,
            is_area=(
                opponent_action.threat_entry.targeting_mode != TargetingMode.SINGLE
                or covered is not None
            ),
        )

    if interaction_factory is not None:
        record_defense_roll(
            participant,
            attacker_name=opponent_action.opponent.name,
            check_type=check_type,
            breakdown=breakdown,
            style_fit=style_fit,
            summary=defense_result_line(result, damage_result.damage_dealt),
            interaction=interaction_factory(),
            combat_round=opponent_action.round_number,
            dodge_modifier=dodge_modifier,
        )

    return DefenseResult(
        success_level=result.success_level,
        damage_multiplier=multiplier,
        final_damage=final_damage,
        damage_result=damage_result,
    )
