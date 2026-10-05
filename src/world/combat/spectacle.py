"""Spectacle: earned displays shake enemy witnesses' morale (#4147).

Pure arithmetic plus ``apply_spectacle``, which never broadcasts. ``deliver_spectacle``
posts ``SpectacleResult.lines`` on ``transaction.on_commit(robust=True)``, so every
spectacle line posts after commit.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import (
    CombatAllegiance,
    OpponentStatus,
    SpectacleKind,
    SpectacleReaction,
)
from world.combat.models import (
    OpponentTierTemplate,
    SpectacleConfig,
    SpectacleReactionLine,
    SpectacleRecord,
)
from world.combat.morale import (
    OpponentMoraleState,
    apply_morale_damage,
    morale_state_for,
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
    allies: list[CombatOpponent], config: SpectacleConfig, kind: str, success_level: int
) -> list[CombatOpponent]:
    """Raise each active ally's morale; return only the allies whose morale rose."""
    gain = raw_hit(config=config, kind=kind, success_level=success_level)
    gain = gain * config.ally_gain_percent // 100
    if gain <= 0:
        return []
    heartened: list[CombatOpponent] = []
    for ally in allies:
        if ally.morale >= ally.max_morale:
            continue
        ally.morale = min(ally.max_morale, ally.morale + gain)
        ally.save(update_fields=["morale"])
        heartened.append(ally)
    return heartened


def _group_name(opponent: CombatOpponent) -> str:
    template = opponent.creature_template
    return template.name if template is not None else opponent.name


def _group_names(opponents: list[CombatOpponent]) -> str:
    names = list(dict.fromkeys(_group_name(opponent) for opponent in opponents))
    return " and ".join(names)


def _group_sizes(opponents: list[CombatOpponent]) -> Counter[str]:
    """Active members per group name, so a verb agrees with the group, not the sentence."""
    return Counter(_group_name(opponent) for opponent in opponents)


def _sentence(
    opponents: list[CombatOpponent],
    verbs: tuple[str, str],
    sizes: Counter[str],
    tail: str = "",
) -> str:
    """One sentence naming ``opponents``' groups; singular only for a lone active member."""
    names = dict.fromkeys(_group_name(opponent) for opponent in opponents)
    plural, singular = verbs
    verb = singular if sum(sizes[name] for name in names) == 1 else plural
    return f"The {' and '.join(names)} {verb}{tail}."


_BREAK = ("break", "breaks")
_FALTER = ("falter", "falters")
_HOLD = ("hold", "holds")
_SHAKEN = ("are shaken", "is shaken")
_HEARTEN = ("take heart", "takes heart")


def _by_outcome(
    witnesses: list[CombatOpponent], shifts: list[SpectacleShift]
) -> tuple[list[CombatOpponent], list[CombatOpponent], list[CombatOpponent]]:
    """Split the shaken witnesses into those that broke, faltered, and held (state unchanged)."""
    by_id = {w.pk: w for w in witnesses}
    broke: list[CombatOpponent] = []
    faltered: list[CombatOpponent] = []
    held: list[CombatOpponent] = []
    for shift in shifts:
        opponent = by_id[shift.opponent_id]
        if shift.after == shift.before:
            held.append(opponent)
        elif shift.after == OpponentMoraleState.BREAK:
            broke.append(opponent)
        else:
            faltered.append(opponent)
    return broke, faltered, held


def _credit_line(
    persona: str,
    display_name: str,
    outcome: tuple[list[CombatOpponent], list[CombatOpponent], list[CombatOpponent]],
    heartened: list[CombatOpponent],
    sizes: Counter[str],
) -> str:
    """One sentence per resulting state, so no witness is credited a state it never reached.

    The first sentence names the caster and the display. When some group changed state, a
    steady group that held is named as holding; a group already faltering that stays so gets
    no clause (its chip already says it). With no change at all, every witness is "shaken by"
    the display (#4147 demo Screens 1-2).
    """
    broke, faltered, held = outcome
    credit = f" before {persona}'s {display_name}"
    sentences: list[str] = []
    if broke:
        sentences.append(_sentence(broke, _BREAK, sizes, credit))
        credit = ""
    if faltered:
        sentences.append(_sentence(faltered, _FALTER, sizes, credit))
        credit = ""
    if not sentences:
        sentences.append(_sentence(held, _SHAKEN, sizes, f" by {persona}'s {display_name}"))
    else:
        steady = [o for o in held if morale_state_for(o) == OpponentMoraleState.STEADY]
        if steady:
            sentences.append(_sentence(steady, _HOLD, sizes))
    if heartened:
        sentences.append(_sentence(heartened, _HEARTEN, sizes))
    return " ".join(sentences)


def _flavour_line(  # noqa: PLR0913 - private helper, one arg per line input
    lines: list[SpectacleReactionLine],
    reaction: str,
    kind: str,
    group: list[CombatOpponent],
    persona: str,
    display_name: str,
) -> str:
    """The most specific authored line for a reaction: creature beats kind beats generic."""
    template_id = group[0].creature_template_id
    best: tuple[tuple[bool, bool], str] | None = None
    for row in lines:
        if row.reaction != reaction:
            continue
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
        .replace("<actor>", persona)
        .replace("<group>", _group_names(group))
        .replace("<display>", display_name)
    )


def _enemy_reaction(
    outcome: tuple[list[CombatOpponent], list[CombatOpponent], list[CombatOpponent]],
) -> tuple[str, list[CombatOpponent]]:
    """The strongest reaction among the witnesses, and the witnesses who showed it."""
    broke, faltered, held = outcome
    if broke:
        return SpectacleReaction.BROKEN, broke
    if faltered:
        return SpectacleReaction.FALTERING, faltered
    return SpectacleReaction.SHAKEN, held


def _tier_morale_map() -> dict[str, bool]:
    """``{tier: has_morale}`` in one query; a tier with no template keeps its morale."""
    return dict(OpponentTierTemplate.objects.values_list("tier", "has_morale"))


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
    has_morale = _tier_morale_map()
    shifts: list[SpectacleShift] = []
    records: list[SpectacleRecord] = []
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
            has_morale=has_morale.get(opponent.tier, True),
        )
        apply_morale_damage(opponent, hit)
        records.append(
            SpectacleRecord(
                opponent=opponent,
                caster=caster_sheet,
                kind=kind,
                technique=technique,
            )
        )
        shifts.append(SpectacleShift(opponent.pk, before.value, morale_state_for(opponent).value))
    if not shifts:
        return SpectacleResult()
    SpectacleRecord.objects.bulk_create(records)
    allies = list(
        encounter.opponents.filter(status=OpponentStatus.ACTIVE, allegiance=CombatAllegiance.ALLY)
    )
    heartened = _hearten_allies(allies, config, kind, success_level)
    persona = active_persona_for_sheet(caster_sheet).name
    outcome = _by_outcome(witnesses, shifts)
    flavour = heartened_line = ""
    if not scene_gm_accounts(encounter.scene):
        lines = list(SpectacleReactionLine.objects.all())
        reaction, group = _enemy_reaction(outcome)
        flavour = _flavour_line(lines, reaction, kind, group, persona, display_name)
        if heartened:
            heartened_line = _flavour_line(
                lines, SpectacleReaction.HEARTENED, kind, heartened, persona, display_name
            )
    return SpectacleResult(
        credit_line=_credit_line(
            persona, display_name, outcome, heartened, _group_sizes(witnesses + allies)
        ),
        flavour_line=flavour,
        heartened_line=heartened_line,
        shifts=tuple(shifts),
        heartened_ids=tuple(ally.pk for ally in heartened),
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
    """Post a spectacle's lines to the encounter room, web and telnet, once committed.

    The post waits for the surrounding transaction: the client refetches the encounter on
    the payload and would read pre-commit morale, and a rolled-back round must not have
    announced a shift that never happened.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    def _post() -> None:
        for line in result.lines:
            broadcast_action_outcome(encounter=encounter, narration=line, deliver_telnet=True)

    transaction.on_commit(_post, robust=True)
