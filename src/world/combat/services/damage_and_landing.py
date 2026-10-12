"""Sent-flying landings, participant damage application, interceptors, companion defend."""

from __future__ import annotations

from decimal import Decimal
import math
from typing import TYPE_CHECKING

from django.db.models import Case, Q, When

from flows.constants import EventName
from flows.events.payloads import DamagePreApplyPayload
from world.combat import services as _svc
from world.combat.constants import (
    SENT_FLYING_IMPACT_FRACTION,
    CombatManeuver,
    OpponentStatus,
    ParticipantStatus,
    StrikeDelivery,
)
from world.combat.damage_source import classify_source
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.services.break_bar_and_protection import (
    apply_equipped_armor_soak,
    apply_position_cover,
)
from world.combat.services.combos import _emit_post_damage_events
from world.combat.services.interpose import _dispatch_interpose_action, apply_rampart_interception
from world.combat.services.interpose_helpers import _fire_on_hit_pool
from world.combat.services.npc_round_and_damage import (
    _apply_condition_damage_interactions,
    _apply_execute_multiplier,
)
from world.combat.services.pc_and_npc_actions import _allegiance_credit_sheet
from world.combat.services.windup_and_attacks import (
    _apply_sustained_erosion_rider,
    _clear_sent_flying_marker,
)
from world.combat.types import ActionOutcome, ParticipantDamageResult
from world.scenes.constants import RoundStatus
from world.vitals.constants import (
    DEATH_HEALTH_THRESHOLD,
    KNOCKOUT_HEALTH_THRESHOLD,
    PERMANENT_WOUND_THRESHOLD,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import ConditionTemplate, DamageType
    from world.vitals.models import CharacterVitals


def _resolve_one_sent_flying_landing(
    participant: CombatParticipant,
    template: ConditionTemplate,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> None:
    """Land one unanswered Sent Flying marker: plummet chain, or a hard impact (#2638).

    Reuses the plummet system's own fall-eligibility seam
    (``maybe_emit_fall`` — emits ``EventName.FELL`` only when the destination
    Position is CHASM) rather than reimplementing it: if the victim's room has
    a CHASM position, they are launched over the edge into it and
    ``maybe_emit_fall`` hands off to the existing multi-round descent +
    CATCH_THE_FALLER machinery — zero new machinery, per the design.
    Otherwise this is a hard, unassisted landing: a second Physical debit of
    ``floor(sent_flying_damage * SENT_FLYING_IMPACT_FRACTION)`` through the
    STANDARD combat damage path (``apply_damage_to_participant`` +
    ``process_damage_consequences`` — the same two-call shape
    ``_resolve_npc_action_on_target`` uses for every other NPC hit), resolved
    at its full computed value with NO extra narration beyond whatever that
    standard path already produces — the celebrate/silence boundary: an
    unanswered landing is unremarked. The marker + its damage carrier are
    cleared either way.
    """
    from world.areas.positioning.constants import PositionKind  # noqa: PLC0415
    from world.areas.positioning.models import Position  # noqa: PLC0415
    from world.areas.positioning.services import (  # noqa: PLC0415
        force_move_to_position,
        maybe_emit_fall,
    )
    from world.combat.sent_flying_content import (  # noqa: PLC0415
        SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME,
    )
    from world.conditions.models import DamageType  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    damage = participant.sent_flying_damage
    _clear_sent_flying_marker(participant, character, template)

    room = character.location
    chasm = (
        Position.objects.filter(room=room, kind=PositionKind.CHASM).first()
        if room is not None
        else None
    )
    if chasm is not None:
        force_move_to_position(character, chasm)
        maybe_emit_fall(character, chasm)
        return

    impact = math.floor(damage * SENT_FLYING_IMPACT_FRACTION)
    if impact <= 0:
        return

    damage_type = DamageType.objects.filter(name=SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME).first()
    dmg_result = _svc.apply_damage_to_participant(
        participant,
        impact,
        damage_type=damage_type,
    )
    process_damage_consequences(
        character_sheet=participant.character_sheet,
        damage_dealt=dmg_result.damage_dealt,
        damage_type=damage_type,
    )


def _resolve_sent_flying_markers(encounter: CombatEncounter) -> None:
    """Explicitly resolve every unanswered Sent Flying marker at round end (#2638).

    Mirrors the plummet system's own explicit-resolution idiom — never a
    per-round DoT tick. Batches: one participant query (candidates carrying a
    nonzero damage carrier) + one BATCHED ``ConditionInstance`` existence
    check across every candidate's character (never a query per participant —
    "no queries in loops"); a candidate whose marker was already cleared by a
    mid-air catch (or removed by some other path) just gets its stale carrier
    zeroed, no landing resolution. Called from ``resolve_round`` after the
    round-tick pass and before boss phase transitions.
    """
    from world.combat.sent_flying_content import SENT_FLYING_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionInstance, ConditionTemplate  # noqa: PLC0415

    try:
        template = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        return

    marked = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
            sent_flying_damage__gt=0,
        ).select_related("character_sheet__character")
    )
    if not marked:
        return

    character_ids = [p.character_sheet.character_id for p in marked]
    still_marked_ids = set(
        ConditionInstance.objects.filter(
            condition=template,
            target_id__in=character_ids,
            is_suppressed=False,
        ).values_list("target_id", flat=True)
    )

    for p in marked:
        character = p.character_sheet.character
        if character.id not in still_marked_ids:
            # Stale carrier (marker already cleared elsewhere) — just reset it.
            p.sent_flying_damage = 0
            p.save(update_fields=["sent_flying_damage"])
            continue
        _resolve_one_sent_flying_landing(p, template, character)


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


def apply_damage_to_participant(  # noqa: PLR0913
    participant: CombatParticipant,
    damage: int,
    *,
    force_death: bool = False,
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

    # Deliberate ordering: the on-hit pool (knockback/trap) resolves and may
    # apply its own damage to vitals.health BEFORE the triggering hit's own
    # `vitals.health -= effective_damage` below runs. Both writes land on the
    # same idmapper-cached CharacterVitals instance, so the arithmetic still
    # composes correctly regardless of order (e.g. 100 - 10 hit - 30 trap = 60).
    if on_hit_pool is not None:
        _fire_on_hit_pool(character, source, on_hit_pool)

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

    effective_damage = apply_damage_reduction_from_threads(character, effective_damage)

    # Damage-type resistance (condition + gift-thread) via the shared seam (#1588).
    # The species drawback's negative ConditionResistanceModifier (vulnerability) and
    # the species-gift thread's positive RESISTANCE pull-effect net here. None
    # damage_type is a no-op. Mirrors the three non-combat damage seams that now call
    # the same function.
    effective_damage = resolve_damage_type_resistance(character, effective_damage, damage_type)

    # Equipped-armor soak (issue #508). PCs have no authored soak field; worn
    # armor is their only soak source, and absorbing pieces take durability wear.
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
        health_after=health_after,
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


def _apply_combo_rider(
    participant: CombatParticipant,
    action: CombatRoundAction,
    target: CombatOpponent,
    outcome: ActionOutcome,
) -> None:
    """Append combo-upgraded bonus damage when the target is still alive.

    The combo rider is applied in addition to the pipeline result. It is
    skipped when the target has been defeated (by the pipeline or earlier).
    """
    target.refresh_from_db()
    if target.status == OpponentStatus.DEFEATED:
        return
    combo = action.combo_upgrade
    dmg_result = _svc.apply_damage_to_opponent(
        target,
        combo.bonus_damage,
        bypass_soak=combo.bypass_soak,
        source_sheet=participant.character_sheet,
    )
    outcome.combo_used = combo
    outcome.damage_results.append(dmg_result)


def _resolve_npc_action_on_opponent_target(  # noqa: PLR0913 - needs full resolution context
    target_opponent: CombatOpponent,
    *,
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    outcome: ActionOutcome,
    conditions: list,
    condition_applications: list,
) -> None:
    """Resolve one NPC action against a single OPPONENT target (#1584 Task 7b, #4091).

    Routes an ALLY summon's, or a charmed/turned NPC's, attack at a hostile opponent.
    Damage only — the PC survivability pipeline (``process_damage_consequences``)
    stays PC-only here; ``apply_damage_to_opponent`` already sets
    ``OpponentStatus.DEFEATED`` internally. Damage/defeat achievement credit goes to
    ``_allegiance_credit_sheet`` (the summoner, or the PC who won the attacker over);
    null-safe when neither applies. A threat entry's ``conditions_applied`` now lands
    on an opponent target too, when the hit dealt damage (#4091) — the bulk apply
    after the resolution loops in ``_resolve_npc_action`` covers it.
    """
    # Mirror the participant guard: skip an escaped/defeated (non-ACTIVE) target.
    if target_opponent.status != OpponentStatus.ACTIVE:
        return

    dmg_result = _svc.apply_damage_to_opponent(
        target_opponent,
        int(npc_action.threat_entry.base_damage * npc_action.damage_scale),
        damage_type=npc_action.threat_entry.damage_type,
        source_sheet=_allegiance_credit_sheet(opponent, opponent.encounter),
    )
    outcome.damage_results.append(dmg_result)
    if dmg_result.damage_dealt > 0 and conditions and target_opponent.objectdb_id is not None:
        condition_applications.extend((target_opponent.objectdb, ct) for ct in conditions)


def _try_interpose(
    participant: CombatParticipant,
    pre_payload: DamagePreApplyPayload,
) -> None:
    """Select and dispatch the highest-precedence armed INTERPOSE this round.

    Named-ally declarations precede guard-anyone declarations. Ties use the
    guardian participant id and then declaration id. An unavailable declaration
    is skipped, but an attempted challenge (including a failed roll) ends the
    search so reaction and per-hit budgets retain their existing semantics.

    Looks for a :class:`~world.combat.models.CombatRoundAction` declaring
    ``INTERPOSE`` for *participant* (or any ally) in the current round, resolves
    the interposer's capability challenge via :func:`dispatch_interpose`, and
    mutates *pre_payload.amount* in place.

    Passes ``select_best_check_rating=True`` (no explicit *approach*) so the
    interposer's better-rated reaction action — Reflexes or the Melee-Defense
    twin, whichever the guardian is actually built for — is picked deterministically
    (#2207; see :func:`~world.mechanics.reactions._select_best_rated_action`).

    **Guard:** no-op when the encounter is not ``RESOLVING`` so that
    non-combat callers of :func:`apply_damage_to_participant` are unaffected.

    At most one guardian is exercised for a hit. If a higher-precedence guardian
    cannot attempt, selection falls through to the next declaration.

    **Technique-guardian branch (#2207):** when the declaration carries a
    validated protective technique (``action.focused_action_id`` set — see
    :func:`declare_interpose`), dispatch replaces the mundane capability-reaction
    challenge with :func:`_try_technique_interpose` (the guardian's own cast
    check, anima cost instead of fatigue). The mundane path below is otherwise
    unchanged.
    """
    encounter = participant.encounter
    if encounter.status != RoundStatus.RESOLVING:
        return

    # Bug fix (#2638, discovered while building the sibling sent-flying catch
    # query): Django's `field__in=[x, None]` silently DROPS the None entry —
    # it compiles to a bare `IN (x)`, never `x OR field IS NULL` — so a
    # guard-anyone (`focused_ally_target=None`) declaration could never
    # actually fire here, even though `ally_intercepted_for_me` and
    # `_ensure_interpose_challenges` both correctly treat it as armed cover.
    # Q(...) | Q(...) is required to express the OR NULL branch.
    # Named guardians have precedence over guard-anyone declarations. Within a
    # precedence tier, participant id and declaration id provide stable ordering
    # rather than relying on database insertion order. Exclude self-interpose
    # before selection so a victim's broad declaration cannot shadow a backup.
    actions = list(
        CombatRoundAction.objects.filter(
            Q(focused_ally_target=participant) | Q(focused_ally_target__isnull=True),
            participant__encounter=encounter,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            participant__status=ParticipantStatus.ACTIVE,
        )
        .exclude(participant=participant)
        .select_related("participant__character_sheet__character")
        .order_by(
            Case(When(focused_ally_target=participant, then=0), default=1),
            "participant_id",
            "pk",
        )
    )
    if not actions:
        return

    protected = participant.character_sheet.character
    for action in actions:
        # A false result means this declaration could not attempt (for example,
        # its reaction or technique is unavailable). Only an actual attempt,
        # including a failed roll, ends protector selection.
        if _dispatch_interpose_action(action, protected, pre_payload):
            return


def _try_companion_defend(
    participant: CombatParticipant,
    pre_payload: DamagePreApplyPayload,
) -> None:
    """Check for a companion ordered to DEFEND_ALLY for this participant (#1921).

    If found, redirect the damage to the companion's CombatOpponent via
    ``apply_damage_to_opponent`` (which handles soak, resistance, and defeat).
    The companion's soak applies. If the companion is defeated, overflow
    damage passes through to the original target.

    **Guard:** no-op when the encounter is not ``RESOLVING`` so that
    non-combat callers of :func:`apply_damage_to_participant` are unaffected.
    """
    from world.companions.constants import CompanionOrderKind  # noqa: PLC0415
    from world.companions.models import CompanionOrder  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.RESOLVING:
        return

    order = (
        CompanionOrder.objects.filter(
            defending_participant=participant,
            encounter=encounter,
            round_number=encounter.round_number,
            order_kind=CompanionOrderKind.DEFEND_ALLY,
        )
        .select_related("companion")
        .first()
    )
    if order is None:
        return

    # Find the companion's materialized CombatOpponent
    companion_opponent = CombatOpponent.objects.filter(
        summoned_by=order.companion.owner,
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    ).first()
    if companion_opponent is None:
        return

    # Redirect damage to the companion. skip_guardian_shield=True: the
    # guardian already had a chance to interpose for `participant` above via
    # _try_interpose (same blow) — without this, the redirect re-enters
    # _resolve_opponent_pre_apply -> _try_guardian_shield_opponent and would
    # charge that guardian's interpose fatigue/anima a second time for one
    # hit (#2207 review finding I1). The companion's own DAMAGE_PRE_APPLY
    # trigger band still runs.
    _svc.apply_damage_to_opponent(
        companion_opponent,
        pre_payload.amount,
        damage_type=pre_payload.damage_type,
        skip_guardian_shield=True,
    )

    # If companion survived, zero out the damage to the ally
    if companion_opponent.status == OpponentStatus.ACTIVE:
        pre_payload.amount = 0
    else:
        # Companion defeated; overflow damage goes to the ally
        pre_payload.amount = max(0, pre_payload.amount - companion_opponent.max_health)
