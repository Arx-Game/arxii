"""Spectacle: earned displays shake enemy witnesses' morale (#4147).

Pure arithmetic plus ``apply_spectacle``. Never broadcasts: the caller delivers
``SpectacleResult.lines`` on its own channel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import (
    CombatAllegiance,
    OpponentStatus,
    SpectacleKind,
    SpectacleReaction,
)
from world.combat.models import SpectacleConfig, SpectacleReactionLine, SpectacleRecord
from world.combat.morale import (
    OpponentMoraleState,
    apply_morale_damage,
    morale_state_for,
    tier_has_morale,
)
from world.combat.types import SpectacleResult, SpectacleShift
from world.gm.prompt_services import scene_gm_accounts
from world.magic.audere import audere_check_level_bonus
from world.progression.services.skill_development import get_character_path_level
from world.scenes.services import active_persona_for_sheet

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter, CombatOpponent
    from world.magic.models.techniques import Technique


def raw_hit(*, config: SpectacleConfig, kind: str, success_level: int) -> int:
    """Base hit for a display kind, plus its per-success-level term where it has one."""
    base = {
        SpectacleKind.AUDERE_ENTRY: config.audere_entry_hit,
        SpectacleKind.ULTIMATE: config.ultimate_hit,
        SpectacleKind.CROSSING: config.crossing_hit,
        SpectacleKind.CRITICAL_TECHNIQUE: config.critical_technique_hit,
        SpectacleKind.DEVASTATING_ACTION: config.devastating_action_hit,
    }[kind]
    per_level = {
        SpectacleKind.ULTIMATE: config.ultimate_hit_per_success_level,
        SpectacleKind.CRITICAL_TECHNIQUE: config.critical_technique_hit_per_success_level,
    }.get(kind, 0)
    return base + per_level * max(success_level, 0)


def spectacle_hit(  # noqa: PLR0913 - the brief fixes this keyword-only signature
    *,
    config: SpectacleConfig,
    kind: str,
    success_level: int,
    caster_level: int,
    opponent_level: int,
    has_morale: bool,
) -> int:
    """Morale removed from one witness (spec B0, steps 1-6)."""
    raw = raw_hit(config=config, kind=kind, success_level=success_level)
    steps = int((caster_level - opponent_level) / max(config.levels_per_step, 1))
    factor = max(config.minimum_percent, 100 + config.percent_per_step * steps)
    hit = raw * factor // 100
    if not has_morale:
        hit = max(1, hit * config.mindless_percent // 100)
    return hit


def classify_cast(
    *,
    technique: Technique,
    runtime_intensity: int,
    success_level: int,
    config: SpectacleConfig,
) -> str | None:
    """The display kind a technique cast earns, or None when it earns none."""
    if technique.is_ultimate:
        return SpectacleKind.ULTIMATE
    if (
        runtime_intensity >= config.critical_technique_min_intensity
        and success_level >= config.critical_technique_min_success_level
    ):
        return SpectacleKind.CRITICAL_TECHNIQUE
    return None


def is_devastating(
    *,
    damage_by_opponent: dict[int, int],
    health_before: dict[int, int],
    config: SpectacleConfig,
) -> bool:
    """Whether one action removed enough of the enemy side's current health."""
    total = sum(health_before.values())
    if total <= 0:
        return False
    dealt = sum(
        min(damage, health_before[opp_id])
        for opp_id, damage in damage_by_opponent.items()
        if opp_id in health_before
    )
    return dealt * 100 >= total * config.devastating_action_force_percent


def _already_shaken_ids(
    caster_sheet: CharacterSheet,
    kind: str,
    technique: Technique | None,
    opponent_ids: list[int],
) -> set[int]:
    records = SpectacleRecord.objects.filter(caster=caster_sheet, opponent_id__in=opponent_ids)
    if technique is not None:
        records = records.filter(technique=technique)
    else:
        records = records.filter(kind=kind, technique__isnull=True)
    return set(records.values_list("opponent_id", flat=True))


def _hearten_allies(
    encounter: CombatEncounter, config: SpectacleConfig, kind: str, success_level: int
) -> tuple[int, ...]:
    gain = raw_hit(config=config, kind=kind, success_level=success_level)
    gain = gain * config.ally_gain_percent // 100
    healed: list[int] = []
    allies = encounter.opponents.filter(
        status=OpponentStatus.ACTIVE, allegiance=CombatAllegiance.ALLY
    )
    for ally in allies:
        ally.morale = min(ally.max_morale, ally.morale + gain)
        ally.save(update_fields=["morale"])
        healed.append(ally.pk)
    return tuple(healed)


def _group_name(opponent: CombatOpponent) -> str:
    template = opponent.creature_template
    return template.name if template is not None else opponent.name


def _group_names(opponents: list[CombatOpponent]) -> str:
    names = list(dict.fromkeys(_group_name(opponent) for opponent in opponents))
    return " and ".join(names)


def _shaken_opponents(
    witnesses: list[CombatOpponent], shifts: list[SpectacleShift]
) -> list[CombatOpponent]:
    ids = {shift.opponent_id for shift in shifts}
    return [w for w in witnesses if w.pk in ids]


def _credit_line(  # noqa: PLR0913 - private helper, one arg per line input
    caster_sheet: CharacterSheet,
    display_name: str,
    witnesses: list[CombatOpponent],
    shifts: list[SpectacleShift],
    heartened: tuple[int, ...],
    allies: list[CombatOpponent],
) -> str:
    persona = active_persona_for_sheet(caster_sheet).name
    names = _group_names(_shaken_opponents(witnesses, shifts))
    broke = any(s.after == OpponentMoraleState.BREAK for s in shifts)
    faltered = any(
        s.after == OpponentMoraleState.FALTER and s.before == OpponentMoraleState.STEADY
        for s in shifts
    )
    if broke:
        line = f"The {names} break before {persona}'s {display_name}."
    elif faltered:
        line = f"The {names} falter before {persona}'s {display_name}."
    else:
        line = f"The {names} are shaken by {persona}'s {display_name}."
    if heartened:
        ally_names = _group_names([a for a in allies if a.pk in heartened])
        line += f" The {ally_names} take heart."
    return line


def _flavour_line(  # noqa: PLR0913 - private helper, one arg per line input
    encounter: CombatEncounter,
    caster_sheet: CharacterSheet,
    display_name: str,
    kind: str,
    witnesses: list[CombatOpponent],
    shifts: list[SpectacleShift],
) -> str:
    if scene_gm_accounts(encounter.scene):
        return ""
    if any(s.after == OpponentMoraleState.BREAK for s in shifts):
        reaction = SpectacleReaction.BROKEN
    elif any(s.after != s.before for s in shifts):
        reaction = SpectacleReaction.FALTERING
    else:
        reaction = SpectacleReaction.SHAKEN
    shaken = _shaken_opponents(witnesses, shifts)
    template_id = shaken[0].creature_template_id if shaken else None
    best: tuple[tuple[bool, bool], str] | None = None
    for row in SpectacleReactionLine.objects.filter(reaction=reaction):
        if row.creature_template_id is not None and row.creature_template_id != template_id:
            continue
        if row.kind and row.kind != kind:
            continue
        rank = (row.creature_template_id is not None, bool(row.kind))
        if best is None or rank > best[0]:
            best = (rank, row.text)
    if best is None:
        return ""
    return (
        best[1]
        .replace("<actor>", active_persona_for_sheet(caster_sheet).name)
        .replace("<group>", _group_names(shaken))
        .replace("<display>", display_name)
    )


def apply_spectacle(  # noqa: PLR0913 - keyword-only public contract
    *,
    encounter: CombatEncounter,
    caster_sheet: CharacterSheet,
    kind: str,
    display_name: str,
    success_level: int = 0,
    technique: Technique | None = None,
    witnesses: list[CombatOpponent] | None = None,
) -> SpectacleResult:
    """Shake each witness once per caster and move; hearten allies; build the lines (#4147).

    Never broadcasts: the caller delivers ``result.lines`` on its own channel.
    """
    config = SpectacleConfig.load()
    caster_level = get_character_path_level(caster_sheet.character) + audere_check_level_bonus(
        caster_sheet.character
    )
    if witnesses is None:
        witnesses = list(
            encounter.opponents.filter(
                status=OpponentStatus.ACTIVE, allegiance=CombatAllegiance.ENEMY
            )
        )
    witnesses = [w for w in witnesses if w.status == OpponentStatus.ACTIVE]
    already = _already_shaken_ids(caster_sheet, kind, technique, [w.pk for w in witnesses])
    shifts: list[SpectacleShift] = []
    for opponent in witnesses:
        if opponent.pk in already:
            continue
        before = morale_state_for(opponent)
        hit = spectacle_hit(
            config=config,
            kind=kind,
            success_level=success_level,
            caster_level=caster_level,
            opponent_level=opponent.level,
            has_morale=tier_has_morale(opponent),
        )
        apply_morale_damage(opponent, hit)
        SpectacleRecord.objects.create(
            encounter=encounter,
            opponent=opponent,
            caster=caster_sheet,
            kind=kind,
            technique=technique,
        )
        shifts.append(SpectacleShift(opponent.pk, before.value, morale_state_for(opponent).value))
    if not shifts:
        return SpectacleResult()
    heartened = _hearten_allies(encounter, config, kind, success_level)
    allies = list(encounter.opponents.filter(pk__in=heartened))
    return SpectacleResult(
        credit_line=_credit_line(caster_sheet, display_name, witnesses, shifts, heartened, allies),
        flavour_line=_flavour_line(encounter, caster_sheet, display_name, kind, witnesses, shifts),
        shifts=tuple(shifts),
        heartened_ids=heartened,
    )


def encounter_for_character(character: ObjectDB) -> CombatEncounter | None:  # noqa: OBJECTDB_PARAM - callers hold the puppeted body
    """The encounter a character is fighting in, via its COMBAT engagement (#4147)."""
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    engagement = CharacterEngagement.objects.filter(
        character_id=character.pk, engagement_type=EngagementType.COMBAT
    ).first()
    if engagement is None:
        return None
    source = engagement.source
    return source if isinstance(source, CombatEncounter) else None


def deliver_spectacle(encounter: CombatEncounter, result: SpectacleResult) -> None:
    """Post a spectacle's lines to the encounter room, web and telnet."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    for line in result.lines:
        broadcast_action_outcome(encounter=encounter, narration=line, deliver_telnet=True)
