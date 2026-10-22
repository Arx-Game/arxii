"""Interception pipeline: interpose, redirect and rampart on opponent damage. One call cycle."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Exists, OuterRef, Q

from flows.constants import EventName
from flows.events.payloads import DamagePreApplyPayload
from world.combat import services as _svc
from world.combat.constants import (
    ABSORPTION_CAP_PER_MOMENT,
    INTERPOSE_BASE_FATIGUE_COST,
    REACTIONS_PER_ROUND,
    ActionCategory,
    ClashFlavor,
    CombatAllegiance,
    CombatManeuver,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    StrikeDelivery,
)
from world.combat.damage_source import classify_source
from world.combat.models import (
    Clash,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.services.boss.story_recognition import _record_story_envoy_rescue
from world.combat.services.damage.condition_interaction import _apply_condition_damage_interactions
from world.combat.services.damage.defeat import _emit_companion_fall, _resolve_opponent_defeat
from world.combat.services.damage.engagement_lock import (
    _break_engagement_lock_on_defeat,
    _maybe_trigger_lock_interference,
)
from world.combat.services.damage.execute import (
    _apply_execute_multiplier,
    _opponent_health_before_pct,
)
from world.combat.services.damage.interpose_dispatch import (
    _grade_interpose_damage,
    _narrate_reaction_declined,
    _narrate_technique_interpose_fizzle,
    _settle_technique_interpose_cost,
    apply_interpose_outcome,
)
from world.combat.services.damage.soak import (
    _effective_resistance_for_opponent,
    _effective_soak_for_opponent,
)
from world.combat.services.damage.swarm import _apply_swarm_damage, _zero_opponent_damage_result
from world.combat.services.declarations.redirect import _redirect_away, _redirect_to_object
from world.combat.services.encounter.threat import _accumulate_damage_threat
from world.combat.types import OpponentDamageResult
from world.fatigue.constants import EffortLevel
from world.fatigue.services import apply_fatigue
from world.mechanics.types import ChallengeResolutionResult
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.areas.positioning.models import RampartElementProfile
    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import DamageType
    from world.magic.models.anima import CharacterAnima


def _emit_opponent_pre_apply(
    opponent: CombatOpponent,
    raw_damage: int,
    damage_type: DamageType | None,
    source_sheet: CharacterSheet | None,
) -> tuple[int, bool]:
    """Emit DAMAGE_PRE_APPLY for an opponent; return ``(amount, dropped)``.

    Mirrors the participant path so reactive defences (force-field/reflect/blink)
    fire on NPCs and ALLY summons identically (#1584). Returns the possibly
    mutated damage amount and whether the hit should be dropped — the event
    cancelled it, or the mutated amount fell to <= 0. Opponents with no
    objectdb/location skip the event (amount unchanged, never dropped here).
    """
    if opponent.objectdb is None or opponent.objectdb.location is None:
        return raw_damage, False
    damage_source = classify_source(source_sheet.character if source_sheet is not None else None)
    pre_payload = DamagePreApplyPayload(
        target=opponent.objectdb,
        amount=raw_damage,
        damage_type=damage_type,
        source=damage_source,
    )
    stack = _svc.emit_event(
        EventName.DAMAGE_PRE_APPLY,
        pre_payload,
        location=opponent.objectdb.location,
    )
    if stack.was_cancelled():
        return raw_damage, True
    return pre_payload.amount, pre_payload.amount <= 0


def _try_guardian_shield_opponent(
    opponent: CombatOpponent,
    raw_damage: int,
    damage_type: DamageType | None,
    source_sheet: CharacterSheet | None,
) -> tuple[int, bool]:
    """Guardian-shields-a-summon (#2207): run ANY-ALLY Interpose for an
    ALLY-allegiance ``CombatOpponent`` ward. Return ``(amount, dropped)``,
    mirroring :func:`_emit_opponent_pre_apply`'s contract — ``dropped=True``
    means the guardian fully blocked the hit and the caller should return a
    zero damage result.

    No-op passthrough (amount unchanged, never dropped) when *opponent* is not
    ``allegiance=ALLY`` (an ENEMY opponent is never a ward) or has no
    ``objectdb`` (nothing to bind the interpose challenge/ward target to).
    """
    if opponent.allegiance != CombatAllegiance.ALLY or opponent.objectdb is None:
        return raw_damage, False

    interpose_source = classify_source(source_sheet.character if source_sheet is not None else None)
    interpose_payload = DamagePreApplyPayload(
        target=opponent.objectdb,
        amount=raw_damage,
        damage_type=damage_type,
        source=interpose_source,
    )
    _try_interpose_for_opponent(opponent, interpose_payload)
    amount = int(interpose_payload.amount)
    return amount, amount <= 0


def _resolve_opponent_pre_apply(
    opponent: CombatOpponent,
    raw_damage: int,
    damage_type: DamageType | None,
    source_sheet: CharacterSheet | None,
    *,
    skip_guardian_shield: bool = False,
) -> tuple[int, bool]:
    """Run DAMAGE_PRE_APPLY, then guardian-shields-a-summon (#2207), for an opponent.

    Combines :func:`_emit_opponent_pre_apply` and
    :func:`_try_guardian_shield_opponent` into a single ``(amount, dropped)``
    step for :func:`apply_damage_to_opponent` — the guardian check only runs
    when the reactive DAMAGE_PRE_APPLY step didn't already drop the hit, so a
    cancelled/zeroed hit never charges the guardian's interpose fatigue for
    blocking a hit that no longer exists (mirrors
    :func:`apply_damage_to_participant`'s ordering).

    ``skip_guardian_shield=True`` skips ONLY :func:`_try_guardian_shield_opponent`
    — :func:`_emit_opponent_pre_apply` (the opponent's own DAMAGE_PRE_APPLY
    trigger band) still runs. Used by :func:`_try_companion_defend`'s redirect
    to avoid double-charging a guardian that already had a chance to interpose
    earlier in the same blow.

    Rampart interception (#2209) runs first, before the DAMAGE_PRE_APPLY emit —
    an opponent (e.g. an ALLY summon) standing at a rampart-covered position is
    shielded exactly like a PC. No threat entry is available on this path, so
    delivery/is_area default to MELEE/False.
    """
    if opponent.objectdb is not None:
        raw_damage = apply_rampart_interception(
            opponent.objectdb,
            raw_damage,
            damage_type,
            attacker_ref=source_sheet.character if source_sheet is not None else None,
        )
    raw_damage, dropped = _emit_opponent_pre_apply(opponent, raw_damage, damage_type, source_sheet)
    if dropped:
        return raw_damage, True
    if skip_guardian_shield:
        return raw_damage, False
    return _try_guardian_shield_opponent(opponent, raw_damage, damage_type, source_sheet)


def apply_damage_to_opponent(  # noqa: PLR0913
    opponent: CombatOpponent,
    raw_damage: int,
    *,
    bypass_soak: bool = False,
    bypass_pre_apply: bool = False,
    damage_type: DamageType | None = None,
    source_sheet: CharacterSheet | None = None,
    skip_guardian_shield: bool = False,
    execute_missing_health_multiplier: Decimal = Decimal(0),
    skip_condition_interactions: bool = False,
) -> OpponentDamageResult:
    """Apply damage to an NPC opponent, accounting for soak, probing,
    and damage-type resistance.

    ``skip_condition_interactions=True`` skips the condition-damage-interaction
    multiplier (#2018): the round tick's damage over time passes it so a tick never
    consumes or transforms conditions, matching the PC tick (#4572).

    All raw damage (even fully soaked) contributes to probing. Only damage
    that exceeds soak and resistance actually reduces health.

    When ``source_sheet`` is provided, increments the source's achievement
    counters: ``damage_dealt`` (by post-soak damage), and on defeat
    ``opponents_defeated``.

    ``skip_guardian_shield=True`` skips ONLY the guardian-shields-a-summon
    (#2207) hook — the opponent's own DAMAGE_PRE_APPLY trigger band still
    runs. See :func:`_resolve_opponent_pre_apply`.

    Allegiance-break rolls (#4091, Decision 16) do NOT live here — they used to,
    once per call, which meant a multi-profile technique or a combo rider rolled
    (and narrated a "holds" line) several times for one blow. They are rolled
    once per opponent per PC action, after all of that action's damage (every
    profile plus any combo rider) is known — see
    :func:`_attempt_allegiance_breaks_for_action`, called from
    :func:`_resolve_pc_action`.

    ``execute_missing_health_multiplier`` (#2643): the resolving technique damage
    profile's ``execute_missing_health_multiplier`` (default 0 = no-op, matching every
    existing caller byte-for-byte). Scales damage up as the opponent's PRE-hit health
    runs low — see :func:`_apply_execute_multiplier`. The caller (a technique's damage
    resolution — ``CombatTechniqueResolver._apply_profiles_to_target``) is the one place
    the damage profile is in hand; everywhere else defaults to inert.
    """
    # Swarm: no HP, no soak, no probing -- a landing attack clears bodies.
    if opponent.tier == OpponentTier.SWARM and opponent.swarm_count is not None:
        del source_sheet
        return _apply_swarm_damage(opponent, raw_damage)

    # DAMAGE_PRE_APPLY (cancellable, amount mutable). bypass_pre_apply=True skips
    # emit + mutation; the bounced-reflect path uses this to terminate re-emission
    # (loop guard).
    if not bypass_pre_apply:
        # DAMAGE_PRE_APPLY, then guardian-shields-a-summon (#2207) for
        # ALLY-allegiance opponents — see _resolve_opponent_pre_apply.
        raw_damage, dropped = _resolve_opponent_pre_apply(
            opponent,
            raw_damage,
            damage_type,
            source_sheet,
            skip_guardian_shield=skip_guardian_shield,
        )
        if dropped:
            return _zero_opponent_damage_result(opponent)

    effective_soak = _effective_soak_for_opponent(opponent, bypass_soak)

    resistance = _effective_resistance_for_opponent(opponent, damage_type)

    damage_through = max(0, raw_damage - effective_soak - resistance)

    # Execute (#2643): smooth ramp off the opponent's PRE-hit health, captured here
    # before this hit's own subtraction below — a second profile/hit in the same cast
    # (AoE, multi-profile techniques) correctly compounds off each opponent's own
    # already-reduced health, never a recursive fraction. Placed right before the
    # condition-damage-interaction multiply per design (both are final-stage percent
    # scalers on net damage; order between them doesn't change per-technique intent
    # since only one technique's profile ever supplies a nonzero multiplier per hit).
    damage_through = _apply_execute_multiplier(
        damage_through,
        execute_missing_health_multiplier,
        _opponent_health_before_pct(opponent),
    )

    # Condition-damage interactions (#2018). Final percentage multiplier on
    # net damage, after soak + resistance. May consume/transform conditions.
    interaction_result = None
    if damage_through > 0 and opponent.objectdb is not None and not skip_condition_interactions:
        damage_through, interaction_result = _apply_condition_damage_interactions(
            opponent.objectdb, damage_type, damage_through
        )

    # Combo damage that bypasses soak should not also probe — the combo
    # itself is the reward for probing.
    probing_increment = 0 if bypass_soak else max(0, raw_damage)

    opponent.health -= damage_through
    # ``increment_probing`` is the sibling standalone write site for the no-damage
    # passive path (combo-opening passives). This write stays inline because it
    # shares a single combined save with health/status below; ``probing_increment``
    # is already ``max(0, …)`` so both paths apply the same non-negative clamp.
    opponent.probing_current += probing_increment

    # Hero Killer cannot be defeated -- narrative immunity ("you must run").
    defeated = opponent.health <= 0 and opponent.tier != OpponentTier.HERO_KILLER
    if defeated:
        defeated = _resolve_opponent_defeat(opponent, source_sheet)

    # Break active engagement lock on opponent defeat (#2020).
    if defeated:
        _break_engagement_lock_on_defeat(opponent)

    opponent.save(update_fields=["health", "probing_current", "status"])

    if defeated:
        _emit_companion_fall(opponent)

    # Achievement counters: see world.combat.achievement_counters. Wired in
    # a follow-up phase — keeping the source_sheet kwarg in place so the
    # call sites are pre-threaded.
    # Threat accumulation: damage dealt -> ThreatRecord increment (#2020).
    # Only post-soak, post-resistance damage (damage_through) contributes — the
    # real signal of who is hurting the NPC. No source_sheet = no threat record.
    if source_sheet is not None and damage_through > 0:
        _accumulate_damage_threat(opponent, source_sheet, damage_through)
        # Interference beat (#2020/#3447): a non-locked PC landing damage on a
        # locked opponent fires the duel-interference drama for the locked duelist.
        _maybe_trigger_lock_interference(opponent, source_sheet)
    del source_sheet

    return OpponentDamageResult(
        damage_dealt=damage_through,
        health_damaged=damage_through > 0,
        probed=probing_increment > 0,
        probing_increment=probing_increment,
        defeated=defeated,
        kills=0,
        opponent_id=opponent.pk,
        damage_interaction=interaction_result,
    )


def _try_interpose(
    participant: CombatParticipant,
    pre_payload: DamagePreApplyPayload,
) -> None:
    """Select and dispatch the highest-precedence guardian for this hit.

    Order: named-ally declarations, then standing guards, then guard-anyone
    declarations. Within the declaration tiers, ties use the guardian participant
    id and then declaration id. An unavailable guardian is skipped, but an
    attempted challenge (including a failed roll) ends the search so reaction and
    per-hit budgets retain their existing semantics. A declaration takes
    precedence over a standing guard: a guardian who declared any INTERPOSE this
    round (naming this ward, naming another ward, or guarding anyone) is tried only
    through that declaration, never as a standing guard, so she is tried at most
    once per hit and her declared technique and effort are the ones used.

    **Standing guards (#4584, ADR-4584-A):** a ward bearing an active
    ``ConditionTemplate.source_guards_bearer`` condition is guarded by its
    ``source_character`` when she is an ACTIVE participant of this encounter,
    when she declared no INTERPOSE this round
    (:func:`~world.conditions.services.guardians_by_target`, oldest instance
    first). A guard cast on oneself never interposes for its own
    bearer. A standing guard counts against both budgets exactly as a declaration
    does (``REACTIONS_PER_ROUND`` and ``ABSORPTION_CAP_PER_MOMENT``); ADR-4584-A
    revisits ADR-0161 for this. It covers player-character wards in combat only:
    not an ALLY summon ward (:func:`_try_interpose_for_opponent`) and not
    out-of-combat Sudden Harm.

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
    cannot attempt, selection falls through to the next one.

    **Technique-guardian branch (#2207):** when the declaration carries a
    validated protective technique (``action.focused_action_id`` set — see
    :func:`declare_interpose`), dispatch replaces the mundane capability-reaction
    challenge with :func:`_try_technique_interpose` (the guardian's own cast
    check, anima cost instead of fatigue). The mundane path below is otherwise
    unchanged. A standing guard always takes the mundane path.
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
    # Within a precedence tier, participant id and declaration id provide stable
    # ordering rather than relying on database insertion order. Exclude
    # self-interpose before selection so a victim's broad declaration cannot
    # shadow a backup.
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
        .order_by("participant_id", "pk")
    )
    named_actions = [a for a in actions if a.focused_ally_target_id == participant.pk]
    anyone_actions = [a for a in actions if a.focused_ally_target_id is None]

    protected = participant.character_sheet.character
    # CombatRoundAction is unique per (participant, round), so the named and
    # guard-anyone tiers never share a guardian, and _standing_guardians leaves out
    # anyone who declared INTERPOSE at all: no guardian is tried twice for one hit.
    for action in named_actions:
        # A false result means this guardian could not attempt (for example, its
        # reaction or technique is unavailable). Only an actual attempt, including
        # a failed roll, ends protector selection.
        if _dispatch_interpose_action(action, protected, pre_payload):
            return
    for guardian in _standing_guardians(participant, protected):
        if _attempt_guardian_interpose(guardian, protected, pre_payload, action=None):
            return
    for action in anyone_actions:
        if _dispatch_interpose_action(action, protected, pre_payload):
            return


def _standing_guardians(
    participant: CombatParticipant,
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM - the ward's own character
) -> list[CombatParticipant]:
    """ACTIVE participants of the ward's encounter standing guard over her, in guard order.

    Guard order is :func:`~world.conditions.services.guardians_by_target`'s (oldest
    instance first). The ward herself is never her own guardian. A guardian who
    declared any INTERPOSE this round is left out: her declaration takes precedence
    and is tried in its own tier (or, naming another ward, not for this hit at all).
    """
    from world.conditions.services import guardians_by_target  # noqa: PLC0415

    guardian_ids = guardians_by_target([protected]).get(protected.pk, [])
    if not guardian_ids:
        return []
    # CharacterSheet shares its character's pk, so character ids match sheet ids.
    declared_interpose = CombatRoundAction.objects.filter(
        participant_id=OuterRef("pk"),
        round_number=participant.encounter.round_number,
        maneuver=CombatManeuver.INTERPOSE,
    )
    by_character = {
        p.character_sheet_id: p
        for p in CombatParticipant.objects.filter(
            encounter_id=participant.encounter_id,
            status=ParticipantStatus.ACTIVE,
            character_sheet_id__in=guardian_ids,
        )
        .exclude(pk=participant.pk)
        .exclude(Exists(declared_interpose))
        .select_related("character_sheet__character")
    }
    return [by_character[pk] for pk in guardian_ids if pk in by_character]


def _try_interpose_for_opponent(
    opponent: CombatOpponent,
    pre_payload: DamagePreApplyPayload,
) -> None:
    """Guardian-shields-a-summon variant of :func:`_try_interpose` (#2207).

    Extends interpose protection to ALLY-allegiance ``CombatOpponent`` wards —
    player summons/companion NPCs fighting on the party's side — so a declared
    guardian can shield them the same way they can shield a PC. No-op when
    *opponent* is not ``allegiance=ALLY`` (an ENEMY opponent is never a ward)
    or when the encounter is not ``RESOLVING`` (mirrors :func:`_try_interpose`).

    **ANY-ALLY only:** ``CombatRoundAction.focused_ally_target`` FKs
    ``CombatParticipant``, so a ``CombatOpponent`` can never be named as a
    *specific* ward — only an armed ``focused_ally_target IS NULL`` (any-ally)
    declaration can pick it up. Named-ally guarding of a summon is a follow-up
    once ``focused_ally_target`` (or a sibling field) can point at an opponent.
    There is no self-interpose check here (unlike :func:`_try_interpose`): the
    interposer is always a ``CombatParticipant`` and the ward is always a
    ``CombatOpponent``, so the two can never be the same row.
    """
    if opponent.allegiance != CombatAllegiance.ALLY:
        return

    encounter = opponent.encounter
    if encounter.status != RoundStatus.RESOLVING:
        return

    action = (
        CombatRoundAction.objects.filter(
            participant__encounter=encounter,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target__isnull=True,
            participant__status=ParticipantStatus.ACTIVE,
        )
        .select_related("participant__character_sheet__character")
        .first()
    )
    if action is None:
        return

    _dispatch_interpose_action(action, pre_payload.target, pre_payload)


def _dispatch_interpose_action(
    action: CombatRoundAction,
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    pre_payload: DamagePreApplyPayload,
) -> bool:
    """Resolve an armed INTERPOSE action and report whether it attempted.

    The declared-guardian entry to :func:`_attempt_guardian_interpose`.
    """
    return _attempt_guardian_interpose(action.participant, protected, pre_payload, action=action)


def _attempt_guardian_interpose(
    guardian: CombatParticipant,
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    pre_payload: DamagePreApplyPayload,
    *,
    action: CombatRoundAction | None,
) -> bool:
    """Have *guardian* try to intercept this hit and report whether she attempted.

    ``action`` is her declared INTERPOSE, or ``None`` for a standing guard
    (``ConditionTemplate.source_guards_bearer``, #4584). A standing guard covers
    player-character wards in combat only (no ALLY summon ward, no out-of-combat
    Sudden Harm) and counts against both budgets exactly as a declaration does
    (ADR-4584-A).

    A false result means the guardian was unavailable and selection may try
    another. A true result includes a failed challenge: once a guardian actually
    attempts, her reaction and this hit's answer budget are consumed and no later
    guardian is retried.
    """
    interposer = guardian.character_sheet.character
    if guardian.reactions_used >= REACTIONS_PER_ROUND:
        _narrate_reaction_declined(interposer, protected, cap=False)
        return False
    if pre_payload.answers_consumed >= ABSORPTION_CAP_PER_MOMENT:
        _narrate_reaction_declined(interposer, protected, cap=True)
        return False

    # Bond combat bonus (#2021): relationship-scaled protection.
    from world.relationships.services import bond_bonus  # noqa: PLC0415

    modifiers = bond_bonus(interposer, protected)

    technique_action = (
        action if action is not None and action.focused_action_id is not None else None
    )
    amount_before = pre_payload.amount
    if technique_action is not None:
        attempted = _try_technique_interpose(
            technique_action,
            interposer,
            protected,
            pre_payload,
            extra_modifiers=modifiers,
        )
        if not attempted:
            return False
    else:
        result = _svc.dispatch_interpose(
            interposer,
            protected,
            pre_payload,
            approach=None,
            extra_modifiers=modifiers,
            select_best_check_rating=True,
        )
        if result is None:
            # No qualifying reaction action is an unavailable guardian, not an
            # attempted failure. Leave both budgets untouched for fallback.
            return False

    if pre_payload.amount < amount_before:
        source_action = action if action is not None else _own_round_action(guardian)
        if source_action is not None:
            _record_story_envoy_rescue(guardian, source_action, protected)

    # Increment both budgets only after a dispatch/technique has truly started.
    # This preserves the fallback path for unavailable guardians while counting
    # failed rolls as real attempts.
    guardian.reactions_used += 1
    guardian.save(update_fields=["reactions_used"])
    pre_payload.answers_consumed += 1

    if technique_action is None:
        # Charge fatigue to the interposer ONLY on fire (readiness is free).
        # Mirror _resolve_pc_action: apply_fatigue(sheet, category, base_cost, effort).
        # A standing guard declared nothing, so she pays physical at very low effort.
        if action is not None:
            fatigue_category = action.focused_category or ActionCategory.PHYSICAL
            effort_level = action.effort_level
        else:
            fatigue_category = ActionCategory.PHYSICAL
            effort_level = EffortLevel.VERY_LOW
        apply_fatigue(
            guardian.character_sheet,
            fatigue_category,
            INTERPOSE_BASE_FATIGUE_COST,
            effort_level,
        )
    return True


def _own_round_action(guardian: CombatParticipant) -> CombatRoundAction | None:
    """The guardian's own declaration this round, if she made one."""
    return CombatRoundAction.objects.filter(
        participant=guardian,
        round_number=guardian.encounter.round_number,
    ).first()


def _guardian_can_fire_technique_interpose(
    anima: CharacterAnima | None, cost: int, *, consented: bool
) -> bool:
    """True when a cost>0 technique-guardian reaction may fire.

    No pool at all means there's nothing to consent with. Otherwise: affordable
    fires unconditionally; unaffordable fires only when consented (#3573), which
    runs the guardian's anima into deficit (:func:`_settle_technique_interpose_cost`
    handles the actual debit).
    """
    if anima is None:
        return False
    return anima.current >= cost or consented


def _try_technique_interpose(
    action: CombatRoundAction,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    pre_payload: DamagePreApplyPayload,
    *,
    extra_modifiers: int = 0,
) -> bool:
    """Resolve a technique-guardian's protective reactive-trigger technique (#2207).

    Runs when ``action.focused_action_id`` is set — the guardian declared a
    known protective technique (``declare_interpose(technique=...)``) instead of
    a plain mundane interpose. Diverges from :func:`dispatch_interpose` in three
    ways:

    1. **Affordability first, unless consented.** Cost is the matched protective
       ``ConditionTemplate.reactive_anima_cost`` (resolved via
       :func:`~world.magic.services.targeting.protective_condition_and_flavor` —
       the same traversal :func:`~world.magic.services.targeting.protective_flavor`
       walks at declaration time, first protective-flavored template wins). Can't
       pay -> the reaction fizzles: NO roll, NO fatigue, NO anima charged,
       damage proceeds unchanged to ``_try_companion_defend`` as today, and
       the guardian and the room are told (#3574,
       :func:`_narrate_technique_interpose_fizzle`). **Unless**
       ``action.confirm_soulfray_risk`` (#3573) is set: a consented guardian
       fires regardless of affordability, running the pool into deficit and
       accruing Soulfray (point 3 below).
    2. **The roll is the guardian's own cast check**
       (:func:`~world.magic.services.magic_skills.resolve_cast_check`: the check
       type plus the technique skill term), rolled
       against the same authored difficulty as the mundane Interpose challenge
       (:data:`~world.combat.interpose_content.INTERPOSE_CHALLENGE_NAME`'s
       ``ChallengeTemplate.severity``) — a technique guardian's protection is
       spellcasting, not martial reflex, so it never touches
       :func:`dispatch_capability_reaction`.
    3. **Cost is anima, not fatigue.** On fire (any non-fizzle resolution) the
       guardian's anima is debited via :func:`~world.magic.services.anima.deduct_anima`
       (mirrors :func:`~world.magic.services.effect_handlers._try_spend_reactive`'s
       debit pattern, minus the ``ConditionInstance`` machinery - the guardian is
       casting live, not carrying a passive buff). No ``INTERPOSE_BASE_FATIGUE_COST``
       is charged on this path. A consented guardian (``confirm_soulfray_risk``,
       #3573) may run the pool into deficit - ``deduct_anima``'s ``lethal`` kwarg
       is threaded from ``action.participant.encounter.is_lethal`` so a non-lethal
       encounter never draws life force - and every consented fire (deficit or
       not) accrues Soulfray via
       :func:`~world.magic.services.soulfray.accumulate_soulfray`. A deficit fire
       also broadcasts a commitment line to the encounter.

    Grading reuses :func:`_grade_interpose_damage` — the SAME clean/partial/fail
    banding (including SHIELD divisor widening) the mundane path uses via
    :func:`apply_interpose_outcome`, so a technique guardian and a mundane
    guardian resolve identically once the check lands.

    **BLINK flavor, clean success only:** relocates *protected* (the ward) to
    *interposer*'s own current position — "you're with me now," out of harm's
    way — via :func:`~world.areas.positioning.services.force_move_to_position`
    (the same unchecked-move primitive
    :func:`~world.magic.services.effect_handlers.blink_dodge` uses). Destination
    is the guardian's own position because this branch predates #2206: once
    ``CombatRoundAction.cast_destination`` lands, queue-time reconciliation
    should prefer that declared destination over the guardian's own position.
    No-op (damage still zeroed) if the guardian isn't currently placed anywhere.

    **REDIRECT flavor (#2210):** after grading, ``saved = amount_before -
    pre_payload.amount`` (whatever the block prevented — full on a clean
    block, half on a partial, zero on a failure) is sent to the declaration's
    destination (``CombatRoundAction.redirect_opponent_target`` /
    ``redirect_object_target`` — see :func:`_resolve_technique_redirect`).
    """
    from world.combat.interpose_content import INTERPOSE_CHALLENGE_NAME  # noqa: PLC0415
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415
    from world.magic.services.magic_skills import resolve_cast_check  # noqa: PLC0415
    from world.magic.services.targeting import (  # noqa: PLC0415
        PROTECTIVE_FLAVOR_BLINK,
        PROTECTIVE_FLAVOR_REDIRECT,
        protective_condition_and_flavor,
    )
    from world.mechanics.models import ChallengeTemplate  # noqa: PLC0415

    technique = action.focused_action

    resolved = protective_condition_and_flavor(technique)
    if resolved is None:
        # declare_interpose already validated this at declaration time; fail
        # safe (damage proceeds unchanged) rather than crash if authored
        # content changed mid-encounter.
        return False
    condition_template, flavor = resolved

    # Affordability first (mirrors _try_spend_reactive's cost<=0 free-fire rule,
    # world/magic/services/effect_handlers.py): a free-cost protective technique
    # never needs a CharacterAnima row to fire. A consented guardian
    # (confirm_soulfray_risk, #3573) bypasses the affordability gate and fires
    # into deficit instead.
    cost = condition_template.reactive_anima_cost
    consented = bool(action.confirm_soulfray_risk)
    anima = None
    if cost > 0:
        anima = CharacterAnima.objects.filter(character_id=interposer.pk).first()
        if not _guardian_can_fire_technique_interpose(anima, cost, consented=consented):
            # Fizzle: no pool at all, or unaffordable and unconsented - no roll,
            # no cost, damage proceeds. Not silent (#3574): the guardian learns
            # their save did not catch, and the table sees a working fail.
            _narrate_technique_interpose_fizzle(action, interposer, protected, technique)
            return False

    severity_template = ChallengeTemplate.objects.filter(name=INTERPOSE_CHALLENGE_NAME).first()
    if severity_template is None:
        # Unseeded content (mirrors _ensure_interpose_challenges' warn-and-skip
        # for the mundane path): fail safe like the resolved-is-None branch
        # above — no roll, no cost, damage proceeds unchanged.
        return False
    severity = severity_template.severity
    cast_check = resolve_cast_check(interposer, technique)
    if cast_check is None:
        # Unprovisioned caster + template-less technique (clash.py guards the
        # same pairing) — fail safe like the resolved-is-None branch above:
        # no roll, no cost, damage proceeds to the next protection layer.
        return False
    # #2536 Task 5 review fix: thread the live round context — action.participant
    # is already dereferenced elsewhere in this function (current_position below),
    # so the plumbing a CHECK_BONUS perk needs is trivially available; skipping it
    # would silently strand a future perk scoped to the guardian's protective
    # technique CheckType. No natural offense `target` exists on a reactive
    # protective roll (there is no opposing actor being checked against), so
    # target stays None — only holder/subject/resolution-keyed situations apply.
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    situation_ctx = SituationContext(
        holder=action.participant.character_sheet,
        subject=action.participant.character_sheet,
        target=None,
        resolution=CombatRoundContext(action.participant),
    )
    check_result = _svc.perform_check(
        interposer,
        cast_check.check_type,
        target_difficulty=severity,
        extra_modifiers=extra_modifiers,
        situation_ctx=situation_ctx,
        extra_traits=cast_check.extra_traits,
    )

    # Debit on fire (any non-fizzle resolution) - anima, not fatigue. A consented
    # guardian may run into deficit and accrues Soulfray on every fire (#3573).
    if cost > 0:
        # The earlier affordability gate already returned if cost > 0 and anima
        # was None, so anima is guaranteed set here.
        assert anima is not None  # noqa: S101  # type narrowing for ty
        _settle_technique_interpose_cost(
            action,
            interposer,
            protected,
            anima=anima,
            cost=cost,
            consented=consented,
            check_result=check_result,
        )

    amount_before = pre_payload.amount
    is_clean_block = _grade_interpose_damage(
        pre_payload, check_result.success_level, interposer=interposer
    )

    if is_clean_block and flavor == PROTECTIVE_FLAVOR_BLINK:
        from world.areas.positioning.services import force_move_to_position  # noqa: PLC0415

        dest = action.participant.current_position
        if dest is not None:
            force_move_to_position(protected, dest)

    if flavor == PROTECTIVE_FLAVOR_REDIRECT:
        saved = amount_before - pre_payload.amount
        _resolve_technique_redirect(action, interposer, saved, damage_type=pre_payload.damage_type)
    return True


def _resolve_technique_redirect(
    action: CombatRoundAction,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    saved: int,
    *,
    damage_type: DamageType | None,
) -> None:
    """Resolve a REDIRECT-flavor guardian's saved damage into its destination (#2210).

    ``saved`` is whatever :func:`_grade_interpose_damage` prevented from landing on
    the ward — full amount on a clean block, half on a partial, zero on a failure.
    ``saved <= 0`` means nothing redirects (a failed block has nothing to send
    anywhere). Otherwise dispatches per the declaration
    (``CombatRoundAction.redirect_opponent_target`` / ``redirect_object_target``,
    set by :func:`declare_interpose`); both null (or a destination that's no
    longer valid at resolution time — the target defeated, the object moved or
    already consumed) degrades to "away," the universal fallback.
    """
    if saved <= 0:
        return

    encounter = action.participant.encounter
    opponent = action.redirect_opponent_target
    obj = action.redirect_object_target

    if opponent is not None:
        if opponent.status == OpponentStatus.ACTIVE:
            _redirect_to_opponent(encounter, interposer, opponent, saved, damage_type=damage_type)
        else:
            _redirect_away(encounter, interposer)
        return

    if obj is not None:
        from world.mechanics.services import volatile_object_property  # noqa: PLC0415

        obj_property = volatile_object_property(obj)
        if obj.db_location_id == encounter.room_id and obj_property is not None:
            _redirect_to_object(encounter, interposer, obj, obj_property)
        else:
            _redirect_away(encounter, interposer)
        return

    _redirect_away(encounter, interposer)


def _redirect_to_opponent(
    encounter: CombatEncounter,
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    opponent: CombatOpponent,
    saved: int,
    *,
    damage_type: DamageType | None,
) -> None:
    """Apply the saved damage to the declared chosen-enemy opponent and broadcast it."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    _svc.apply_damage_to_opponent(opponent, saved, bypass_pre_apply=True, damage_type=damage_type)
    narration = f"{interposer.db_key} hurls the blow back — it slams into {opponent.name}!"
    broadcast_action_outcome(encounter=encounter, narration=narration)


def dispatch_interpose(  # noqa: PLR0913 - select_best_check_rating extends existing signature
    interposer: ObjectDB,  # noqa: OBJECTDB_PARAM
    protected: ObjectDB,  # noqa: OBJECTDB_PARAM
    pre_payload: DamagePreApplyPayload,
    *,
    approach: str | None,
    extra_modifiers: int = 0,
    select_best_check_rating: bool = False,
) -> ChallengeResolutionResult | None:
    """Resolve *interposer*'s interpose attempt and apply the graded outcome.

    Thin wrapper over :func:`~world.mechanics.reactions.dispatch_capability_reaction`:
    looks up the active Interpose :class:`~world.mechanics.models.ChallengeInstance`
    bound to *protected*, resolves it through *interposer*'s capabilities, and
    calls :func:`apply_interpose_outcome` to mutate *pre_payload* in place.

    *select_best_check_rating* (#2207) opts into the best-of-check reaction-action
    selection (Reflexes vs. the Melee-Defense twin) when *approach* is ``None`` —
    passed ``True`` by :func:`_try_interpose` (the combat damage path). Default
    ``False`` preserves the plain first-match behavior for the scene-cover caller
    (``world.scenes.sudden_harm``), which passes ``approach=None`` unchanged.

    Returns the :class:`~world.mechanics.types.ChallengeResolutionResult`, or
    ``None`` when no active Interpose challenge is bound to *protected* or
    *interposer* has no qualifying approach.
    """
    import functools  # noqa: PLC0415

    from world.combat.interpose_content import INTERPOSE_CHALLENGE_NAME  # noqa: PLC0415
    from world.mechanics.reactions import dispatch_capability_reaction  # noqa: PLC0415

    return dispatch_capability_reaction(
        interposer,
        protected,
        challenge_name=INTERPOSE_CHALLENGE_NAME,
        approach=approach,
        error_msg=(
            f"No interpose approach is available to {interposer!r} "
            f"for protected target {protected!r}."
        ),
        outcome_fn=functools.partial(apply_interpose_outcome, pre_payload, interposer=interposer),
        select_best_check_rating=select_best_check_rating,
        extra_modifiers=extra_modifiers,
    )


def _fire_rampart_retaliation(
    profile: RampartElementProfile,
    attacker_ref: object | None,
) -> None:
    """MELEE_RETALIATION signature: burn a melee striker's CombatOpponent back.

    Mirrors ``reflect_damage`` (world/magic/services/effect_handlers.py) —
    ``bypass_pre_apply=True`` terminates re-emission so the retaliation strike
    cannot itself trigger another rampart interception or reflect loop. Never
    retaliates against a PC (ADR-0023): a no-op unless ``attacker_ref``
    resolves to a ``CombatOpponent``.
    """
    if not isinstance(attacker_ref, CombatOpponent):
        return
    if profile.signature_value <= 0:
        return
    _svc.apply_damage_to_opponent(
        attacker_ref,
        profile.signature_value,
        bypass_pre_apply=True,
        damage_type=profile.signature_damage_type,
    )


def _rampart_resist(
    profile: RampartElementProfile,
    damage_type: DamageType | None,
    *,
    delivery: str,
    is_area: bool,
) -> int:
    """The resist term for one intercepted strike: base row + MISSILE_WARD adjustment."""
    from world.areas.positioning.constants import RampartSignature  # noqa: PLC0415

    resist = 0
    if damage_type is not None:
        resist = sum(
            profile.resistances.filter(damage_type=damage_type).values_list("value", flat=True)
        )
    if profile.signature_behavior == RampartSignature.MISSILE_WARD:
        if delivery == StrikeDelivery.MISSILE:
            resist += profile.signature_value
        if is_area:
            resist -= profile.signature_value
    return resist


def apply_rampart_interception(  # noqa: PLR0913
    character_or_opponent: Character,  # noqa: OBJECTDB_PARAM - ObjectDB target, mirrors apply_position_cover
    damage: int,
    damage_type: DamageType | None,
    *,
    attacker_ref: object | None,
    delivery: str = StrikeDelivery.MELEE,
    is_area: bool = False,
) -> int:
    """Intercept a strike against a rampart-covered position (#2209).

    Resolves the target's Position via the same lookup ``apply_position_cover``
    uses. No-op (damage passes through unchanged) when the target is
    unpositioned, has no Rampart, or the strike is a sustained attack already
    being drained by an active WARD Clash bound to this rampart — the
    no-double-drain rule; the clash drains instead.

    Math: resist is the profile's resistance row for ``damage_type`` (0 if
    untyped or absent); a MISSILE_WARD profile additionally adds
    ``signature_value`` against MISSILE delivery and subtracts it against area
    strikes. ``chip = max(1, damage - resist)`` (a min-1 floor so barrages
    always crack the rampart). A chip that doesn't clear the rampart's
    remaining integrity fully absorbs the strike (returns 0); a chip that
    clears it collapses the rampart and lets the overflow remainder through.

    Fires MELEE_RETALIATION on interception for a melee strike. GRASPING is
    handled at the forced-move landing seam (``force_move_to_position``), not
    here.

    Returns the damage that should continue through the normal pipeline.
    """
    if damage <= 0:
        return damage
    from world.areas.positioning.constants import RampartSignature  # noqa: PLC0415
    from world.areas.positioning.services import (  # noqa: PLC0415
        damage_rampart,
        position_of,
        rampart_at,
    )

    position = position_of(character_or_opponent)
    if position is None:
        return damage
    rampart = rampart_at(position)
    if rampart is None:
        return damage

    # No-double-drain: a sustained attack already draining via an active WARD
    # clash bound to this rampart skips interception entirely.
    from world.combat.constants import ClashStatus  # noqa: PLC0415

    active_ward = Clash.objects.filter(
        rampart=rampart, flavor=ClashFlavor.WARD, status=ClashStatus.ACTIVE
    ).exists()
    if active_ward:
        return damage

    profile = rampart.element_profile
    resist = _rampart_resist(profile, damage_type, delivery=delivery, is_area=is_area)
    chip = max(1, damage - resist)

    if chip < rampart.integrity:
        damage_rampart(rampart, chip)
        pass_through = 0
    else:
        overflow = chip - rampart.integrity
        damage_rampart(rampart, chip)
        pass_through = min(damage, overflow)

    if delivery == StrikeDelivery.MELEE and profile.signature_behavior == (
        RampartSignature.MELEE_RETALIATION
    ):
        _fire_rampart_retaliation(profile, attacker_ref)

    return pass_through
