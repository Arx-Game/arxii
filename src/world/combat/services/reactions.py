"""Reactions: the automatic dodge, what it costs, and the roll that gets harder (#4676).

A character dodges an NPC attack automatically when a capability she holds above its
innate baseline has a ``reaction_reach``, or a Phase Step ward is on her. The dodge is
her defense roll with that capability's value as a bonus; it costs anima, or fatigue
for a physical capability, and each reaction she has already made this round takes
``MovementConfig.reaction_difficulty_step`` off the roll. There is no cap. Her plan
(``CombatParticipant.dodge_enabled`` / ``dodge_landing``) says whether to dodge and
where to land; with no landing she dodges in place.

Movement reads capabilities only (#4651 decision 2): the source of a capability
never matters here. The Phase Step ward keeps its own payer rule (a ward someone
else cast charges its caster, #2208).
"""

from __future__ import annotations

from collections.abc import Iterator
import contextlib
import contextvars
from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.areas.positioning.constants import PositionKind, ReactionCostKind, ReactionReach
from world.areas.positioning.models import Position
from world.areas.positioning.services import (
    adjacent_open_positions,
    force_move_to_position,
    position_of,
)
from world.combat.constants import DEFENSE_REDUCED_THRESHOLD, ActionCategory
from world.combat.models import MovementConfig

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatOpponentAction, CombatParticipant
    from world.conditions.models import CapabilityType, ConditionInstance

#: True while an NPC attack is resolving through the automatic dodge, so the Phase
#: Step interceptor (``blink_dodge``) leaves the hit to the roll (#4676).
DODGE_ROLL_ACTIVE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "dodge_roll_active", default=False
)

#: Where a dodge may land, for each reach. ADJACENT and AIRBORNE add the places
#: next door; AIRBORNE also the air above her place; ANY_PLACE the whole room.
_REACH_ORDER = {
    ReactionReach.IN_PLACE: 1,
    ReactionReach.ADJACENT: 2,
    ReactionReach.AIRBORNE: 3,
    ReactionReach.ANY_PLACE: 4,
}


@dataclass(frozen=True)
class ReactionTuning:
    """The reaction tuning values, from the MovementConfig row or the field defaults."""

    dodge_anima_cost: int
    dodge_fatigue_cost: int
    reaction_difficulty_step: int
    wound_cap_shrink_per_round: int
    reactive_save_max_cut: int


@dataclass(frozen=True)
class DodgeSource:
    """What lets her dodge: a capability with a reach, or a Phase Step ward."""

    reach: str
    cost_kind: str
    value: int
    capability: CapabilityType | None = None
    ward: ConditionInstance | None = None


@dataclass(frozen=True)
class Dodge:
    """A dodge she will make: its source and where she lands (None stays put)."""

    source: DodgeSource
    landing: Position | None


@contextlib.contextmanager
def dodge_roll_active() -> Iterator[None]:
    """Mark the enclosed damage as already answered by the dodge roll."""
    token = DODGE_ROLL_ACTIVE.set(True)
    try:
        yield
    finally:
        DODGE_ROLL_ACTIVE.reset(token)


def reaction_tuning() -> ReactionTuning:
    """The authored tuning, or each field's default when no MovementConfig row exists."""
    row = MovementConfig.objects.cached_singleton()
    if row is None:
        row = MovementConfig()  # unsaved: carries every field's default
    return ReactionTuning(
        dodge_anima_cost=row.dodge_anima_cost,
        dodge_fatigue_cost=row.dodge_fatigue_cost,
        reaction_difficulty_step=row.reaction_difficulty_step,
        wound_cap_shrink_per_round=row.wound_cap_shrink_per_round,
        reactive_save_max_cut=row.reactive_save_max_cut,
    )


def reaction_penalty(participant: CombatParticipant) -> int:
    """The roll penalty for her next reaction: one step per reaction made this round."""
    return reaction_tuning().reaction_difficulty_step * participant.reactions_used


def record_reaction(participant: CombatParticipant) -> None:
    """Count one more reaction this round (dodge, guard or catch)."""
    participant.reactions_used += 1
    participant.save(update_fields=["reactions_used"])


def _phase_step_ward(sheet: CharacterSheet) -> ConditionInstance | None:
    """Her oldest active Phase Step ward, designated by its handler path, not its name."""
    from flows.consts import FlowActionChoices  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.services.effect_handlers import BLINK_DODGE_HANDLER_PATH  # noqa: PLC0415

    return (
        ConditionInstance.objects.filter(
            target=sheet.character,
            condition__reactive_triggers__flow_definition__steps__action=(
                FlowActionChoices.CALL_SERVICE_FUNCTION
            ),
            condition__reactive_triggers__flow_definition__steps__variable_name=(
                BLINK_DODGE_HANDLER_PATH
            ),
            resolved_at__isnull=True,
        )
        .order_by("pk")
        .first()
    )


def dodge_sources(participant: CombatParticipant) -> list[DodgeSource]:
    """Every way she can dodge right now, strongest first."""
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

    sheet = participant.character_sheet
    sources: list[DodgeSource] = []
    dodging = [
        capability
        for capability in CapabilityType.objects.cached_all()
        if capability.reaction_reach != ReactionReach.NONE
    ]
    for capability in dodging:
        above = get_effective_capability_value(sheet, capability) - capability.innate_baseline
        if above > 0:
            sources.append(
                DodgeSource(
                    reach=capability.reaction_reach,
                    cost_kind=capability.reaction_cost_kind,
                    value=above,
                    capability=capability,
                )
            )
    ward = _phase_step_ward(sheet)
    if ward is not None:
        sources.append(
            DodgeSource(
                reach=ReactionReach.ANY_PLACE, cost_kind=ReactionCostKind.ANIMA, value=0, ward=ward
            )
        )
    sources.sort(key=lambda s: (s.value, _REACH_ORDER.get(s.reach, 0)), reverse=True)
    return sources


def reachable_landings(current: Position | None, reach: str) -> list[Position]:
    """The places a dodge with this reach may land in, her own place first."""
    if current is None or reach == ReactionReach.NONE:
        return []
    if reach == ReactionReach.IN_PLACE:
        return [current]
    if reach == ReactionReach.ANY_PLACE:
        others = Position.objects.filter(room_id=current.room_id).exclude(pk=current.pk)
        return [current, *sorted(others, key=lambda p: p.name)]
    neighbours = []
    for edge in adjacent_open_positions(current):
        other = edge.position_b if edge.position_a_id == current.pk else edge.position_a
        neighbours.append(other)
    if reach == ReactionReach.AIRBORNE:
        above = Position.objects.filter(
            room_id=current.room_id, kind=PositionKind.AERIAL, elevation_anchor=current
        ).first()
        if above is not None and not current.is_roofed:
            neighbours.append(above)
    unique = {p.pk: p for p in neighbours if p.pk != current.pk}
    return [current, *sorted(unique.values(), key=lambda p: p.name)]


def dodge_landing_options(participant: CombatParticipant) -> list[Position]:
    """Every place her strongest-reaching dodge can land in this round (her plan's choices)."""
    sources = dodge_sources(participant)
    if not sources:
        return []
    current = position_of(participant.character_sheet.character)
    widest = max(sources, key=lambda s: _REACH_ORDER.get(s.reach, 0))
    return reachable_landings(current, widest.reach)


def _reachable_dodge_source(
    sources: list[DodgeSource], current: Position | None, landing: Position
) -> DodgeSource | None:
    """Find the first source that reaches the planned landing."""
    return next(
        (source for source in sources if landing in reachable_landings(current, source.reach)), None
    )


def choose_dodge(
    participant: CombatParticipant, *, covered_position: Position | None = None
) -> Dodge | None:
    """The dodge she makes against this attack, or None (plain defense roll).

    A planned landing is used when some source reaches it; otherwise she dodges in
    place with her strongest source. Against a place-covering attack only a landing
    outside the covered place helps, so with no such landing she does not dodge.
    """
    if not participant.dodge_enabled:
        return None
    sources = dodge_sources(participant)
    if not sources:
        return None
    current = position_of(participant.character_sheet.character)
    landing = participant.dodge_landing
    if landing is not None and current is not None and landing.room_id != current.room_id:
        landing = None
    if landing is not None:
        source = _reachable_dodge_source(sources, current, landing)
        if source is not None:
            if covered_position is not None and landing.pk == covered_position.pk:
                return None
            return Dodge(source=source, landing=landing if landing != current else None)
    if covered_position is not None:
        return None
    return Dodge(source=sources[0], landing=None)


def pay_for_dodge(participant: CombatParticipant, dodge: Dodge) -> bool:
    """Charge the dodge's cost; False when she cannot pay (then she does not dodge)."""
    if dodge.source.ward is not None:
        from world.conditions.services import spend_condition_use  # noqa: PLC0415
        from world.magic.services.effect_handlers import _try_spend_reactive  # noqa: PLC0415

        if not _try_spend_reactive(dodge.source.ward):
            return False
        spend_condition_use(dodge.source.ward)
        return True
    tuning = reaction_tuning()
    sheet = participant.character_sheet
    if dodge.source.cost_kind == ReactionCostKind.FATIGUE:
        from world.fatigue.constants import EffortLevel  # noqa: PLC0415
        from world.fatigue.services import apply_fatigue  # noqa: PLC0415

        apply_fatigue(sheet, ActionCategory.PHYSICAL, tuning.dodge_fatigue_cost, EffortLevel.LOW)
        return True
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415

    anima = CharacterAnima.objects.filter(character_id=sheet.pk).first()
    if anima is None or anima.current < tuning.dodge_anima_cost:
        return False
    deduct_anima(sheet.character, tuning.dodge_anima_cost, lethal=False)
    return True


def land_dodge(participant: CombatParticipant, dodge: Dodge, success_level: int) -> bool:
    """Move her to her landing when the roll at least partly succeeded; True if she moved."""
    if dodge.landing is None or success_level < DEFENSE_REDUCED_THRESHOLD:
        return False
    force_move_to_position(participant.character_sheet.character, dodge.landing)
    return True


def covered_place(
    opponent_action: CombatOpponentAction, participant: CombatParticipant
) -> Position | None:
    """The place a place-covering attack lands on, or None for any other attack.

    A matured wind-up carries the place it was telegraphed on; a covering attack with
    no wind-up covers its target's place as it resolves.
    """
    if not opponent_action.threat_entry.covers_place:
        return None
    if opponent_action.covered_position_id is not None:
        return opponent_action.covered_position
    return position_of(participant.character_sheet.character)


def dodge_cost_line(source: DodgeSource) -> str:
    """The bare cost of a dodge with this source, for the dodge plan."""
    tuning = reaction_tuning()
    if source.ward is not None:
        cost = f"{source.ward.condition.reactive_anima_cost} anima"
    elif source.cost_kind == ReactionCostKind.FATIGUE:
        cost = f"{tuning.dodge_fatigue_cost} fatigue"
    else:
        cost = f"{tuning.dodge_anima_cost} anima"
    return f"Each dodge costs {cost}. Each dodge after the first this round is harder."
