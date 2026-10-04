"""The standoff verbs: read, press, name terms, fight and share a spark.

Every verb is one transaction that locks the encounter row, then the group row, and
re-reads state before it rolls anything: a verb dispatched after the standoff ended
(fight begun, group settled) is refused with no roll. Lock order is always encounter then
group, matching ``end_standoff_into_fight``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
import random
from typing import TYPE_CHECKING

from django.db import transaction

from world.checks.services import (
    collect_check_modifiers,
    compute_resist_increment,
    level_opposition,
    perform_check,
)
from world.checks.social_target import DriveHit, SocialDifficulty, social_target_difficulty
from world.checks.theater import check_outcome_faces, maybe_emit_resolution_theater
from world.combat.constants import (
    DEMORALIZE_MORALE_PER_LEVEL,
    MINDLESS_MORALE_RESISTANCE,
    CauseKind,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.morale import (
    OpponentMoraleState,
    apply_morale_damage,
    morale_state_for,
    tier_has_morale,
)
from world.conditions.services import apply_condition
from world.fatigue.constants import EffortLevel
from world.mechanics.models import Application
from world.standoffs.constants import (
    FIGHT_BEGINS_MESSAGE,
    SUCCESS_LEVEL_WORDS,
    RevealKind,
    StandoffGroupState,
    TermsEffect,
)
from world.standoffs.models import (
    CreatureDrive,
    RegardRule,
    StandoffApproach,
    StandoffConfig,
    StandoffGroup,
    StandoffReveal,
    StandoffSparkShare,
    StandoffTerms,
)
from world.standoffs.services.force import evaluate_causes
from world.standoffs.services.regard import (
    MatchedRegard,
    band_shift_from,
    drive_strength_from,
    regard_matches,
)
from world.standoffs.services.routing import complete_standoff
from world.standoffs.services.state import (
    active_members,
    end_standoff_into_fight,
    flush_cache_on_error,
    is_in_standoff,
    settle_empty_groups,
)
from world.standoffs.types import StandoffActionResult

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant

BOTCH_LEVEL = -2
CRITICAL_LEVEL = 2
_MSG_OVER = "The standoff is over."
_MSG_SETTLED = "That group is no longer in the standoff."
_MSG_EMPTY = "There is nobody left in that group."
_MSG_UNCONFIGURED = "You can't do that right now."


def _lock(
    encounter: CombatEncounter, group: StandoffGroup | None
) -> tuple[CombatEncounter, StandoffGroup | None]:
    """Lock the encounter row, then the group row, and re-read both.

    ``select_for_update().get(pk=...)`` takes the row lock; the identity map hands back the
    resident instance, which is why the ``refresh_from_db`` follows: it makes that instance
    show what the database holds now that the lock is ours.
    """
    from world.combat.models import CombatEncounter  # noqa: PLC0415

    locked_encounter = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    locked_encounter.refresh_from_db()
    if group is None:
        return locked_encounter, None
    locked_group = StandoffGroup.objects.select_for_update().get(pk=group.pk)
    locked_group.refresh_from_db()
    return locked_encounter, locked_group


def _refusal(encounter: CombatEncounter, group: StandoffGroup | None) -> str | None:
    if not is_in_standoff(encounter):
        return _MSG_OVER
    if group is not None and group.state != StandoffGroupState.OPEN:
        return _MSG_SETTLED
    return None


def _word(tier: int) -> str:
    """The plain outcome word for a check tier ("Success", "Critical failure"...)."""
    return SUCCESS_LEVEL_WORDS[max(-2, min(2, tier))]


def _refuse(message: str) -> StandoffActionResult:
    return StandoffActionResult(success=False, message=message)


def _roll_inputs(
    members: list[CombatOpponent],
) -> tuple[CombatOpponent, int]:
    return members[0], max(member.level for member in members)


def _revealed_set(group: StandoffGroup) -> set[tuple[str, int | None, int | None]]:
    return set(group.reveals.values_list("kind", "drive_id", "regard_rule_id"))


def hidden_things(
    group: StandoffGroup,
    participants: list[CombatParticipant],
    *,
    revealed: set[tuple[str, int | None, int | None]] | None = None,
    known_matches: dict[int, list[MatchedRegard]] | None = None,
) -> list[tuple[str, CreatureDrive | None, RegardRule | None]]:
    """Cause, then drives by strength desc, then regard rules by pk, that are not yet read.

    A caller that already holds the reveal set, or some sheets' matched rules (keyed by
    sheet pk), passes them in so they are not read again.
    """
    if revealed is None:
        revealed = _revealed_set(group)
    known = known_matches or {}
    template = group.creature_template
    hidden: list[tuple[str, CreatureDrive | None, RegardRule | None]] = []
    if template.cause != CauseKind.NONE and (RevealKind.CAUSE, None, None) not in revealed:
        hidden.append((RevealKind.CAUSE, None, None))
    hidden.extend(
        (RevealKind.DRIVE, drive, None)
        for drive in template.drives.order_by("-strength", "pk")
        if (RevealKind.DRIVE, drive.pk, None) not in revealed
    )
    rules = list(template.regard_rules.order_by("pk"))
    matching_ids = {
        match.rule.pk
        for participant in participants
        for match in (
            known[participant.character_sheet.pk]
            if participant.character_sheet.pk in known
            else regard_matches(group, participant.character_sheet, rules)
        )
    }
    hidden.extend(
        (RevealKind.REGARD, None, rule)
        for rule in rules
        if rule.pk in matching_ids and (RevealKind.REGARD, None, rule.pk) not in revealed
    )
    return hidden


def _focus_matches(
    thing: tuple[str, CreatureDrive | None, RegardRule | None],
    focus_kind: str | None,
    focus_drive_id: int | None,
    focus_regard_rule_id: int | None,
    focus_property_id: int | None = None,
) -> bool:
    kind, drive, rule = thing
    if kind != focus_kind:
        return False
    if kind == RevealKind.DRIVE:
        if focus_drive_id is None and focus_property_id is None:
            # "What moves them?": any hidden drive; hidden_things lists them strongest first.
            return drive is not None
        return drive is not None and (
            drive.pk == focus_drive_id
            or (focus_property_id is not None and drive.property_id == focus_property_id)
        )
    if kind == RevealKind.REGARD:
        return rule is not None and rule.pk == focus_regard_rule_id
    return True


def _reveal(
    group: StandoffGroup, thing: tuple[str, CreatureDrive | None, RegardRule | None]
) -> StandoffReveal:
    kind, drive, rule = thing
    reveal, _ = StandoffReveal.objects.get_or_create(
        group=group, kind=kind, drive=drive, regard_rule=rule
    )
    return reveal


@flush_cache_on_error(lambda participant, *_, **__: participant.encounter)
@transaction.atomic
def standoff_read(  # noqa: PLR0913 - the focus kwargs are the read verb's whole payload
    participant: CombatParticipant,
    group: StandoffGroup,
    *,
    focus_kind: str | None = None,
    focus_drive_id: int | None = None,
    focus_regard_rule_id: int | None = None,
    focus_property_id: int | None = None,
) -> StandoffActionResult:
    """Read a group: a partial reveals one hidden thing, a success the one looked for."""
    encounter, group = _lock(participant.encounter, group)
    refusal = _refusal(encounter, group)
    if refusal:
        return _refuse(refusal)
    config = StandoffConfig.load()
    if config.read_check_type is None:
        return _refuse(_MSG_UNCONFIGURED)
    members = active_members(group)
    if not members:
        return _refuse(_MSG_EMPTY)
    participants = list(encounter.participants.filter(status=ParticipantStatus.ACTIVE))
    hidden = hidden_things(group, participants)
    if not hidden:
        return _refuse("There is nothing more to read in that group.")

    sheet = participant.character_sheet
    first, level = _roll_inputs(members)
    difficulty = level_opposition(config.read_check_type, level=level, character=first.objectdb)
    result = perform_check(
        sheet.character,
        config.read_check_type,
        target_difficulty=difficulty,
        extra_modifiers=collect_check_modifiers(sheet, config.read_check_type).total,
    )
    tier = result.success_level
    if tier < 0:
        return StandoffActionResult(
            False, f"You study them. {_word(tier)}. You learn nothing.", success_level=tier
        )
    if tier >= 2:  # noqa: PLR2004 - critical: everything
        chosen = hidden
    elif tier == 1:
        focused = [
            t
            for t in hidden
            if _focus_matches(
                t, focus_kind, focus_drive_id, focus_regard_rule_id, focus_property_id
            )
        ]
        chosen = (focused or hidden)[:1]
    else:
        chosen = [random.choice(hidden)]  # noqa: S311 # NOSONAR game RNG, not crypto
    revealed = [_reveal(group, thing) for thing in chosen]
    # No evaluate_causes here: a read changes none of a cause's inputs (force, emboldening,
    # suppressing regard), so the cause cannot newly fire.
    return StandoffActionResult(
        True, f"You study them. {_word(tier)}.", success_level=tier, revealed=revealed
    )


@dataclass(frozen=True)
class GradingContext:
    """Everything grading a group for one viewer reads, fetched once.

    The roll paths and the web view both build this, so a shown grade and the roll behind
    it come from the same inputs.

    ``resist_increment`` uses the FIRST member's Composure with the group's highest level
    (``max(m.level)``): a group is one creature kind, so members share a Composure and the
    level is the only thing that varies.
    """

    members: list[CombatOpponent]
    drives: list[CreatureDrive]
    matches: list[MatchedRegard]
    mindless_resistance: int
    resist_increment: int

    @property
    def first(self) -> CombatOpponent:
        return self.members[0]

    @property
    def level(self) -> int:
        return max(member.level for member in self.members)

    @property
    def band_shift(self) -> int:
        return band_shift_from(self.matches)


def build_grading_context(
    group: StandoffGroup,
    sheet: CharacterSheet,
    *,
    members: list[CombatOpponent] | None = None,
    matches: list[MatchedRegard] | None = None,
) -> GradingContext:
    """Read a group's members, drives and the viewer's matched rules once."""
    members = active_members(group) if members is None else members
    has_morale = any(tier_has_morale(member) for member in members)
    first_character = members[0].objectdb
    resist = (
        0
        if first_character is None
        else compute_resist_increment(
            first_character, EffortLevel.MEDIUM, level_override=max(m.level for m in members)
        )
    )
    return GradingContext(
        members=members,
        drives=list(group.creature_template.drives.select_related("property")),
        matches=regard_matches(group, sheet) if matches is None else matches,
        mindless_resistance=0 if has_morale else MINDLESS_MORALE_RESISTANCE,
        resist_increment=resist,
    )


def press_grade(
    group: StandoffGroup,
    sheet: CharacterSheet,
    approach: StandoffApproach,
    ctx: GradingContext | None = None,
    targeted_by_capability: dict[int, set[int]] | None = None,
) -> tuple[SocialDifficulty, list[tuple[CreatureDrive, DriveHit]], set[int]]:
    """Grade a press; ``ctx`` and ``targeted_by_capability`` let a caller read them once."""
    if ctx is None:
        ctx = build_grading_context(group, sheet)
    if targeted_by_capability is None:
        targeted_by_capability = targeted_properties_by_capability(
            [approach.capability_id], [drive.property_id for drive in ctx.drives]
        )
    targeted = targeted_by_capability.get(approach.capability_id, set())
    hits = []
    for drive in ctx.drives:
        if drive.property_id not in targeted:
            continue
        strength = drive_strength_from(ctx.matches, drive)
        if strength > 0:
            hits.append((drive, DriveHit(label=drive.property.name, strength=strength)))
    difficulty = social_target_difficulty(
        actor_sheet=sheet,
        target_character=ctx.first.objectdb,
        check_type=approach.check_type,
        target_level=ctx.level,
        drive_hits=[hit for _, hit in hits],
        sway_target=approach.sway_target,
        mindless_resistance=ctx.mindless_resistance,
        resist_increment=ctx.resist_increment,
        extra_bands=ctx.band_shift,
    )
    return difficulty, hits, targeted


def targeted_properties_by_capability(
    capability_ids: list[int], property_ids: list[int]
) -> dict[int, set[int]]:
    """Which of ``property_ids`` each capability has an Application aimed at, in one query."""
    targeted: dict[int, set[int]] = {}
    for capability_id, property_id in Application.objects.filter(
        capability_id__in=capability_ids, target_property_id__in=property_ids
    ).values_list("capability_id", "target_property_id"):
        targeted.setdefault(capability_id, set()).add(property_id)
    return targeted


def press_difficulty(
    group: StandoffGroup,
    sheet: CharacterSheet,
    approach: StandoffApproach,
    ctx: GradingContext | None = None,
) -> SocialDifficulty:
    """The graded difficulty of pressing ``group`` with ``approach`` (needs an active member)."""
    return press_grade(group, sheet, approach, ctx)[0]


def terms_difficulty(
    group: StandoffGroup,
    sheet: CharacterSheet,
    terms: StandoffTerms,
    ctx: GradingContext | None = None,
    config: StandoffConfig | None = None,
) -> SocialDifficulty:
    """The graded difficulty of naming ``terms`` to ``group`` (needs an active member)."""
    config = config or StandoffConfig.load()
    if ctx is None:
        ctx = build_grading_context(group, sheet)
    return social_target_difficulty(
        actor_sheet=sheet,
        target_character=ctx.first.objectdb,
        check_type=config.terms_check_type,
        target_level=ctx.level,
        mindless_resistance=ctx.mindless_resistance,
        resist_increment=ctx.resist_increment,
        extra_bands=terms.difficulty_shift_bands + ctx.band_shift - group.terms_ease,
    )


def _embolden_on_botch(group: StandoffGroup, config: StandoffConfig) -> None:
    group.emboldened_bands += config.botch_force_bands
    group.save(update_fields=["emboldened_bands"])


def _share_shifting_sparks(
    group: StandoffGroup, sheet: CharacterSheet, targeted_property_ids: set[int]
) -> None:
    """Acting on a spark reveals it: share every matched rule that shifted this roll."""
    for match in regard_matches(group, sheet):
        rule = match.rule
        # A drive shift counts when the press aims at that drive, even if the shift took
        # its strength to zero and it no longer registers as a hit.
        shifted = rule.difficulty_shift_bands != 0 or (
            rule.drive_shift != 0 and rule.drive_id in targeted_property_ids
        )
        if shifted:
            StandoffSparkShare.objects.get_or_create(
                group=group, character_sheet=sheet, regard_rule=rule
            )


@flush_cache_on_error(lambda participant, *_, **__: participant.encounter)
@transaction.atomic
def standoff_press(
    participant: CombatParticipant, group: StandoffGroup, approach: StandoffApproach
) -> StandoffActionResult:
    """Press a group with a social approach: a success eases terms, a botch emboldens them."""
    encounter, group = _lock(participant.encounter, group)
    refusal = _refusal(encounter, group)
    if refusal:
        return _refuse(refusal)
    members = active_members(group)
    if not members:
        return _refuse(_MSG_EMPTY)
    config = StandoffConfig.load()
    sheet = participant.character_sheet
    graded, hits, targeted = press_grade(
        group, sheet, approach, build_grading_context(group, sheet, members=members)
    )
    result = perform_check(
        sheet.character,
        approach.check_type,
        target_difficulty=graded.difficulty,
        extra_modifiers=collect_check_modifiers(
            sheet, approach.check_type, extra_contributions=graded.contributions
        ).total,
    )
    _share_shifting_sparks(group, sheet, targeted)
    tier = result.success_level
    message = "Your words do not move them."
    morale_line = ""
    if tier >= 1:
        group.terms_ease += 1
        group.save(update_fields=["terms_ease"])
        if approach.damages_morale:
            before = [morale_state_for(member) for member in members]
            for member in members:
                apply_morale_damage(member, tier * DEMORALIZE_MORALE_PER_LEVEL)
            morale_line = _morale_shift_line(
                group, sheet, before, [morale_state_for(m) for m in members]
            )
        revealed_ids = {
            drive_id for kind, drive_id, _ in _revealed_set(group) if kind == RevealKind.DRIVE
        }
        named = [hit.label for drive, hit in hits if drive.pk in revealed_ids]
        message = "They soften." if not named else f"They soften: {', '.join(named)}."
        steps = group.terms_ease
        message += f" Terms are now {steps} {'step' if steps == 1 else 'steps'} easier."
    elif tier <= BOTCH_LEVEL:
        _embolden_on_botch(group, config)
        message = "It goes badly; they grow bolder."
    attack_lines: list[str] = []
    fight_started = evaluate_causes(encounter, attack_lines)
    return StandoffActionResult(
        success=tier >= 1,
        message=f"{_word(tier)}. {message}",
        success_level=tier,
        fight_started=fight_started,
        morale_line=morale_line,
        attack_line=attack_lines[0] if attack_lines else "",
    )


def _morale_shift_line(
    group: StandoffGroup,
    sheet: CharacterSheet,
    before: list[OpponentMoraleState],
    after: list[OpponentMoraleState],
) -> str:
    """When a press moves the group's morale to a worse state, the room line crediting who did it.

    The persona the actor presents is named, never the character key. Empty when no
    member's state changed. The action layer sends it right after the press line itself,
    so the room reads the press before its consequence.
    """
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    changed = [new for old, new in zip(before, after, strict=True) if old != new]
    if not changed:
        return ""
    word = "break" if OpponentMoraleState.BREAK in changed else "falter"
    return (
        f"{active_persona_for_sheet(sheet).name} shakes the {group.creature_template.name}: "
        f"they {word}."
    )


def _drive_revealed(group: StandoffGroup, property_id: int) -> bool:
    return group.reveals.filter(kind=RevealKind.DRIVE, drive__property_id=property_id).exists()


def _apply_terms(
    members: list[CombatOpponent],
    terms: StandoffTerms,
    config: StandoffConfig,
    actor: CharacterSheet,
    tier: int,
) -> None:
    """Apply the terms' effect; a critical applies ``critical_effect`` instead when authored."""
    effect = (
        terms.critical_effect if tier >= CRITICAL_LEVEL and terms.critical_effect else terms.effect
    )
    condition = config.turn_condition if effect == TermsEffect.TURN else config.pass_condition
    for member in members:
        if effect == TermsEffect.FLEE:
            member.status = OpponentStatus.FLED
            member.save(update_fields=["status"])
        elif condition is not None and member.objectdb is not None:
            apply_condition(member.objectdb, condition, source_character=actor.character)


@flush_cache_on_error(lambda participant, *_, **__: participant.encounter)
@transaction.atomic
def standoff_terms(
    participant: CombatParticipant, group: StandoffGroup, terms: StandoffTerms
) -> StandoffActionResult:
    """Name terms to a group: a partial or better settles it; the last settle ends the standoff."""
    encounter, group = _lock(participant.encounter, group)
    refusal = _refusal(encounter, group)
    if refusal:
        return _refuse(refusal)
    members = active_members(group)
    if not members:
        return _refuse(_MSG_EMPTY)
    if terms.required_drive_id is not None and not _drive_revealed(group, terms.required_drive_id):
        return _refuse("You do not yet know what would make them listen to those terms.")
    config = StandoffConfig.load()
    if config.terms_check_type is None:
        return _refuse(_MSG_UNCONFIGURED)
    sheet = participant.character_sheet
    graded = terms_difficulty(group, sheet, terms)
    result = perform_check(
        sheet.character,
        config.terms_check_type,
        target_difficulty=graded.difficulty,
        extra_modifiers=collect_check_modifiers(
            sheet, config.terms_check_type, extra_contributions=graded.contributions
        ).total,
    )
    if result.outcome is None:
        return _refuse(_MSG_UNCONFIGURED)
    _share_shifting_sparks(group, sheet, set())
    faces, selected = check_outcome_faces(result)
    transaction.on_commit(
        partial(
            maybe_emit_resolution_theater,
            character=sheet.character,
            title=terms.name,
            consequences=faces,
            selected=selected,
            force=True,
        )
    )
    tier = result.success_level
    if tier < 0:
        if tier <= BOTCH_LEVEL:
            _embolden_on_botch(group, config)
        attack_lines: list[str] = []
        fight_started = evaluate_causes(encounter, attack_lines)
        return StandoffActionResult(
            False,
            f"{_word(tier)}. They refuse your terms.",
            success_level=tier,
            fight_started=fight_started,
            attack_line=attack_lines[0] if attack_lines else "",
        )
    _apply_terms(members, terms, config, sheet, tier)
    group.state = StandoffGroupState.SETTLED
    group.settled_outcome = result.outcome
    group.save(update_fields=["state", "settled_outcome"])
    settle_empty_groups(encounter)
    attack_lines = []
    fight_started = False
    if not encounter.standoff_groups.exclude(state=StandoffGroupState.SETTLED).exists():
        complete_standoff(encounter)
    else:
        fight_started = evaluate_causes(encounter, attack_lines)
    return StandoffActionResult(
        True,
        f"{_word(tier)}. {terms.description or 'They accept.'}",
        success_level=tier,
        settled=True,
        fight_started=fight_started,
        attack_line=attack_lines[0] if attack_lines else "",
    )


def _fight_encounter(
    participant: CombatParticipant | None = None,  # noqa: ARG001 - mirrors the verb signature
    encounter: CombatEncounter | None = None,
) -> CombatEncounter:
    """The encounter ``standoff_fight`` was called on, whether passed by position or keyword."""
    if encounter is None:
        msg = "standoff_fight needs an encounter"
        raise TypeError(msg)
    return encounter


@flush_cache_on_error(_fight_encounter)
@transaction.atomic
def standoff_fight(
    participant: CombatParticipant,  # noqa: ARG001 - uniform verb signature
    encounter: CombatEncounter,
) -> StandoffActionResult:
    """The party breaks the standoff and the fight begins."""
    locked, _ = _lock(encounter, None)
    refusal = _refusal(locked, None)
    if refusal:
        return _refuse(refusal)
    started = end_standoff_into_fight(locked, initiated_by_pc_side=True)
    if not started:
        return _refuse(_MSG_OVER)
    return StandoffActionResult(True, FIGHT_BEGINS_MESSAGE, fight_started=True)


@flush_cache_on_error(lambda participant, *_, **__: participant.encounter)
@transaction.atomic
def standoff_share_spark(
    participant: CombatParticipant, group: StandoffGroup, regard_rule: RegardRule
) -> StandoffActionResult:
    """Share what your character feels about this group, if a regard rule applies to you."""
    encounter, group = _lock(participant.encounter, group)
    refusal = _refusal(encounter, group)
    if refusal:
        return _refuse(refusal)
    sheet = participant.character_sheet
    if regard_rule.pk not in {m.rule.pk for m in regard_matches(group, sheet)}:
        return _refuse("That does not apply to you.")
    StandoffSparkShare.objects.get_or_create(
        group=group, character_sheet=sheet, regard_rule=regard_rule
    )
    # No evaluate_causes here: sharing a spark changes none of a cause's inputs (force,
    # emboldening), and the suppression check reads the party's own regard, not shares.
    return StandoffActionResult(True, "You share what you feel.")
