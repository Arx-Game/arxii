"""Boss break-bar assessment and per-round events."""

from __future__ import annotations

from world.combat.constants import (
    BREAK_NOVELTY_MULTIPLIER,
    ENTITY_TYPE_PC,
    BreakContributionKind,
    OpponentStatus,
    OpponentTier,
)
from world.combat.models import (
    BreakBarContribution,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
)
from world.combat.services.boss.break_bar_contributions import (
    _boss_new_debuff_events,
    _newly_suppressed_lieutenants,
    _pc_lock_hold_contributors,
)
from world.combat.services.boss.reinforcements import _active_reinforcer_count
from world.combat.services.boss.story_recognition import _record_story_break_recognition
from world.combat.types import ActionOutcome


def assess_break_bar(
    encounter: CombatEncounter,
    action_outcomes: list[ActionOutcome],
) -> None:
    """Assess break-bar depletion for all boss opponents with a break bar (#2642).

    Diversity-weighted, not per-hit: five feeds (DAMAGE / COMBO / HOLD / DEBUFF /
    SUPPRESSION — ``BreakContributionKind``) are each persisted as a
    ``BreakBarContribution`` row. Depletion sums 1 unit per distinct (actor, kind)
    pair this round, doubled for a pair's first-ever (kind, effect_type)
    occurrence in the encounter, plus the landed combo's flat ``bonus_damage``.
    The result is divided by ``1 + active_unsuppressed_reinforcers`` (the
    lieutenant gate) — floored at 1 unit whenever any depletion occurred, never
    a hard block. When the bar reaches 0, the vulnerability window opens and a
    break celebration broadcasts, naming every distinct contributor.

    Called from resolve_round's post-pass, AFTER the clash post-pass resolves
    this round's clashes (so the HOLD feed can see a LOCK-clash win that
    resolved this same round).

    When the bar reaches 0 a BOSS_BREAK dramatic surge also fires for every
    ACTIVE PC (#3445), once per boss per phase - the re-break loop does not
    repeat it.
    """
    round_number = encounter.round_number
    bosses = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
            tier=OpponentTier.BOSS,
            break_bar_threshold__gt=0,
            vulnerability_rounds_remaining=0,
        )
    )
    if not bosses:
        return

    for boss in bosses:
        _assess_boss_break_bar(encounter, boss, round_number, action_outcomes)


def _outcome_damaged_boss(outcome: ActionOutcome, boss_pk: int) -> bool:
    """Return True if the outcome's damage results include damage to the given boss."""
    return any(
        hasattr(r, "opponent_id") and r.opponent_id == boss_pk for r in outcome.damage_results
    )


def _assess_boss_break_bar(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
    action_outcomes: list[ActionOutcome],
) -> None:
    """Assess and apply one boss's break-bar depletion for this round (#2642)."""
    events, combo_bonus = _break_bar_events_this_round(
        encounter, boss, round_number, action_outcomes
    )
    if not events and combo_bonus <= 0:
        return

    raw_depletion = _persist_break_bar_events(boss, round_number, events) + combo_bonus
    if raw_depletion <= 0:
        return

    active_reinforcers = _active_reinforcer_count(boss, round_number)
    # Proportional gate — floor at 1 unit whenever depletion occurred; never a
    # hard block (#2642).
    bar_damage = max(raw_depletion // (1 + active_reinforcers), 1)

    boss.break_bar_current = max(0, boss.break_bar_current - bar_damage)
    broke_this_round = boss.break_bar_current == 0
    if broke_this_round:
        boss.vulnerability_rounds_remaining = boss.vulnerability_rounds
    boss.save(update_fields=["break_bar_current", "vulnerability_rounds_remaining"])
    if broke_this_round:
        _broadcast_break_celebration(encounter, boss)
        _record_story_break_recognition(encounter, boss, round_number)
        from world.combat.escalation import apply_boss_break_surge  # noqa: PLC0415

        apply_boss_break_surge(opponent=boss)


def _break_bar_events_this_round(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
    action_outcomes: list[ActionOutcome],
) -> tuple[list[tuple[str, int | None, int | None]], int]:
    """Gather this round's break-bar feed events for *boss*.

    Returns ``(events, combo_bonus)`` where each event is
    ``(kind, participant_id, effect_type_id)`` — one per qualifying feed,
    persisted 1:1 as a ``BreakBarContribution`` row by the caller. Combo's flat
    ``bonus_damage`` depletion is returned separately (additive, not part of
    the diversity-unit pool).
    """
    events: list[tuple[str, int | None, int | None]] = []
    combo_bonus = 0

    # Combo path: first landed combo this round (unchanged bonus_damage depletion,
    # plus its own COMBO diversity-unit contribution).
    for outcome in action_outcomes:
        if outcome.combo_used is not None and _outcome_damaged_boss(outcome, boss.pk):
            combo_bonus = outcome.combo_used.bonus_damage
            events.append(
                (BreakContributionKind.COMBO, outcome.participant_id, outcome.effect_type_id)
            )
            break

    # DAMAGE feed: every qualifying PC damage outcome this round.
    events.extend(
        (BreakContributionKind.DAMAGE, outcome.participant_id, outcome.effect_type_id)
        for outcome in action_outcomes
        if (
            outcome.entity_type == ENTITY_TYPE_PC
            and outcome.participant_id is not None
            and outcome.effect_type_id is not None
            and _outcome_damaged_boss(outcome, boss.pk)
        )
    )

    # HOLD feed: PC-side LOCK-clash win against this boss, resolved this round.
    events.extend(
        (BreakContributionKind.HOLD, participant_id, None)
        for participant_id in _pc_lock_hold_contributors(encounter, boss, round_number)
    )

    round_started_at = encounter.round_started_at

    # DEBUFF feed: new behavior-altering condition landed on the boss this round.
    events.extend(
        (BreakContributionKind.DEBUFF, participant_id, None)
        for participant_id in _boss_new_debuff_events(boss, encounter, round_started_at)
    )

    # SUPPRESSION feed: a reinforcing lieutenant became suppressed this round.
    events.extend(
        (BreakContributionKind.SUPPRESSION, participant_id, None)
        for _lieutenant, participant_id in _newly_suppressed_lieutenants(
            encounter, boss, round_number, round_started_at
        )
    )

    return events, combo_bonus


def _persist_break_bar_events(
    boss: CombatOpponent,
    round_number: int,
    events: list[tuple[str, int | None, int | None]],
) -> int:
    """Persist one ``BreakBarContribution`` row per event; return the diversity-unit total.

    1 unit per distinct (actor, kind) pair this round, doubled to
    ``BREAK_NOVELTY_MULTIPLIER`` for a (kind, effect_type) pair's first-ever
    appearance across the whole encounter (checked against rows persisted in
    prior rounds — never rows created within this same call).
    """
    existing_pairs = set(
        BreakBarContribution.objects.filter(opponent=boss).values_list("kind", "effect_type_id")
    )
    novel_pairs_seen: set[tuple[str, int | None]] = set()
    actor_kind_pairs: set[tuple[int | None, str]] = set()

    for kind, participant_id, effect_type_id in events:
        BreakBarContribution.objects.create(
            opponent=boss,
            participant_id=participant_id,
            round_number=round_number,
            kind=kind,
            effect_type_id=effect_type_id,
        )
        actor_kind_pairs.add((participant_id, kind))
        pair = (kind, effect_type_id)
        if pair not in existing_pairs:
            novel_pairs_seen.add(pair)

    base_units = len(actor_kind_pairs)
    bonus_units = len(novel_pairs_seen) * (BREAK_NOVELTY_MULTIPLIER - 1)
    return base_units + bonus_units


def _broadcast_break_celebration(encounter: CombatEncounter, boss: CombatOpponent) -> None:
    """Broadcast the break moment naming every distinct contributor this encounter (#2642).

    Mirrors ``render_combo_finisher_narration``'s contributor-naming style.
    ``broadcast_action_outcome`` reaches both channels, web and telnet (#4640).
    """
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        join_labels,
    )

    contributor_labels = _break_bar_contributor_labels(boss)
    if not contributor_labels:
        return

    names = join_labels(contributor_labels)
    narration = f"{boss.name}'s wall breaks — {names} broke through!"
    broadcast_action_outcome(encounter=encounter, narration=narration)


def _break_bar_contributor_labels(boss: CombatOpponent) -> list[str]:
    """Distinct PC labels credited on any ``BreakBarContribution`` row for *boss* this encounter."""
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    participant_ids = (
        BreakBarContribution.objects.filter(opponent=boss, participant__isnull=False)
        .values_list("participant_id", flat=True)
        .distinct()
    )
    participants = list(
        CombatParticipant.objects.filter(pk__in=participant_ids).select_related(
            "character_sheet__character"
        )
    )
    # Persona display name, not str(CombatParticipant) -> str(CharacterSheet)
    # ("Sheet for {key}") -- #4091 fix round 3.
    persona_names = persona_names_for_sheets(p.character_sheet_id for p in participants)
    return [
        persona_names.get(p.character_sheet_id, p.character_sheet.character.key)
        for p in participants
    ]
