"""The standoff verbs: read, press, name terms, fight and share a spark.

Every verb is one transaction that locks the encounter row, then the group row, and
re-reads state before it rolls anything: a verb dispatched after the standoff ended
(fight begun, group settled) is refused with no roll. Lock order is always encounter then
group, matching ``end_standoff_into_fight``.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from django.db import transaction

from world.checks.services import collect_check_modifiers, level_opposition, perform_check
from world.checks.social_target import DriveHit, SocialDifficulty, social_target_difficulty
from world.combat.constants import (
    DEMORALIZE_MORALE_PER_LEVEL,
    MINDLESS_MORALE_RESISTANCE,
    CauseKind,
    OpponentStatus,
    ParticipantStatus,
)
from world.combat.morale import apply_morale_damage, tier_has_morale
from world.conditions.services import apply_condition
from world.mechanics.models import Application
from world.standoffs.constants import RevealKind, StandoffGroupState, TermsEffect
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
from world.standoffs.services.regard import band_shift_toward, drive_strength_toward, regard_matches
from world.standoffs.services.routing import complete_standoff
from world.standoffs.services.state import (
    active_members,
    end_standoff_into_fight,
    is_in_standoff,
    settle_empty_groups,
)
from world.standoffs.types import StandoffActionResult

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant

BOTCH_LEVEL = -2
_MSG_OVER = "The standoff is over."
_MSG_SETTLED = "That group is no longer in the standoff."
_MSG_EMPTY = "There is nobody left in that group."
_MSG_UNCONFIGURED = "Standoffs are not set up for this check."


def _lock(
    encounter: CombatEncounter, group: StandoffGroup | None
) -> tuple[CombatEncounter, StandoffGroup | None]:
    """Lock the encounter row, then the group row, and re-read both."""
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


def _refuse(message: str) -> StandoffActionResult:
    return StandoffActionResult(success=False, message=message)


def _roll_inputs(
    members: list[CombatOpponent],
) -> tuple[CombatOpponent, int]:
    return members[0], max(member.level for member in members)


def _revealed_set(group: StandoffGroup) -> set[tuple[str, int | None, int | None]]:
    return set(group.reveals.values_list("kind", "drive_id", "regard_rule_id"))


def _hidden_things(
    group: StandoffGroup, participants: list[CombatParticipant]
) -> list[tuple[str, CreatureDrive | None, RegardRule | None]]:
    """Cause, then drives by strength desc, then regard rules by pk, that are not yet read."""
    revealed = _revealed_set(group)
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
        for match in regard_matches(group, participant.character_sheet, rules)
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
    hidden = _hidden_things(group, participants)
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
        return StandoffActionResult(False, "You learn nothing.", success_level=tier)
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
        chosen = [random.choice(hidden)]  # noqa: S311 - game roll
    revealed = [_reveal(group, thing) for thing in chosen]
    return StandoffActionResult(True, "You read the group.", success_level=tier, revealed=revealed)


def _press_grade(
    group: StandoffGroup, sheet: CharacterSheet, approach: StandoffApproach
) -> tuple[SocialDifficulty, list[tuple[CreatureDrive, DriveHit]], set[int]]:
    members = active_members(group)
    first, level = _roll_inputs(members)
    drives = list(group.creature_template.drives.select_related("property"))
    targeted = set(
        Application.objects.filter(
            capability_id=approach.capability_id,
            target_property_id__in=[drive.property_id for drive in drives],
        ).values_list("target_property_id", flat=True)
    )
    hits = []
    for drive in drives:
        if drive.property_id not in targeted:
            continue
        strength = drive_strength_toward(group, drive, sheet)
        if strength > 0:
            hits.append((drive, DriveHit(label=drive.property.name, strength=strength)))
    difficulty = social_target_difficulty(
        actor_sheet=sheet,
        target_character=first.objectdb,
        check_type=approach.check_type,
        target_level=level,
        drive_hits=[hit for _, hit in hits],
        sway_target=approach.sway_target,
        mindless_resistance=(
            0 if any(tier_has_morale(m) for m in members) else MINDLESS_MORALE_RESISTANCE
        ),
        extra_bands=band_shift_toward(group, sheet),
    )
    return difficulty, hits, targeted


def press_difficulty(
    group: StandoffGroup, sheet: CharacterSheet, approach: StandoffApproach
) -> SocialDifficulty:
    """The graded difficulty of pressing ``group`` with ``approach`` (needs an active member)."""
    return _press_grade(group, sheet, approach)[0]


def terms_difficulty(
    group: StandoffGroup, sheet: CharacterSheet, terms: StandoffTerms
) -> SocialDifficulty:
    """The graded difficulty of naming ``terms`` to ``group`` (needs an active member)."""
    config = StandoffConfig.load()
    members = active_members(group)
    first, level = _roll_inputs(members)
    return social_target_difficulty(
        actor_sheet=sheet,
        target_character=first.objectdb,
        check_type=config.terms_check_type,
        target_level=level,
        mindless_resistance=(
            0 if any(tier_has_morale(m) for m in members) else MINDLESS_MORALE_RESISTANCE
        ),
        extra_bands=terms.difficulty_shift_bands
        + band_shift_toward(group, sheet)
        - group.terms_ease,
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
    graded, hits, targeted = _press_grade(group, sheet, approach)
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
    if tier >= 1:
        group.terms_ease += tier
        group.save(update_fields=["terms_ease"])
        if approach.damages_morale:
            for member in members:
                apply_morale_damage(member, tier * DEMORALIZE_MORALE_PER_LEVEL)
        revealed_ids = {
            drive_id for kind, drive_id, _ in _revealed_set(group) if kind == RevealKind.DRIVE
        }
        named = [hit.label for drive, hit in hits if drive.pk in revealed_ids]
        message = "They soften." if not named else f"They soften: {', '.join(named)}."
    elif tier <= BOTCH_LEVEL:
        _embolden_on_botch(group, config)
        message = "It goes badly; they grow bolder."
    fight_started = evaluate_causes(encounter)
    return StandoffActionResult(
        success=tier >= 1,
        message=message,
        success_level=tier,
        fight_started=fight_started,
    )


def _drive_revealed(group: StandoffGroup, property_id: int) -> bool:
    return group.reveals.filter(kind=RevealKind.DRIVE, drive__property_id=property_id).exists()


def _apply_terms(
    members: list[CombatOpponent],
    terms: StandoffTerms,
    config: StandoffConfig,
    actor: CharacterSheet,
) -> None:
    condition = config.turn_condition if terms.effect == TermsEffect.TURN else config.pass_condition
    for member in members:
        if terms.effect == TermsEffect.FLEE:
            member.status = OpponentStatus.FLED
            member.save(update_fields=["status"])
        elif condition is not None and member.objectdb is not None:
            apply_condition(member.objectdb, condition, source_character=actor.character)


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
    _share_shifting_sparks(group, sheet, set())
    tier = result.success_level
    if tier < 0:
        if tier <= BOTCH_LEVEL:
            _embolden_on_botch(group, config)
        fight_started = evaluate_causes(encounter)
        return StandoffActionResult(
            False, "They refuse your terms.", success_level=tier, fight_started=fight_started
        )
    _apply_terms(members, terms, config, sheet)
    group.state = StandoffGroupState.SETTLED
    group.settled_outcome = result.outcome
    group.save(update_fields=["state", "settled_outcome"])
    settle_empty_groups(encounter)
    if not encounter.standoff_groups.exclude(state=StandoffGroupState.SETTLED).exists():
        complete_standoff(encounter)
    else:
        evaluate_causes(encounter)
    return StandoffActionResult(True, "They accept.", success_level=tier, settled=True)


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
    return StandoffActionResult(True, "The fight begins.", fight_started=True)


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
    return StandoffActionResult(True, "You share what you feel.")
