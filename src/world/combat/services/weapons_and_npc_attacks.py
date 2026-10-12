"""Joust, NPC attack resolution, elevation, and equipped weapon helpers."""

from __future__ import annotations

from collections.abc import Callable
import math
from typing import TYPE_CHECKING

from flows.constants import EventName
from flows.events.payloads import AttackPreResolvePayload
from world.checks.constants import ModifierSourceKind
from world.checks.services import level_opposition
from world.checks.types import ModifierContribution
from world.combat import services as _svc
from world.combat.constants import (
    ELEVATION_ADVANTAGE_TARGET_NAME,
    ENTITY_TYPE_NPC,
    CombatManeuver,
    EncounterType,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    wind_penalty,
)
from world.combat.models import (
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.services.boss_and_social import _damage_multiplier_for_success
from world.combat.services.break_bar_and_protection import _combat_target_bonus
from world.combat.services.damage_and_landing import _resolve_npc_action_on_opponent_target
from world.combat.services.declaration_phase import _JOUST_PARTICIPANT_COUNT
from world.combat.services.interpose_helpers import _trigger_sent_flying
from world.combat.services.pc_and_npc_actions import _npc_action_target_label
from world.combat.types import ActionOutcome, DefenseResult, ParticipantDamageResult
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.areas.positioning.models import Position
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult
    from world.combat.types import WeaponContribution
    from world.conditions.models import ConditionTemplate, DamageType
    from world.items.models import ItemInstance
    from world.magic.models import Technique
    from world.magic.models.techniques import AbstractDamageProfile
    from world.scenes.models import Interaction

    PerformCheckFn = Callable[..., CheckResult]


def _equipped_weapon_archetype(character: Character) -> str | None:
    """The ``gear_archetype`` of character's strongest equipped weapon, or None."""
    inst = _select_equipped_weapon(character)
    if inst is None:
        return None
    return inst.template.gear_archetype


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


def resolve_npc_attack(
    opponent_action: CombatOpponentAction,
    participant: CombatParticipant,
    check_type: CheckType,
    *,
    perform_check_fn: PerformCheckFn | None = None,
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

    # Wind-as-mechanic (#1555) symmetry: the same gale that ruins a PC's
    # missile shot ruins an NPC's. Only MISSILE-delivered threat entries with
    # a defense roll are affected — flat base_damage entries (no defense_check_type,
    # never reaching this function) stay untouched.
    if (
        opponent_action.threat_entry.delivery == StrikeDelivery.MISSILE
        and participant.encounter.room is not None
    ):
        from world.locations.constants import StatKey  # noqa: PLC0415
        from world.locations.services import felt_exposure  # noqa: PLC0415

        wind_mod = wind_penalty(felt_exposure(participant.encounter.room, stat_key=StatKey.WIND))
        if wind_mod:
            bond_contributions = [
                *bond_contributions,
                ModifierContribution(
                    source_kind=ModifierSourceKind.SCENE,
                    source_label="Wind",
                    value=-wind_mod,
                ),
            ]

    breakdown = _svc.collect_check_modifiers(
        participant.character_sheet,
        check_type,
        scene=participant.encounter.scene,
        extra_contributions=bond_contributions,
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

    result: CheckResult = perform_check_fn(
        character,
        check_type,
        target_difficulty=level_opposition(
            check_type,
            level=opponent_action.opponent.level,
            character=opponent_action.opponent.objectdb,
        ),
        extra_modifiers=breakdown.total,
        situation_ctx=situation_ctx,
        stat_override=DEFENSE_STAT,
    )

    multiplier = _damage_multiplier_for_success(result.success_level)
    # damage_multiplier is a Decimal field (authored per-opponent scaling);
    # damage_scale (#2637, the wind-up downgrade ladder) is a plain float —
    # apply them in two steps so Decimal never multiplies directly against a
    # float (TypeError).
    base_damage = int(
        opponent_action.threat_entry.base_damage * opponent_action.opponent.damage_multiplier
    )
    base_damage = int(base_damage * opponent_action.damage_scale)
    final_damage = math.floor(base_damage * multiplier)

    damage_result = _svc.apply_damage_to_participant(
        participant,
        final_damage,
        damage_type=opponent_action.threat_entry.damage_type,
        source=opponent_action.opponent,
        on_hit_pool=opponent_action.threat_entry.on_hit_consequence_pool,
        delivery=opponent_action.threat_entry.delivery,
        is_area=opponent_action.threat_entry.targeting_mode != TargetingMode.SINGLE,
    )

    return DefenseResult(
        success_level=result.success_level,
        damage_multiplier=multiplier,
        final_damage=final_damage,
        damage_result=damage_result,
    )


def _resolve_npc_action_on_target(  # noqa: PLR0913 - per-target resolution needs full context
    target_participant: CombatParticipant,
    *,
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
    conditions: list,
    outcome: ActionOutcome,
    condition_applications: list,
    get_npc_action_interaction: Callable[[], Interaction],
) -> None:
    """Resolve one NPC action against a single target, recording results in place.

    Skips escaped (non-ACTIVE) and dead targets. Applies damage (via a defense
    check when one is configured, else flat threat damage), runs the
    survivability pipeline, and queues any conditions for bulk apply by
    appending to ``outcome`` and ``condition_applications``.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    # A successful escape protects for the rest of the round (#878). The
    # idmapper guarantees this is the same instance _resolve_flee just
    # mutated, so the status write is visible without a re-fetch.
    if target_participant.status != ParticipantStatus.ACTIVE:
        return

    # Damage recipients: any not-dead target is valid. Unconscious / dying
    # PCs still take damage (incapacitation/dying are conditions, not a gate
    # on damage application). Only the dead are excluded.
    if is_dead(target_participant.character_sheet):
        return

    # Survivability pipeline — knockout, death, wound checks.
    # coherence_cache_scope memoizes motif_coherence_bonus per (sheet, resonance)
    # so DR (inside apply_damage_to_participant / resolve_npc_attack) + the three
    # save baselines (inside process_damage_consequences) share one wardrobe walk (#1267).
    from world.magic.services import coherence_cache_scope  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    with coherence_cache_scope():
        if defense_check_type is not None:
            defense = resolve_npc_attack(
                npc_action,
                target_participant,
                defense_check_type,
                perform_check_fn=defense_check_fn,
            )
            dmg_result = defense.damage_result
        else:
            dmg_result = _svc.apply_damage_to_participant(
                target_participant,
                int(npc_action.threat_entry.base_damage * npc_action.damage_scale),
                damage_type=npc_action.threat_entry.damage_type,
                source=opponent,
                on_hit_pool=npc_action.threat_entry.on_hit_consequence_pool,
                delivery=npc_action.threat_entry.delivery,
                is_area=npc_action.threat_entry.targeting_mode != TargetingMode.SINGLE,
            )
        outcome.damage_results.append(dmg_result)

        consequence = process_damage_consequences(
            character_sheet=target_participant.character_sheet,
            damage_dealt=dmg_result.damage_dealt,
            damage_type=npc_action.threat_entry.damage_type,
            combat_interaction_factory=get_npc_action_interaction,
            source_character=opponent.objectdb,
        )
    outcome.damage_consequences.append(consequence)

    # Sent Flying trigger (#2638): a sends_flying attack that connects with
    # damage > 0 launches its victim airborne — the plummet-pattern's
    # "in-flight" clone (see the "Sent Flying" function family: _trigger_sent_flying
    # onward, defined above swarm_kills).
    if npc_action.threat_entry.sends_flying and dmg_result.damage_dealt > 0:
        _trigger_sent_flying(target_participant, npc_action, dmg_result.damage_dealt)

    # Nemesis/toxic-NPC-bond regard hook (#2039): a notable (persona-backed)
    # NPC opponent critically harming a PC (death- or permanent-wound-eligible
    # hit) records an NPC_HARMED_PC_INTEREST regard event. A mook/persona-less
    # opponent's hit — or any non-critical hit from a notable NPC — is
    # deliberately a no-op: no NpcRegard row is ever created for it.
    if opponent.persona_id is not None and (
        dmg_result.death_eligible or dmg_result.permanent_wound_eligible
    ):
        from world.npc_services.constants import NpcRegardEventReason  # noqa: PLC0415
        from world.npc_services.regard import (  # noqa: PLC0415
            get_regard_event_config,
            record_npc_regard_event,
        )
        from world.scenes.models import Persona  # noqa: PLC0415

        try:
            pc_persona = target_participant.character_sheet.primary_persona
        except Persona.DoesNotExist:
            pc_persona = None
        if pc_persona is not None:
            cfg = get_regard_event_config()
            record_npc_regard_event(
                holder_persona=opponent.persona,
                target=pc_persona,
                amount=cfg.combat_harm_amount,
                reason=NpcRegardEventReason.NPC_HARMED_PC_INTEREST,
                source_npc_combat_action=npc_action,
            )

    # Collect condition applications for bulk apply
    if dmg_result.damage_dealt > 0 and conditions:
        target_obj = target_participant.character_sheet.character
        condition_applications.extend((target_obj, ct) for ct in conditions)


def _resolve_npc_action(
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
) -> ActionOutcome:
    """Resolve a single NPC's action against its targets.

    Exactly one target relation is populated per action: participant ``targets``
    (the normal PC-facing path — applies damage, knockout/death transitions, and
    threat-entry conditions) or ``opponent_targets`` (an ALLY summon, or a charmed/
    turned NPC, attacking a hostile opponent — damage plus threat-entry conditions
    on a damaging hit; #1584, #4091). No survivability pipeline either way for the
    opponent-target path.

    When ``defense_check_type`` is None (production), the defense check type is
    sourced from ``npc_action.threat_entry.defense_check_type`` (#1994). A
    non-None external param (test override) takes precedence.
    """
    # Source from threat entry when no external override is provided (#1994).
    effective_defense_check_type = defense_check_type or npc_action.threat_entry.defense_check_type
    outcome = ActionOutcome(entity_type=ENTITY_TYPE_NPC, entity_label=str(opponent))

    try:
        targets: list[CombatParticipant] = npc_action.cached_targets
    except AttributeError:
        targets = list(npc_action.targets.all())

    try:
        opponent_targets: list[CombatOpponent] = npc_action.cached_opponent_targets
    except AttributeError:
        opponent_targets = list(npc_action.opponent_targets.all())

    # Exactly one relation is populated; use whichever for narration labels.
    label_targets: list = targets or opponent_targets

    # Pre-fetch conditions from the threat entry
    try:
        conditions = npc_action.threat_entry.cached_conditions
    except AttributeError:
        conditions = list(npc_action.threat_entry.conditions_applied.all())

    from world.combat.interaction_services import (  # noqa: PLC0415
        create_npc_action_interaction,
        personas_for_participants,
    )

    # #3787 Task 5 - who this NPC action struck. Batched once (no queries in a
    # loop): `targets` may hold several PC participants hit by one NPC action.
    # `opponent_targets` (the ALLY-summon-vs-NPC path) are NPCs with no Persona,
    # so they never contribute a target.
    npc_target_personas = personas_for_participants(targets)

    # Lazy factory: mint the ACTION-mode Interaction only when the first
    # survivability tier actually fires (#864). Memoised so all targets of this
    # NPC action share one row.
    npc_action_label = _npc_action_target_label(label_targets)
    _npc_interaction_cache: list[Interaction] = []

    def _get_npc_action_interaction() -> Interaction:
        if not _npc_interaction_cache:
            _npc_interaction_cache.append(
                create_npc_action_interaction(
                    opponent_action=npc_action,
                    target_label=npc_action_label,
                    target_personas=npc_target_personas,
                )
            )
        return _npc_interaction_cache[0]

    condition_applications: list[tuple[ObjectDB, ConditionTemplate]] = []

    for target_participant in targets:
        _resolve_npc_action_on_target(
            target_participant,
            opponent=opponent,
            npc_action=npc_action,
            defense_check_type=effective_defense_check_type,
            defense_check_fn=defense_check_fn,
            conditions=conditions,
            outcome=outcome,
            condition_applications=condition_applications,
            get_npc_action_interaction=_get_npc_action_interaction,
        )

    # Opponent-target path (#1584, #4091): an ALLY summon or a charmed/turned NPC
    # attacking a hostile opponent. Damage, plus threat-entry conditions on a
    # damaging hit (fed into the same bulk-apply call below); no survivability
    # pipeline.
    for target_opponent in opponent_targets:
        _resolve_npc_action_on_opponent_target(
            target_opponent,
            opponent=opponent,
            npc_action=npc_action,
            outcome=outcome,
            conditions=conditions,
            condition_applications=condition_applications,
        )

    # Bulk-apply all conditions from this NPC action
    if condition_applications:
        from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415
        from world.conditions.types import BulkConditionApplication  # noqa: PLC0415

        bulk_apply_conditions(
            [BulkConditionApplication(target=t, template=ct) for (t, ct) in condition_applications],
            source_character=opponent.objectdb,
        )

    # Broadcast a durable, Narrator-authored OUTCOME line for the NPC action.
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        render_action_outcome_narration,
    )

    # Same label_targets as npc_action_label above -- reuse rather than
    # re-running persona_names_for_sheets for the identical list.
    npc_target_label = npc_action_label
    npc_narration = render_action_outcome_narration(
        actor_label=str(opponent),
        technique_name=npc_action.threat_entry.name,
        target_label=npc_target_label,
        outcome=outcome,
        hit_text=npc_action.threat_entry.hit_narration,
        miss_text=npc_action.threat_entry.miss_narration,
    )
    broadcast_action_outcome(
        encounter=opponent.encounter,
        narration=npc_narration,
        target_personas=npc_target_personas,
    )

    return outcome


def elevation_bonus(
    attacker_sheet: CharacterSheet, attacker_pos: Position, target_pos: Position
) -> int:
    """Flat to-hit bonus when attacker is elevated/aerial and target is not.

    Returns 0 in all other cases (both elevated, both ground, attacker
    ground / target elevated). Offensive-only — no penalty for firing up.
    The magnitude comes from the 'elevation_advantage' ModifierTarget
    (staff-authored via CharacterModifier).
    """
    from world.areas.positioning.constants import PositionKind  # noqa: PLC0415

    elevated_kinds = {PositionKind.ELEVATED, PositionKind.AERIAL}
    if attacker_pos.kind not in elevated_kinds:
        return 0
    if target_pos.kind in elevated_kinds:
        return 0
    return _combat_target_bonus(attacker_sheet, ELEVATION_ADVANTAGE_TARGET_NAME)


def _select_equipped_weapon(character: Character) -> ItemInstance | None:
    """The character's strongest equipped weapon instance (>0 effective damage).

    Deterministic: max by effective_weapon_damage, tie-break by item_instance pk
    (lowest pk wins, via negating pk in the comparison key).
    """
    from world.items.constants import WEAPON_ARCHETYPES  # noqa: PLC0415

    best = None
    for equipped in character.equipped_items:
        inst = equipped.item_instance
        if inst.template.gear_archetype not in WEAPON_ARCHETYPES:
            continue
        dmg = inst.effective_weapon_damage
        if dmg <= 0:
            continue
        key = (dmg, -inst.pk)
        if best is None or key > best[0]:
            best = (key, inst)
    return best[1] if best is not None else None


def effective_weapon_profile(character: Character) -> WeaponContribution | None:
    """The character's strongest equipped weapon as a combat contribution."""
    from world.combat.types import WeaponContribution  # noqa: PLC0415

    inst = _select_equipped_weapon(character)
    if inst is None:
        return None
    return WeaponContribution(
        damage=inst.effective_weapon_damage,
        damage_type=inst.effective_weapon_damage_type,
    )


def _weapon_augmented_budget(
    profile: AbstractDamageProfile,
    budget: int,
    weapon: WeaponContribution | None,
    sheet: object | None = None,
) -> tuple[int, DamageType | None]:
    """Fold an equipped weapon's contribution into a damage profile's budget.

    For a ``uses_equipped_weapon`` profile with an equipped weapon, adds the
    weapon's damage to the formula budget, then the covenant-role weapon-damage
    bonus (via ``_combat_target_bonus``) when a sheet is supplied. If the
    profile authored no damage_type of its own, the weapon's type is used.
    Returns ``(budget, damage_type)``; non-weapon profiles (or an unarmed
    attacker) pass through unchanged.
    """
    profile_damage_type = profile.damage_type
    if profile.uses_equipped_weapon and weapon is not None:
        budget += weapon.damage
        if sheet is not None:
            from world.items.constants import WEAPON_DAMAGE_TARGET_NAME  # noqa: PLC0415

            budget += _combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)
        if profile_damage_type is None:
            profile_damage_type = weapon.damage_type
    return budget, profile_damage_type


def _wear_equipped_weapon(character: Character) -> None:
    """Apply one point of durability wear to the character's strongest weapon.

    Called once per landed weapon-based attack (not once per damage profile), so
    a multi-component technique does not double-wear the weapon.
    """
    weapon_inst = _select_equipped_weapon(character)
    if weapon_inst is None:
        return
    from world.items.services.durability import decrement_item_durability  # noqa: PLC0415

    decrement_item_durability(item_instance=weapon_inst)
