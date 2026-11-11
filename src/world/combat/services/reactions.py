"""Reactions: the automatic dodge, what it costs, and the roll that gets harder (#4676, #5066).

A character dodges an NPC attack automatically when one of her capability sources matches
an application that dodges (``Application.dodges``, matched by
``source_matches_application`` in ``world.areas.positioning.traversal``), or a Phase Step
ward is on her. Each dodge is one use of that source (``movement_use``): with a technique it
is a cast of it, paid, rolled and powered as a cast, and the roll's strength is added to her
defense roll and sets how far she may land (the shared bands); with anything else it costs
physical fatigue and its value is the bonus. Each reaction she has already made this round
takes ``MovementConfig.reaction_difficulty_step`` off the roll. There is no cap.

Her plan (``CombatParticipant.dodge_enabled`` / ``dodge_landing`` / ``dodge_technique`` /
``dodge_into_soulfray``) says whether to dodge, where to land, which technique answers
(else her saved ``CharacterTechnique.default_dodge``, else her strongest source) and whether
to keep dodging when the cast would overspend into Soulfray. With no landing she dodges in
place. The Phase Step ward keeps its own payer rule (a ward someone else cast charges its
caster, #2208).
"""

from __future__ import annotations

from collections.abc import Iterator
import contextlib
import contextvars
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from world.areas.positioning.constants import ReactionReach
from world.areas.positioning.models import Position
from world.areas.positioning.services import (
    REACH_ORDER,
    force_move_to_position,
    position_of,
    reachable_landings,
)
from world.areas.positioning.traversal import MovementSource, matched_movement, reach_for_strength
from world.combat.constants import DEFENSE_REDUCED_THRESHOLD
from world.combat.models import MovementConfig
from world.combat.types import Steadier, SteadyResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatOpponentAction, CombatParticipant
    from world.combat.services.movement_use import MovementUse
    from world.conditions.models import Compulsion, ConditionInstance

#: True while an NPC attack is resolving through the automatic dodge, so the Phase
#: Step interceptor (``blink_dodge``) leaves the hit to the roll (#4676).
DODGE_ROLL_ACTIVE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "dodge_roll_active", default=False
)


#: What a use costs when it costs nothing (a non-technique use outside a fight).
FREE_USE = "free"


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
    """What lets her dodge: one of her sources matching a dodging application, or a ward.

    ``value`` is its standing strength (a technique's grant before any roll) and ``reach``
    how far that strength lands her; a technique dodge rolls its own strength each time.
    """

    reach: str
    value: int
    way: str = ""
    movement: MovementSource | None = None
    ward: ConditionInstance | None = None

    @property
    def technique_id(self) -> int | None:
        """The technique a dodge with this source casts, or None."""
        return self.movement.technique_id if self.movement is not None else None

    @property
    def name(self) -> str:
        """What the dodge plan calls this source."""
        if self.ward is not None:
            return self.ward.condition.name
        return self.movement.name if self.movement is not None else ""


@dataclass(frozen=True)
class Dodge:
    """A dodge she will make: its source, where she lands (None stays put), and once made,
    the use it was (its strength and what it cost)."""

    source: DodgeSource
    landing: Position | None
    use: MovementUse | None = None

    @property
    def strength(self) -> int:
        """What the dodge adds to her defense roll before the reaction penalty."""
        return self.use.strength if self.use is not None else self.source.value


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


def _preferred_technique_id(participant: CombatParticipant) -> int | None:
    """The technique her plan picks: this fight's choice, else her saved default."""
    if participant.dodge_technique_id is not None:
        return participant.dodge_technique_id
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    return (
        CharacterTechnique.objects.filter(
            character_id=participant.character_sheet_id, default_dodge=True
        )
        .values_list("technique_id", flat=True)
        .first()
    )


def dodge_sources(participant: CombatParticipant) -> list[DodgeSource]:
    """Every way she can dodge right now, the one her plan picks first, then strongest.

    One entry per source: a source matching several dodging applications keeps the first
    (the authored order). The Phase Step ward comes last.
    """
    sheet = participant.character_sheet
    seen: set[tuple[str, int, int]] = set()
    sources: list[DodgeSource] = []
    for ms in matched_movement(sheet.character):
        if not ms.application.dodges:
            continue
        key = (ms.source.source_type, ms.source.source_id, ms.source.capability_id)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            DodgeSource(
                reach=reach_for_strength(ms.standing_strength),
                value=ms.standing_strength,
                way=ms.way,
                movement=ms,
            )
        )
    preferred = _preferred_technique_id(participant)
    sources.sort(
        key=lambda s: (
            s.technique_id is None or s.technique_id != preferred,
            -s.value,
            -REACH_ORDER.get(s.reach, 0),
        )
    )
    ward = _phase_step_ward(sheet)
    if ward is not None:
        sources.append(DodgeSource(reach=ReactionReach.ANY_PLACE, value=0, ward=ward))
    return sources


def dodge_landing_options(participant: CombatParticipant) -> list[Position]:
    """Every place her dodges can land in this round at their standing strength (her plan's
    choices), her own place first."""
    sources = dodge_sources(participant)
    if not sources:
        return []
    current = position_of(participant.character_sheet.character)
    found: dict[int, Position] = {}
    for source in sources:
        for place in reachable_landings(current, source.reach, way=source.way):
            found.setdefault(place.pk, place)
    if current is None:
        return []
    others = sorted((p for pk, p in found.items() if pk != current.pk), key=lambda p: p.name)
    return [current, *others]


def _reachable_dodge_source(
    sources: list[DodgeSource], current: Position | None, landing: Position
) -> DodgeSource | None:
    """Find the first source that reaches the planned landing."""
    return next(
        (
            source
            for source in sources
            if landing in reachable_landings(current, source.reach, way=source.way)
        ),
        None,
    )


def choose_dodge(
    participant: CombatParticipant, *, covered_position: Position | None = None
) -> Dodge | None:
    """The dodge she means to make against this attack, or None (plain defense roll).

    A planned landing is used when some source reaches it at its standing strength;
    otherwise she dodges in place with her first source. Against a place-covering attack
    only a landing outside the covered place helps, so with no such landing she does not
    dodge. A technique dodge's own roll may still land her short (``make_dodge``).
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


def make_dodge(participant: CombatParticipant, dodge: Dodge) -> Dodge | None:
    """Make the dodge: pay for it and, for a technique, cast and roll it (#5066).

    None when it does not happen: a ward that cannot pay, or a technique cast stopped
    before it went off (her "dodge even into Soulfray" box unticked and the cast would
    overspend, or no check to roll); nothing is paid then. A technique dodge whose roll
    does not reach the planned landing dodges in place. An automatic dodge is never
    lethal for a player who is not connected (``movement_use``).
    """
    if dodge.source.ward is not None:
        from world.conditions.services import spend_condition_use  # noqa: PLC0415
        from world.magic.services.effect_handlers import _try_spend_reactive  # noqa: PLC0415

        if not _try_spend_reactive(dodge.source.ward):
            return None
        spend_condition_use(dodge.source.ward)
        return dodge
    from world.combat.services.movement_use import use_movement_source  # noqa: PLC0415

    character = participant.character_sheet.character
    movement = dodge.source.movement
    if movement is None:
        return None
    use = use_movement_source(
        character,
        movement,
        participant=participant,
        lethal=participant.encounter.is_lethal,
        confirm_soulfray_risk=participant.dodge_into_soulfray,
        chosen_by_player=False,
    )
    if not use.went_off:
        return None
    landing = dodge.landing
    if landing is not None:
        current = position_of(character)
        if landing not in reachable_landings(current, use.reach, way=dodge.source.way):
            landing = None
    return replace(dodge, landing=landing, use=use)


def dodge_label(dodge: Dodge) -> str:
    """The defense roll's "Dodge" line: what answered, what its roll gave, what it cost."""
    use = dodge.use
    if use is None or use.technique is None:
        return f"Dodge ({dodge.source.name})" if dodge.source.name else "Dodge"
    parts = [f"strength {use.strength}"]
    if use.roll is not None:
        parts.insert(0, f"roll {use.roll.success_level:+d}")
    parts.append(f"{use.anima_paid} anima")
    if use.soulfray_added:
        parts.append(f"Soulfray +{use.soulfray_added}")
    return f"Dodge ({dodge.source.name}: {', '.join(parts)})"


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


def movement_use_cost(character: ObjectDB, movement: MovementSource, *, in_fight: bool) -> str:  # noqa: OBJECTDB_PARAM - the caster's game object
    """What one use of ``movement`` costs now, e.g. "4 anima" or "1 fatigue" (#5066).

    A technique's own cast cost, priced as ``use_technique`` charges it (out of a fight her
    control often brings it to 0); anything else costs physical fatigue in a fight and
    nothing outside one. A dodge and a turn move with the same source cost the same.
    """
    if movement.technique_id is None:
        if not in_fight:
            return FREE_USE
        return f"{reaction_tuning().dodge_fatigue_cost} fatigue"
    from world.magic.models import Technique  # noqa: PLC0415
    from world.magic.services.techniques import preview_technique_anima_cost  # noqa: PLC0415

    technique = Technique.objects.get(pk=movement.technique_id)
    cost = preview_technique_anima_cost(character, technique)
    return f"{cost.effective_cost} anima"


def dodge_cost_line(participant: CombatParticipant, source: DodgeSource) -> str:
    """The bare cost of a dodge with this source, for the dodge plan."""
    if source.ward is not None:
        cost = f"{source.ward.condition.reactive_anima_cost} anima"
    elif source.movement is not None:
        cost = movement_use_cost(
            participant.character_sheet.character, source.movement, in_fight=True
        )
    else:
        cost = ""
    if source.technique_id is not None:
        return (
            f"Each dodge casts {source.name}: {cost} and a roll whose strength is the bonus. "
            "Each dodge after the first this round is harder."
        )
    return f"Each dodge costs {cost}. Each dodge after the first this round is harder."


def steady_capability_value(participant: CombatParticipant) -> int:
    """How far above its baseline she holds the steadying capability; 0 when she holds none.

    0 as well when staff have set no steadying capability, so nobody steadies.
    """
    from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

    config = MovementConfig.objects.cached_singleton()
    capability = config.steadying_capability if config is not None else None
    if capability is None:
        return 0
    above = get_effective_capability_value(participant.character_sheet, capability)
    return max(0, above - capability.innate_baseline)


def steadiers_for(participant: CombatParticipant) -> list[Steadier]:
    """The allies who could steady a compelled *participant* now, best first (#4802).

    An ally steadies when she is active in the same encounter, is not the steadied
    fighter, has the steady plan on, can act (``can_act``: a knocked-out ally stays ACTIVE
    but steadies nobody), carries no compulsion of her own, holds the steadying
    capability above its baseline, and has the anima to pay. Her bonus is that capability
    plus the steady bonus per point of her bond depth to the steadied fighter (0 with no
    qualifying bond), less her reaction penalty. The biggest bonus comes first; ties go to
    the lowest participant pk.
    """
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415
    from world.combat.escalation import qualifying_bond_depths  # noqa: PLC0415
    from world.combat.models import CombatParticipant as _Participant  # noqa: PLC0415
    from world.conditions.control_loss import active_compulsions_for  # noqa: PLC0415
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415
    from world.vitals.services import can_act  # noqa: PLC0415

    config = MovementConfig.objects.cached_singleton()
    if config is None or config.steadying_capability_id is None:
        return []
    allies = list(
        _Participant.objects.filter(
            encounter_id=participant.encounter_id,
            status=ParticipantStatus.ACTIVE,
            steady_enabled=True,
        )
        .exclude(pk=participant.pk)
        .select_related("character_sheet__character")
        .order_by("pk")
    )
    # The capability and can_act are per-character oracles with no batch form; the
    # compulsion rows are read once for every ally.
    allies = [ally for ally in allies if can_act(ally.character_sheet)]
    capability_by_pk = {ally.pk: steady_capability_value(ally) for ally in allies}
    compelled = active_compulsions_for(
        [ally.character_sheet.character for ally in allies if capability_by_pk[ally.pk] > 0]
    )
    allies = [
        ally
        for ally in allies
        if capability_by_pk[ally.pk] > 0 and ally.character_sheet.character.pk not in compelled
    ]
    if not allies:
        return []
    anima_by_character = dict(
        CharacterAnima.objects.filter(
            character_id__in=[ally.character_sheet_id for ally in allies]
        ).values_list("character_id", "current")
    )
    depth_by_sheet = qualifying_bond_depths(
        [ally.character_sheet for ally in allies],
        participant.character_sheet,
        participant.encounter,
    )
    steadiers = [
        Steadier(
            participant=ally,
            bonus=capability_by_pk[ally.pk]
            + config.steady_bonus_per_depth * depth_by_sheet.get(ally.character_sheet_id, 0)
            - reaction_penalty(ally),
        )
        for ally in allies
        if anima_by_character.get(ally.character_sheet_id, 0) >= config.steady_anima_cost
    ]
    steadiers.sort(key=lambda found: (-found.bonus, found.participant.pk))
    return steadiers


def try_steady(
    participant: CombatParticipant,
    compulsion: Compulsion,
    difficulty: int,
) -> SteadyResult | None:
    """An ally's steadying: a second resist roll for a compelled *participant* (#4802).

    Called by compulsion resolution when the first resist roll lets the compulsion act.
    The best steadier pays the steady anima cost, spends a reaction, and the steadied
    fighter rolls the compulsion's check again with her bonus. None when nobody steadies.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415

    steadiers = steadiers_for(participant)
    if not steadiers:
        return None
    best = steadiers[0]
    config = MovementConfig.objects.cached_singleton()
    cost = config.steady_anima_cost if config is not None else 0
    paid = 0
    if cost:
        steadier = best.participant.character_sheet.character
        before = _anima_held(steadier)
        deduct_anima(steadier, cost, lethal=False)
        paid = before - _anima_held(steadier)
    record_reaction(best.participant)
    result = perform_check_with_modifiers(
        participant.character_sheet.character,
        compulsion.check_type,
        target_difficulty=difficulty,
        extra_modifiers=best.bonus,
    )
    return SteadyResult(
        steadier=best.participant, check_result=result, bonus=best.bonus, anima_paid=paid
    )


def _anima_held(character: ObjectDB) -> int:  # noqa: OBJECTDB_PARAM
    """The anima *character*'s pool holds now, glut included, read from the table."""
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415

    row = (
        CharacterAnima.objects.filter(character_id=character.pk)
        .values_list("current", "glut")
        .first()
    )
    return sum(row) if row is not None else 0
