"""Declaring and resolving flight."""

from __future__ import annotations

from world.checks.constants import ModifierSourceKind
from world.checks.types import ModifierContribution
from world.combat import services as _svc
from world.combat.constants import (
    ENTITY_TYPE_PC,
    FLEE_PARTIAL_SUCCESS_LEVEL,
    CombatManeuver,
    EngagementLockStatus,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.models import (
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    EngagementLock,
    FleeTierModifier,
)
from world.combat.services.declarations.social_check import _record_combat_consequence
from world.combat.services.encounter.config import get_flee_config
from world.combat.types import ActionOutcome
from world.conditions.services import spend_contributing_conditions
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus


def declare_flee(participant: CombatParticipant) -> CombatRoundAction:
    """Declare intent to flee -- passives-only maneuver, auto-ready.

    Creates or replaces the current round's CombatRoundAction with no
    focused action and maneuver=FLEE. Flee resolves as a real check at
    round resolution (_resolve_flee); the participant remains ACTIVE until
    the check succeeds.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter

    # Encounter status check
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot flee: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot flee: participant is no longer active in this encounter."
        raise ValueError(msg)

    # Vitality check — dead characters cannot flee. Unconscious / dying
    # characters may still be dragged out (flee is passives-only).
    if is_dead(participant.character_sheet):
        msg = "Cannot flee: character is dead."
        raise ValueError(msg)
    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.FLEE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


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
        # A strained compulsion resist (#4802) lands its penalty on the flee roll.
        extra_modifiers=breakdown.extra_modifiers_total - action.compulsion_penalty,
    )
    spend_contributing_conditions(breakdown)

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
