"""Applying damage to a participant."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from flows.constants import EventName
from flows.events.payloads import (
    CharacterIncapacitatedPayload,
    DamageAppliedPayload,
    DamagePreApplyPayload,
)
from world.combat import services as _svc
from world.combat.constants import StrikeDelivery
from world.combat.damage_source import classify_source
from world.combat.models import CombatOpponent, CombatParticipant
from world.combat.services.damage.companion_defend import _fire_on_hit_pool, _try_companion_defend
from world.combat.services.damage.condition_interaction import _apply_condition_damage_interactions
from world.combat.services.damage.execute import _apply_execute_multiplier
from world.combat.services.damage.interception import apply_rampart_interception
from world.combat.services.declarations.cover import apply_position_cover
from world.combat.services.encounter.death_gate import _emit_death_gate
from world.combat.services.equipment.armor_soak import apply_equipped_armor_soak
from world.combat.services.npc.sustained import _apply_sustained_erosion_rider
from world.combat.types import ParticipantDamageResult
from world.vitals.constants import (
    DEATH_HEALTH_THRESHOLD,
    KNOCKOUT_HEALTH_THRESHOLD,
    PERMANENT_WOUND_THRESHOLD,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from flows.events.payloads import DamageSource
    from typeclasses.characters import Character
    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import DamageType
    from world.vitals.models import CharacterVitals


def _answer_with_strike_backs(applied_payload: DamageAppliedPayload) -> None:
    """Let each strike-back ward on the struck PC answer the blow, oldest first (#4584).

    Read here, where the hit has landed, from the wards' own retaliation fields
    (``retaliating_instances``), not through a seeded flow. ``strike_back`` decides
    whether the blow is answered (an NPC striker, damage dealt, the fee paid).
    A hit from anything but a ``CombatOpponent`` can never be answered (PCs roll,
    NPCs are targets), so it skips the wards query.
    """
    if applied_payload.amount_dealt <= 0:
        return
    if not isinstance(applied_payload.source.ref, CombatOpponent):
        return
    # Lazy imports: magic.services imports combat.services.
    from world.conditions.services import retaliating_instances  # noqa: PLC0415
    from world.magic.services.effect_handlers import strike_back  # noqa: PLC0415

    for instance in retaliating_instances(applied_payload.target):
        strike_back(payload=applied_payload, instance=instance)


def _emit_post_damage_events(  # noqa: PLR0913
    *,
    character: Character,
    room: ObjectDB | None,
    effective_damage: int,
    damage_type: DamageType | None,
    damage_source: DamageSource,
    health_before: int,
    health_after: int,
    max_health: int,
    knockout_eligible: bool,
    was_in_knockout_band: bool,
    death_eligible: bool,
    force_death: bool,
) -> None:
    """Emit DAMAGE_APPLIED, CHARACTER_INCAPACITATED, and CHARACTER_KILLED events post-save.

    Called after vitals.save(); no-op when room is None (unlocated characters).
    Strike-back wards on the struck PC answer right after DAMAGE_APPLIED (#4584).
    """
    if room is None:
        return
    applied_payload = DamageAppliedPayload(
        target=character,
        amount_dealt=effective_damage,
        damage_type=damage_type,
        source=damage_source,
        hp_after=health_after,
    )
    _svc.emit_event(EventName.DAMAGE_APPLIED, applied_payload, location=room)
    _answer_with_strike_backs(applied_payload)
    # Lazy import: world.conditions.control_loss imports checks and magic services.
    from world.conditions.control_loss import fire_wound_triggers  # noqa: PLC0415

    # A hit that drops the character (incapacitated or dead) rolls nothing: they cannot act.
    if health_after > 0 and not (knockout_eligible or death_eligible or force_death):
        fire_wound_triggers(
            character,
            health_before=health_before,
            health_after=health_after,
            max_health=max_health,
        )

    will_emit_death_gate = death_eligible or force_death
    if knockout_eligible and not was_in_knockout_band and not will_emit_death_gate:
        _svc.emit_event(
            EventName.CHARACTER_INCAPACITATED,
            CharacterIncapacitatedPayload(
                character=character,
                source_event=EventName.DAMAGE_PRE_APPLY,
            ),
            location=room,
        )
    if will_emit_death_gate:
        _emit_death_gate(character, room)


def _run_pre_apply_interceptors(
    participant: CombatParticipant,
    pre_payload: DamagePreApplyPayload,
    room: ObjectDB | None,
    vitals: CharacterVitals,
) -> ParticipantDamageResult | None:
    """Run the cancellable ``DAMAGE_PRE_APPLY`` event and reactive interceptors.

    Returns a zero-damage ``ParticipantDamageResult`` when the event is
    cancelled or the amount is fully zeroed by a reactive interceptor
    (blink/reflect/force-field) — signalling an early exit. Returns ``None``
    when the payload survives and interception (interpose/companion-defend)
    has been applied.
    """
    if room is not None:
        stack = _svc.emit_event(
            EventName.DAMAGE_PRE_APPLY,
            pre_payload,
            location=room,
        )
        if stack.was_cancelled():
            return ParticipantDamageResult(
                damage_dealt=0,
                health_after=vitals.health,
                knockout_eligible=False,
                death_eligible=False,
                permanent_wound_eligible=False,
            )

    # A reactive interceptor (blink/reflect/force-field) that fully avoids the
    # hit zeroes pre_payload.amount via mutation rather than CANCEL_EVENT (#1584).
    # Short-circuit BEFORE _try_interpose so an ally is not charged interpose
    # fatigue for blocking a hit that no longer exists.
    if pre_payload.amount <= 0:
        return ParticipantDamageResult(
            damage_dealt=0,
            health_after=vitals.health,
            knockout_eligible=False,
            death_eligible=False,
            permanent_wound_eligible=False,
        )

    _svc._try_interpose(participant, pre_payload)  # noqa: SLF001 (test patch seam)
    _try_companion_defend(participant, pre_payload)
    return None


def apply_damage_to_participant(  # noqa: C901, PLR0913
    participant: CombatParticipant,
    damage: int,
    *,
    force_death: bool = False,
    ignores_soak: bool = False,
    resistance_shift: int = 0,
    bypass_pre_apply: bool = False,
    damage_type: DamageType | None = None,
    source: object | None = None,
    source_sheet: CharacterSheet | None = None,
    on_hit_pool: ConsequencePool | None = None,
    delivery: str = StrikeDelivery.MELEE,
    is_area: bool = False,
    execute_missing_health_multiplier: Decimal = Decimal(0),
) -> ParticipantDamageResult:
    """Apply damage to a PC via their CharacterVitals.

    ignores_soak skips the complete equipped/resonant armor stage, including
    armor wear. Thread damage reduction always applies, regardless of attack type.
    resistance_shift subtracts points from signed typed resistance for this hit
    only; untyped hits ignore the shift.

    Does NOT roll for knockout/death/wounds — only reports eligibility.
    The caller is responsible for acting on the result.

    When ``source_sheet`` is provided (e.g. PC vs PC damage), increments the
    source's ``damage_dealt`` counter. The target always gets a
    ``damage_received`` increment (regardless of source).

    ``delivery``/``is_area`` (#2209) — NPC callers pass the striking
    ``ThreatPoolEntry.delivery`` and ``targeting_mode != SINGLE``; other
    callers default to MELEE/False. Rampart interception (see
    ``apply_rampart_interception``) runs first, before any other reduction,
    UNLESS ``bypass_pre_apply=True`` (the reflect/retaliation loop guard).

    ``execute_missing_health_multiplier`` (#2643): symmetric sibling of
    :func:`apply_damage_to_opponent`'s same-named kwarg — default 0 (no-op, every
    existing caller unaffected). No live caller passes a nonzero value yet: combat
    technique damage in this codebase only ever resolves against ``CombatOpponent``
    targets (``CombatTechniqueResolver._apply_damage``), never a PC
    ``CombatParticipant`` — this parameter exists so the capability is symmetric and
    directly testable, ready for the day PC-vs-PC technique damage is wired. Uses the
    existing ``health_before_pct`` (captured once, before the condition-damage-
    interaction multiply, and reused for both the execute scaling AND the
    knockout/death classification below it — see :func:`_apply_execute_multiplier`).

    Emits reactive events:
    - DAMAGE_PRE_APPLY (cancellable, mutable amount)
    - DAMAGE_APPLIED (post-save, frozen)
    - CHARACTER_INCAPACITATED (only on the transition into the knockout band,
      and only when the death gate does not also fire — death supersedes)
    - CHARACTER_KILLED (if death_eligible or force_death)
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    vitals = CharacterVitals.objects.get(
        character_sheet=participant.character_sheet,
    )

    character = participant.character_sheet.character
    room = character.location
    from world.conditions.services import resolved_damage_type  # noqa: PLC0415

    # Untyped damage is Physical (#4742): resolve once so every read below agrees.
    damage_type = resolved_damage_type(damage_type)

    if not bypass_pre_apply:
        damage = apply_rampart_interception(
            character,
            damage,
            damage_type,
            attacker_ref=source,
            delivery=delivery,
            is_area=is_area,
        )

    damage_source = classify_source(source)

    # --- DAMAGE_PRE_APPLY (cancellable, amount may be modified) ---
    # bypass_pre_apply=True skips emit + interpose; the bounced-reflect path
    # uses this to terminate re-emission (loop guard). pre_payload is still
    # built so effective_damage derives from it regardless.
    pre_payload = DamagePreApplyPayload(
        target=character,
        amount=damage,
        damage_type=damage_type,
        source=damage_source,
    )
    if not bypass_pre_apply:
        early = _run_pre_apply_interceptors(participant, pre_payload, room, vitals)
        if early is not None:
            return early
    if pre_payload.amount <= 0:
        return ParticipantDamageResult(
            damage_dealt=0,
            health_after=vitals.health,
            knockout_eligible=False,
            death_eligible=False,
            permanent_wound_eligible=False,
        )

    # Use the (possibly interposed/modified) amount from the payload.
    # Coerce to int: the MODIFY_PAYLOAD multiply op (DEFEND halves amount by
    # multiplying by 0.5) and INTERPOSE's floor-division both can widen an
    # int amount to float in memory. Django coerces on save, but keeping the
    # in-memory value integral avoids a float flowing through the damage
    # reductions and threshold comparisons below (#1318).
    effective_damage = int(pre_payload.amount)

    # Thread-derived damage reduction (Spec A §5.8 lines 1658–1668).
    # Inlined here rather than a flow subscriber because the flow/event
    # system dispatches on FlowDefinition rows, not Python callables
    # (see Phase 13 Open Item 3). Reads handler caches; near-zero cost.
    from world.conditions.services import resolve_damage_type_resistance  # noqa: PLC0415
    from world.magic.services import apply_damage_reduction_from_threads  # noqa: PLC0415

    # Thread DR is an unconditional survivability baseline, never armor to pierce.
    effective_damage = apply_damage_reduction_from_threads(character, effective_damage)

    # Damage-type resistance (condition + gift-thread) via the shared seam (#1588).
    # The species drawback's negative ConditionResistanceModifier (vulnerability) and
    # the species-gift thread's positive RESISTANCE pull-effect net here. Untyped
    # damage was resolved to Physical at entry. Mirrors the three non-combat damage
    # seams that now call the same function.
    # A fully absorbed hit stays absorbed; vulnerability must not recreate damage
    # after the thread survivability baseline has reduced it to zero.
    if effective_damage > 0:
        effective_damage = resolve_damage_type_resistance(
            character, effective_damage, damage_type, resistance_shift=resistance_shift
        )

    # Deliberate ordering: the on-hit pool (knockback/trap) fires only for a hit that
    # survives thread DR and resistance (#4742), so an incorporeal bearer who absorbs
    # the blow is not shoved; a hit soaked by armor or cover below still knocks back.
    # The pool may apply its own damage to vitals.health BEFORE this hit's own
    # `vitals.health -= effective_damage` runs; both writes land on the same
    # idmapper-cached CharacterVitals, so the arithmetic composes in either order
    # (e.g. 100 - 10 hit - 30 trap = 60).
    if on_hit_pool is not None and effective_damage > 0:
        _fire_on_hit_pool(character, source, on_hit_pool)

    # Equipped-armor soak (issue #508). PCs have no authored soak field; worn
    # armor is their only soak source, and absorbing pieces take durability wear.
    if not ignores_soak:
        effective_damage = apply_equipped_armor_soak(character, effective_damage)

    # Attack-cover from PositionShelter (applies_to_attacks=True rows, #2011).
    effective_damage = apply_position_cover(character, effective_damage, damage_type)

    # health_before(_pct) captured HERE, before this hit's own reductions/subtraction
    # below — the PRE-hit basis both the execute multiplier (#2643) and the
    # knockout/death classification further down share. vitals.health is untouched
    # by anything above this line, so this is safe to read early.
    health_before = vitals.health
    if vitals.max_health > 0:
        health_before_pct = max(0.0, health_before / vitals.max_health)
    else:
        health_before_pct = 0.0

    # Condition-damage interactions (#2018). Final percentage multiplier on
    # net damage, after resistance + armor soak. May consume/transform conditions.
    interaction_result = None
    if effective_damage > 0:
        effective_damage, interaction_result = _apply_condition_damage_interactions(
            character, damage_type, effective_damage
        )

    # Execute (#2643): see apply_damage_to_opponent's twin block + docstring.
    effective_damage = _apply_execute_multiplier(
        effective_damage, execute_missing_health_multiplier, health_before_pct
    )

    vitals.health -= effective_damage
    health_after = vitals.health

    if vitals.max_health > 0:
        health_pct = max(0.0, health_after / vitals.max_health)
    else:
        health_pct = 0.0

    knockout_eligible = (
        health_pct <= KNOCKOUT_HEALTH_THRESHOLD and health_after > DEATH_HEALTH_THRESHOLD
    )
    # Same band test applied to pre-hit health — used only to latch the
    # CHARACTER_INCAPACITATED emit to the transition into the band.
    was_in_knockout_band = (
        health_before_pct <= KNOCKOUT_HEALTH_THRESHOLD and health_before > DEATH_HEALTH_THRESHOLD
    )
    death_eligible = health_after <= DEATH_HEALTH_THRESHOLD
    permanent_wound_eligible = effective_damage > (vitals.max_health * PERMANENT_WOUND_THRESHOLD)

    # Incapacitation / dying state is no longer written here. It is applied by
    # process_damage_consequences (Bleeding-Out / Unconscious conditions) which
    # the caller invokes after damage. force_death still drives the
    # CHARACTER_KILLED event below; the dying condition itself comes from the
    # consequence pipeline — no stray vitals.status write.
    vitals.save(update_fields=["health"])

    # Achievement counters: see world.combat.achievement_counters. Wired in
    # a follow-up phase — keeping the source_sheet kwarg in place so the
    # call sites are pre-threaded.
    del source_sheet

    _emit_post_damage_events(
        character=character,
        room=room,
        effective_damage=effective_damage,
        damage_type=pre_payload.damage_type,
        damage_source=damage_source,
        health_before=health_before,
        health_after=health_after,
        max_health=vitals.max_health,
        knockout_eligible=knockout_eligible,
        was_in_knockout_band=was_in_knockout_band,
        death_eligible=death_eligible,
        force_death=force_death,
    )

    # A sustained action's absorption budget is eroded by the FINAL applied
    # damage — after rampart interception, pre-apply interceptors, thread
    # resistance, armor soak, position cover, condition interactions, and the
    # execute multiplier have all run. Placing this any earlier would erode on
    # damage that never actually landed (#2705).
    _apply_sustained_erosion_rider(participant, effective_damage)

    return ParticipantDamageResult(
        damage_dealt=effective_damage,
        health_after=health_after,
        knockout_eligible=knockout_eligible,
        death_eligible=death_eligible,
        permanent_wound_eligible=permanent_wound_eligible,
        damage_interaction=interaction_result,
    )
