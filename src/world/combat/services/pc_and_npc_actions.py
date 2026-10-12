"""PC flee and cast broadcasts, NPC action helpers, and per-round boss transitions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.checks.constants import ModifierSourceKind
from world.checks.types import ModifierContribution
from world.combat import services as _svc
from world.combat.constants import (
    ENTITY_TYPE_PC,
    FLEE_PARTIAL_SUCCESS_LEVEL,
    HELD_BACK_NARRATION,
    CombatManeuver,
    EncounterOutcome,
    EngagementLockStatus,
    OpponentStatus,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    EngagementLock,
    FleeTierModifier,
    SustainedAction,
)
from world.combat.services.boss_and_social import (
    _record_combat_consequence,
    check_and_advance_boss_phase,
)
from world.combat.services.declare_action import (
    _broadcast_sustained_broken,
    _dual_dispatch_combat_narration,
)
from world.combat.services.foundations import get_flee_config
from world.combat.types import ActionOutcome, CombatTechniqueResolution, CombatTechniqueResult

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Technique
    from world.magic.services.cast_observation import CastAudience

logger = logging.getLogger(__name__)


def _resolve_flee(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a declared flee as a graded check (#878).

    Difficulty = FleeConfig.base_difficulty + max(FleeTierModifier over active
    opponents' tiers); zero active opponents → tier term 0 (no auto-success).
    Each same-round COVER declaration by an ACTIVE participant whose
    focused_ally_target is this participant adds FleeConfig.cover_bonus.

    Graded outcome by success_level: PARTIAL (-1) or better escapes
    (status → FLED); PARTIAL and below applies the selected pool consequence
    (PARTIAL = escape at a cost; FAILURE/BOTCH = stays ACTIVE). Botch severity
    is authored in the pool's BOTCH-tier entries, not special-cased here.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        resolve_pool_consequences,
        select_consequence,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))
    config = get_flee_config()
    encounter = participant.encounter

    # Difficulty: base + the single worst (max) modifier among active
    # opponents' tiers. One values_list + one filter — no queries in loops.
    active_tiers = set(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        ).values_list("tier", flat=True)
    )
    tier_modifiers = dict(
        FleeTierModifier.objects.filter(tier__in=active_tiers).values_list(
            "tier", "difficulty_modifier"
        )
    )
    tier_term = max((tier_modifiers.get(tier, 0) for tier in active_tiers), default=0)
    difficulty = config.base_difficulty + tier_term

    # Cover: one COUNT over this round's COVER declarations targeting the fleer.
    cover_count = CombatRoundAction.objects.filter(
        participant__encounter=encounter,
        participant__status=ParticipantStatus.ACTIVE,
        round_number=action.round_number,
        maneuver=CombatManeuver.COVER,
        focused_ally_target=participant,
    ).count()

    # Route the cover bonus through the shared modifier seam (the same idiom
    # as effort in CombatTechniqueResolver._roll_check) so the recorded
    # provenance carries a labeled "covering allies" contribution.
    extra_contributions: list[ModifierContribution] = []
    if cover_count:
        extra_contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.CHARACTER,
                source_label=f"Covering allies x{cover_count}",
                value=config.cover_bonus * cover_count,
            )
        )
    # Bond combat bonus (#2021): relationship co-combatant passive.
    from world.relationships.services import bond_combat_bonus  # noqa: PLC0415

    extra_contributions.extend(bond_combat_bonus(participant.character_sheet, encounter))
    breakdown = _svc.collect_check_modifiers(
        participant.character_sheet,
        config.check_type,
        scene=encounter.scene,
        extra_contributions=extra_contributions,
    )

    consequences = (
        resolve_pool_consequences(config.consequence_pool)
        if config.consequence_pool_id is not None
        else []
    )
    character = participant.character_sheet.character
    pending = select_consequence(
        character,
        config.check_type,
        difficulty,
        consequences,
        extra_modifiers=breakdown.total,
    )

    success_level = pending.check_result.success_level
    escaped = success_level >= FLEE_PARTIAL_SUCCESS_LEVEL
    consequence_applies = success_level <= FLEE_PARTIAL_SUCCESS_LEVEL

    if escaped:
        participant.status = ParticipantStatus.FLED
        participant.save(update_fields=["status"])

        # Release any active engagement lock the fleeing PC held (#3386):
        # fleeing shouldn't leave a phantom pairing behind.
        from world.combat.constants import LockBreakReason  # noqa: PLC0415
        from world.combat.engagement_locks import break_engagement_lock  # noqa: PLC0415

        active_lock = EngagementLock.objects.filter(
            participant=participant,
            status=EngagementLockStatus.ACTIVE,
        ).first()
        if active_lock is not None:
            break_engagement_lock(active_lock, reason=LockBreakReason.FLEE)

        # Combat-owned engagement teardown on successful flee (#872).
        from world.mechanics.constants import EngagementType  # noqa: PLC0415
        from world.mechanics.services import end_engagement  # noqa: PLC0415

        end_engagement(
            participant.character_sheet.character,
            EngagementType.COMBAT,
            source=participant.encounter,
        )

    # ACTION-mode Interaction anchor + live broadcast (mirrors the tail of
    # _resolve_pc_action).
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        create_action_interaction,
        render_flee_outcome_narration,
    )
    from world.scenes.interaction_services import push_interaction  # noqa: PLC0415

    interaction = create_action_interaction(
        participant=participant,
        round_number=action.round_number,
        summary_label="Flee",
    )
    if interaction is not None:
        action.interaction = interaction
        action.interaction_timestamp = interaction.timestamp
        action.save(update_fields=["interaction", "interaction_timestamp"])
        push_interaction(interaction)

    if consequence_applies and config.consequence_pool_id is not None:
        apply_resolution(pending, ResolutionContext(character=character))
        _record_combat_consequence(
            participant.character_sheet,
            config.check_type,
            config.consequence_pool,
            pending,
            breakdown,
            interaction=interaction,
            summary="flee attempt",
        )

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    narration = render_flee_outcome_narration(
        # The persona this PC is CURRENTLY presenting as, not str(participant)
        # -> "Sheet for {key}" (#4091 fix round 2). One call per action, not a
        # per-participant loop.
        actor_label=active_persona_for_sheet(participant.character_sheet).name,
        escaped=escaped,
        at_cost=escaped and consequence_applies,
    )
    broadcast_action_outcome(encounter=encounter, narration=narration)

    return outcome


def _record_and_broadcast_pc_action(  # noqa: PLR0913
    *,
    participant: CombatParticipant,
    action: CombatRoundAction,
    technique: Technique,
    target: CombatOpponent | None,
    outcome: ActionOutcome,
    combat_result: CombatTechniqueResult | None,
) -> None:
    """Record the ACTION-mode Interaction and broadcast the outcome narration."""
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        create_action_interaction,
        render_action_declaration_label,
        render_action_outcome_narration,
        render_unattributed_action_narration,
        target_persona_for_round_action,
    )
    from world.scenes.interaction_services import push_interaction  # noqa: PLC0415

    audience = _resolve_combat_cast_audience(participant, technique)

    # #3787 Task 5 - who this action was about. focused_ally_target's persona
    # when the declared target was an ally; None for an NPC opponent target (no
    # Persona behind an NPC - correct, not a gap) or no target at all.
    target_persona = target_persona_for_round_action(action)
    target_personas = [target_persona] if target_persona is not None else None

    # Only the attack path returns a CombatTechniqueResult (which carries fury);
    # the non-attack path returns a CombatTechniqueResolution with no fury field.
    fury_committed = (
        combat_result.fury_committed if isinstance(combat_result, CombatTechniqueResult) else None
    )
    interaction = create_action_interaction(
        participant=participant,
        round_number=action.round_number,
        summary_label=render_action_declaration_label(action),
        strain_committed=(
            combat_result.declared_strain_commitment
            if isinstance(combat_result, CombatTechniqueResult)
            else 0
        ),
        strain_effective=(
            combat_result.effective_strain_commitment
            if isinstance(combat_result, CombatTechniqueResult)
            else 0
        ),
        strain_power_bonus=(
            combat_result.strain_power_bonus
            if isinstance(combat_result, CombatTechniqueResult)
            else 0
        ),
        fury_committed=fury_committed,
        target_personas=target_personas,
    )
    if interaction is not None:
        action.interaction = interaction
        action.interaction_timestamp = interaction.timestamp
        action.save(update_fields=["interaction", "interaction_timestamp"])
        if audience.concealed:
            # Before push_interaction, which reads .visibility to decide whether to
            # broadcast room-wide. Concealing after the push would leak the technique
            # name live and hide it only on scene-log re-read.
            from world.magic.services.cast_observation import (  # noqa: PLC0415
                conceal_action_interaction,
            )

            conceal_action_interaction(interaction, audience)
        push_interaction(interaction)
        if combat_result is not None:
            from world.scenes.power_ledger_services import persist_power_ledger  # noqa: PLC0415

            persist_power_ledger(interaction=interaction, ledger=combat_result.power_ledger)

    from world.magic.services.signature_effects import resolve_signature_snippet  # noqa: PLC0415
    from world.magic.services.technique_personalization import (  # noqa: PLC0415
        paid_price_snippet,
        technique_display_name,
    )
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    target_label = target.name if target is not None else None
    caster_character = participant.character_sheet.character
    signature_snippet = resolve_signature_snippet(caster_character, technique)
    # #4099: the price THIS resolved cast paid (use_technique's one decision, made at
    # resolution, not declaration), never the hold's price.
    price_snippet = paid_price_snippet(
        combat_result.technique_use_result.price_paid
        if isinstance(combat_result, CombatTechniqueResult)
        else None
    )
    interaction_result = next(
        (dr.damage_interaction for dr in outcome.damage_results if dr.damage_interaction),
        None,
    )
    narration = render_action_outcome_narration(
        # The persona this PC is CURRENTLY presenting as, not str(participant)
        # -> "Sheet for {key}" (#4091 fix round 2). One call per action.
        actor_label=active_persona_for_sheet(participant.character_sheet).name,
        technique_name=technique_display_name(caster_character, technique),
        target_label=target_label,
        outcome=outcome,
        power_ledger=combat_result.power_ledger if combat_result is not None else None,
        signature_snippet=signature_snippet,
        price_snippet=price_snippet,
        interaction_result=interaction_result,
        hit_text=technique.hit_narration,
        miss_text=technique.miss_narration,
    )
    # Rendered unconditionally rather than under `if audience.concealed`: it is a pure
    # string build over data already in hand, and branching here would put the
    # concealment decision in two places.
    unattributed_narration = render_unattributed_action_narration(
        target_label=target_label, outcome=outcome
    )
    broadcast_action_outcome(
        encounter=participant.encounter,
        narration=narration,
        audience=audience,
        unattributed_narration=unattributed_narration,
        target_personas=target_personas,
    )


def _resolve_combat_cast_audience(
    participant: CombatParticipant,
    technique: Technique,
) -> CastAudience:
    """Who perceived this action, and how much of it they could attribute (#2734).

    Delegates to the shipped #2710 service, which early-returns an unconcealed
    audience — no queries, no checks — whenever attribution cannot be hidden: a
    SAME-reach technique (you are standing on your target), or a caster whose style
    imposes no concealment. That is the overwhelmingly common case, and the reason an
    ordinary encounter costs nothing extra.
    """
    from world.magic.services.cast_observation import resolve_cast_audience  # noqa: PLC0415

    # No cast_openly equivalent in combat: CombatRoundAction has no such field, so a
    # combat cast always resolves at the caster's style concealment. A deliberate
    # in-combat reveal is its own UX surface (out of scope, #2734).
    return resolve_cast_audience(caster=participant.character_sheet.character, technique=technique)


def _maybe_suggest_entrance_dramatic_moment(
    participant: CombatParticipant,
    combat_result: CombatTechniqueResult,
) -> None:
    """Fire the #2183 dramatic-moment suggestion for a resolved entrance-declared cast.

    The combat-round sibling of ``run_entrance_success_hooks``'s suggestion half —
    fired here (not at declaration time) because the real success level is only known
    once the declared cast actually resolves. Best-effort: a suggestion failure must
    never break round resolution.
    """
    if not combat_result.technique_use_result.confirmed:
        return
    resolution = combat_result.technique_use_result.resolution_result
    if not isinstance(resolution, CombatTechniqueResolution):
        return
    try:
        from world.magic.services.gain import maybe_suggest_dramatic_moments  # noqa: PLC0415

        maybe_suggest_dramatic_moments(
            character_sheet=participant.character_sheet,
            scene=participant.encounter.scene,
            success_level=resolution.check_result.success_level,
            interaction=None,
        )
    except Exception:
        logger.exception(
            "Failed to suggest a dramatic moment for entrance-declared cast (participant_id=%s)",
            participant.pk,
        )


def _maybe_produce_insight_for_cast(
    participant: CombatParticipant,
    combat_result: CombatTechniqueResult,
    technique: Technique,
) -> None:
    """Fire the #2645 Insight rider after a successful combat cast resolution.

    Mirrors ``_maybe_suggest_entrance_dramatic_moment``'s isolation: an
    Insight failure must never break round resolution. Also mirrors
    ``_record_and_broadcast_pc_action``'s ``isinstance`` guard — only the
    attack path returns a full ``CombatTechniqueResult`` (which carries
    ``technique_use_result``); a routing-isolation test double (or a future
    non-attack path) can hand back a bare ``CombatTechniqueResolution``.
    """
    if not isinstance(combat_result, CombatTechniqueResult):
        return
    if not combat_result.technique_use_result.confirmed:
        return
    try:
        from world.covenants.insight import maybe_produce_insight  # noqa: PLC0415

        maybe_produce_insight(
            caster_sheet=participant.character_sheet,
            technique=technique,
            resolution_participant=participant,
        )
    except Exception:
        logger.exception(
            "Failed to produce an Insight for a combat cast (participant_id=%s)",
            participant.pk,
        )


def _maybe_create_weakness_selection_for_cast(
    participant: CombatParticipant,
    combat_result: CombatTechniqueResult,
    technique: Technique,
    target_opponent: CombatOpponent | None,
) -> None:
    """Fire the #2665 weakness-reading rider after a successful combat cast.

    Mirrors ``_maybe_produce_insight_for_cast``'s isolation: a weakness-
    reading failure must never break round resolution.
    """
    if not isinstance(combat_result, CombatTechniqueResult):
        return
    if not combat_result.technique_use_result.confirmed:
        return
    try:
        from world.covenants.weakness import maybe_create_weakness_selection  # noqa: PLC0415

        maybe_create_weakness_selection(
            caster_sheet=participant.character_sheet,
            technique=technique,
            resolution_participant=participant,
            target_opponent=target_opponent,
        )
    except Exception:
        logger.exception(
            "Failed to create a weakness selection for a combat cast (participant_id=%s)",
            participant.pk,
        )


def _attempt_allegiance_breaks_for_action(
    participant: CombatParticipant, outcome: ActionOutcome
) -> None:
    """#4091 Decision 16, fix round 1: one break-attempt roll per opponent per PC
    action, not per damage call.

    ``outcome.damage_results`` at the point this is called (from
    ``_resolve_pc_action``, right after the technique pipeline AND any combo
    rider have both run, before the wind-up interception rider) holds every
    ``OpponentDamageResult`` this single PC action produced — every damage
    profile against every target, plus the combo rider's own hit. Grouping by
    ``opponent_id`` and summing ``damage_dealt`` gives the blow's TOTAL pressure
    against each opponent it actually harmed, so a multi-profile technique or a
    combo-upgraded hit rolls exactly once per opponent, against the combined
    damage -- never once per profile (previously inside ``apply_damage_to_opponent``
    itself, which fired, and narrated a "holds" line, on every single profile/
    rider call).

    Only a PC's own chosen strike reaches here (this function is called only
    from ``_resolve_pc_action``) -- NPC-vs-NPC (``_resolve_npc_action_on_opponent_
    target``), reflected, rampart, and duel-mirror damage never do.
    """
    from world.npc_services.allegiance import (  # noqa: PLC0415
        allegiance_instances_for,
        designating_instance,
    )
    from world.npc_services.allegiance_outcomes import attempt_allegiance_break  # noqa: PLC0415

    totals: dict[int, int] = {}
    for result in outcome.damage_results:
        opponent_id = result.opponent_id
        if opponent_id is None or result.damage_dealt <= 0:
            continue
        totals[opponent_id] = totals.get(opponent_id, 0) + result.damage_dealt
    if not totals:
        return

    # Batched (#4091 final review): one opponent fetch and one allegiance-instance
    # fetch for every harmed opponent, not a SELECT plus get_active_conditions each.
    opponents = [
        opponent
        for opponent in CombatOpponent.objects.filter(pk__in=totals)
        .exclude(status=OpponentStatus.DEFEATED)
        .select_related("objectdb")
        .order_by("pk")
        if opponent.objectdb_id is not None
    ]
    by_target = allegiance_instances_for(o.objectdb_id for o in opponents)
    for opponent in opponents:
        instance = designating_instance(by_target.get(opponent.objectdb_id, []))
        if instance is None:
            continue
        attempt_allegiance_break(
            striker=participant.character_sheet,
            opponent=opponent,
            damage_dealt=totals[opponent.pk],
            instance=instance,
        )


def _maybe_record_npc_regard_on_defeat(
    participant: CombatParticipant,
    action: CombatRoundAction,
    target: CombatOpponent | None,
    outcome: ActionOutcome,
) -> None:
    """Record a PC_FOILED_NPC_PLAN regard event when a PC defeats a notable NPC.

    #2039 — a persona-backed NPC opponent defeated by a PC records a regard
    event. A mook/persona-less opponent's defeat is deliberately a no-op.
    """
    if target is None or target.persona_id is None:
        return
    defeated = any(
        dr.opponent_id == target.pk and dr.defeated
        for dr in outcome.damage_results
        if hasattr(dr, "opponent_id")
    )
    if not defeated:
        return
    from world.npc_services.constants import NpcRegardEventReason  # noqa: PLC0415
    from world.npc_services.regard import (  # noqa: PLC0415
        get_regard_event_config,
        record_npc_regard_event,
    )
    from world.scenes.models import Persona  # noqa: PLC0415

    try:
        pc_persona = participant.character_sheet.primary_persona
    except Persona.DoesNotExist:
        pc_persona = None
    if pc_persona is not None:
        cfg = get_regard_event_config()
        record_npc_regard_event(
            holder_persona=target.persona,
            target=pc_persona,
            amount=cfg.combat_defeat_amount,
            reason=NpcRegardEventReason.PC_FOILED_NPC_PLAN,
            source_pc_combat_action=action,
        )


def _npc_action_target_label(
    label_targets: list[CombatParticipant] | list[CombatOpponent],
) -> str | None:
    """Join display labels for an NPC action's targets, batched (#4091 fix round 3).

    ``label_targets`` holds either PC ``CombatParticipant``s (the normal
    PC-facing path) or NPC ``CombatOpponent``s (the ALLY-summon/charmed-NPC
    opponent-target path) — never a mix. A PC target gets its persona name
    (never ``str(CombatParticipant)``'s ``"Sheet for {key}"``); an opponent
    target's ``.name`` was already correct.
    """
    if not label_targets:
        return None
    if isinstance(label_targets[0], CombatParticipant):
        from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

        persona_names = persona_names_for_sheets(p.character_sheet_id for p in label_targets)
        names = [
            persona_names.get(p.character_sheet_id, p.character_sheet.character.key)
            for p in label_targets
        ]
    else:
        names = [t.name for t in label_targets]
    return ", ".join(names)


def _allegiance_credit_sheet(
    opponent: CombatOpponent, encounter: CombatEncounter
) -> CharacterSheet | None:
    """Who gets damage/defeat credit for an NPC fighting on the party's behalf (#4091).

    A summon credits its summoner. A charmed or turned NPC credits the PC who applied
    the designating allegiance condition, only while that PC is an ACTIVE participant.
    """
    if opponent.summoned_by_id is not None:
        return opponent.summoned_by
    if opponent.objectdb_id is None:
        return None

    from world.npc_services.allegiance import allegiance_instance_on  # noqa: PLC0415

    instance = allegiance_instance_on(opponent.objectdb)
    if instance is None or instance.source_character_id is None:
        return None
    participant = (
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
            character_sheet__character_id=instance.source_character_id,
        )
        .select_related("character_sheet")
        .first()
    )
    return participant.character_sheet if participant is not None else None


def _narrate_held_back(
    encounter: CombatEncounter,
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],
    pc_actions: dict[int, CombatRoundAction],
    sustaining_participant_ids: frozenset[int],
) -> None:
    """Name every PC the resolve loop skipped for having declared nothing (#3552).

    Only under TIMED and MANUAL pace: READY cannot resolve until every ACTIVE
    participant has readied a ``CombatRoundAction``, so a silent skip is
    impossible there. A participant who declared a ``SustainedAction`` this
    round is committing, not holding back.
    """
    if encounter.pace_mode not in (PaceMode.TIMED, PaceMode.MANUAL):
        return
    for entity_type, entity in resolution_order:
        if entity_type != ENTITY_TYPE_PC or not isinstance(entity, CombatParticipant):
            continue
        if entity.pk in sustaining_participant_ids or entity.pk in pc_actions:
            continue
        name = str(entity.character_sheet.character)
        _dual_dispatch_combat_narration(encounter, HELD_BACK_NARRATION.format(name=name))


def _check_boss_transitions(
    encounter: CombatEncounter,
) -> list[tuple[CombatOpponent, int]]:
    """Check all active bosses for phase transitions, return transitions."""
    transitions: list[tuple[CombatOpponent, int]] = []
    boss_opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
            tier=OpponentTier.BOSS,
        )
    )
    for boss in boss_opponents:
        boss.refresh_from_db()
        new_phase = check_and_advance_boss_phase(boss)
        if new_phase is not None:
            transitions.append((boss, new_phase.phase_number))
    return transitions


def _break_pending_sustained_actions(encounter: CombatEncounter) -> None:
    """Break every still-pending PC ``SustainedAction`` when its encounter ends early.

    Neither ``complete_encounter`` nor this function used to clear
    ``SustainedAction`` rows: an encounter that completes (victory, defeat,
    flee, GM-abandoned) before a commitment's ``resolves_round`` ever arrives
    left the row orphaned forever — it never matures, never narrates, and
    (RITUAL kind) its already-consumed components bought nothing (#2705
    adversarial review, Fix 3). Mirrors the "cost stands" ruling
    ``_mature_one_sustained_action`` applies to a downgrades-exceeded break —
    nothing is refunded here either, only broadcast + delete.

    Called from ``cleanup_completed_encounter``, not ``complete_encounter``
    directly: every production completion path (round-resolution auto-complete,
    the GM end endpoint via ``end_encounter``, duel completion) funnels through
    ``complete_encounter``, which unconditionally calls
    ``cleanup_completed_encounter`` — the same seam that already tears down
    every other encounter-scoped commitment (Audere, engagements, escalation
    triggers, UNTIL_END_OF_COMBAT conditions). Traced, not guessed: the only
    other callers of ``cleanup_completed_encounter`` are tests exercising it in
    isolation.

    ``PendingOpponentAttack`` (the NPC mirror) has the same pre-existing gap —
    deliberately NOT fixed here: out of scope for this issue, and it has no
    consumed-cost consequence (an NPC wind-up never spends anything at
    declaration the way a sustained ritual's components do).
    """
    rows = list(
        SustainedAction.objects.filter(encounter=encounter).select_related(
            "participant__character_sheet__character", "ritual", "technique"
        )
    )
    for sustained in rows:
        _broadcast_sustained_broken(sustained)
        sustained.delete()


def _cancel_pending_certain_death_if_abandoned(
    encounter: CombatEncounter, participants: list[CombatParticipant]
) -> None:
    """Abandoned encounters cancel any pending certain death (#4098 owner ruling).

    A GM closing a broken fight shouldn't kill anyone. The caller
    (``cleanup_completed_encounter``) MUST run this before ending Audere/Audere
    Majora: removing that condition there (via ``end_audere``/``end_audere_majora``
    -> ``remove_condition``) reaches ``_resolve_deferred_death_on_expiry``
    (``world/conditions/services.py``), which applies a pending certain death the
    instant the last deferring condition is gone — before this function's own
    caller's backstop loop (further down in ``cleanup_completed_encounter``) ever
    runs. A no-op for every other outcome (VICTORY/DEFEAT/FLED), which still apply
    the death through the ordinary seam or that backstop.
    """
    if encounter.outcome != EncounterOutcome.ABANDONED:
        return

    from world.vitals.services import clear_pending_certain_death  # noqa: PLC0415

    for participant in participants:
        clear_pending_certain_death(participant.character_sheet)
