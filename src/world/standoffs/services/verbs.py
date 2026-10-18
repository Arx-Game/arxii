"""The standoff verbs: read, press, name terms, fight and share an angle.

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
from world.combat.models import SpectacleConfig
from world.combat.morale import (
    OpponentMoraleState,
    apply_morale_damage,
    morale_state_for,
    tier_has_morale,
)
from world.combat.spectacle import apply_spectacle, classify_cast
from world.conditions.services import apply_condition
from world.fatigue.constants import EffortLevel
from world.magic.services.capability_requirements import technique_performable
from world.magic.services.techniques import use_technique
from world.magic.services.ultimates import floor_ultimate_check, readied_ultimate
from world.mechanics.models import Application
from world.scenes.action_constants import DIFFICULTY_BAND_STEP
from world.standoffs.constants import (
    FIGHT_BEGINS_MESSAGE,
    LIVE_GROUP_STATES,
    REASON_PROVOKED_PRESS,
    REASON_PROVOKED_TERMS,
    SUCCESS_LEVEL_WORDS,
    RevealKind,
    StandoffGroupState,
    TermsEffect,
)
from world.standoffs.models import (
    FactionRule,
    StandoffAngleShare,
    StandoffApproach,
    StandoffConfig,
    StandoffGroup,
    StandoffReveal,
    StandoffTerms,
)
from world.standoffs.services.character_profile import target_refusal
from world.standoffs.services.faction_rules import (
    MatchedFactionRule,
    band_shift_from,
    drive_strength_from,
    faction_rule_matches,
    shifting_rule_ids,
)
from world.standoffs.services.force import clear_override, evaluate_causes
from world.standoffs.services.language import language_refusal
from world.standoffs.services.profile import (
    GroupDrive,
    group_cause,
    group_drives,
    group_rules,
)
from world.standoffs.services.proposals import close_group_prompts
from world.standoffs.services.routing import complete_standoff
from world.standoffs.services.state import (
    active_members,
    end_standoff_into_fight,
    flush_cache_on_error,
    is_in_standoff,
    settle_empty_groups,
)
from world.standoffs.types import DisplayCast, StandoffActionResult

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant
    from world.magic.models import Technique
    from world.magic.types.techniques import SoulfrayWarning, TechniqueUseResult
    from world.traits.models import CheckOutcome

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


def _refusal(
    encounter: CombatEncounter,
    group: StandoffGroup | None,
    actor_sheet: CharacterSheet | None = None,
) -> str | None:
    """Why a verb on ``group`` cannot run; with ``actor_sheet`` it also enforces consent.

    A group that is a player character is acted on only by another player character and
    only once its player has opted in (#4441).
    """
    if not is_in_standoff(encounter):
        return _MSG_OVER
    if group is not None and group.state not in LIVE_GROUP_STATES:
        return _MSG_SETTLED
    if group is not None and actor_sheet is not None:
        return target_refusal(group.persona, actor_sheet)
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
    return set(group.reveals.values_list("kind", "drive_id", "faction_rule_id"))


def hidden_things(
    group: StandoffGroup,
    participants: list[CombatParticipant],
    *,
    revealed: set[tuple[str, int | None, int | None]] | None = None,
    known_matches: dict[int, list[MatchedFactionRule]] | None = None,
) -> list[tuple[str, GroupDrive | None, FactionRule | None]]:
    """Cause, then drives by strength desc, then faction rules by pk, that are not yet read.

    A caller that already holds the reveal set, or some sheets' matched rules (keyed by
    sheet pk), passes them in so they are not read again.
    """
    if revealed is None:
        revealed = _revealed_set(group)
    known = known_matches or {}
    cause, _margin = group_cause(group)
    hidden: list[tuple[str, GroupDrive | None, FactionRule | None]] = []
    if cause != CauseKind.NONE and (RevealKind.CAUSE, None, None) not in revealed:
        hidden.append((RevealKind.CAUSE, None, None))
    hidden.extend(
        (RevealKind.DRIVE, drive, None)
        for drive in group_drives(group)
        if (RevealKind.DRIVE, drive.property_id, None) not in revealed
    )
    rules = sorted(group_rules(group), key=lambda entry: entry.rule.pk)
    matching_ids = {
        match.rule.pk
        for participant in participants
        for match in (
            known[participant.character_sheet.pk]
            if participant.character_sheet.pk in known
            else faction_rule_matches(group, participant.character_sheet, rules)
        )
    }
    hidden.extend(
        (RevealKind.FACTION_RULE, None, entry.rule)
        for entry in rules
        if entry.rule.pk in matching_ids
        and (RevealKind.FACTION_RULE, None, entry.rule.pk) not in revealed
    )
    return hidden


def _focus_matches(
    thing: tuple[str, GroupDrive | None, FactionRule | None],
    focus_kind: str | None,
    focus_faction_rule_id: int | None,
    focus_property_id: int | None = None,
) -> bool:
    kind, drive, rule = thing
    if kind != focus_kind:
        return False
    if kind == RevealKind.DRIVE:
        if focus_property_id is None:
            # "What moves them?": any hidden drive; hidden_things lists them strongest first.
            return drive is not None
        return drive is not None and drive.property_id == focus_property_id
    if kind == RevealKind.FACTION_RULE:
        return rule is not None and rule.pk == focus_faction_rule_id
    return True


def _reveal(
    group: StandoffGroup, thing: tuple[str, GroupDrive | None, FactionRule | None]
) -> StandoffReveal:
    kind, drive, rule = thing
    reveal, _ = StandoffReveal.objects.get_or_create(
        group=group,
        kind=kind,
        drive=drive.property if drive is not None else None,
        faction_rule=rule,
    )
    return reveal


@flush_cache_on_error(lambda participant, *_, **__: participant.encounter)
@transaction.atomic
def standoff_read(
    participant: CombatParticipant,
    group: StandoffGroup,
    *,
    focus_kind: str | None = None,
    focus_faction_rule_id: int | None = None,
    focus_property_id: int | None = None,
) -> StandoffActionResult:
    """Read a group: a partial reveals one hidden thing, a success the one looked for."""
    encounter, group = _lock(participant.encounter, group)
    refusal = _refusal(encounter, group, participant.character_sheet)
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
        cause_lines: list[str] = []
        fight_started = evaluate_causes(encounter, cause_lines, after_action=True)
        return StandoffActionResult(
            False,
            f"You study them. {_word(tier)}. You learn nothing.",
            success_level=tier,
            fight_started=fight_started,
            cause_lines=cause_lines,
        )
    if tier >= 2:  # noqa: PLR2004 - critical: everything
        chosen = hidden
    elif tier == 1:
        focused = [
            t
            for t in hidden
            if _focus_matches(t, focus_kind, focus_faction_rule_id, focus_property_id)
        ]
        chosen = (focused or hidden)[:1]
    else:
        chosen = [random.choice(hidden)]  # noqa: S311 # NOSONAR game RNG, not crypto
    revealed = [_reveal(group, thing) for thing in chosen]
    # A read changes none of a cause's inputs, but every action is a point where the cause
    # is tested: a GM's "hold for one action" is tested again after the next one.
    cause_lines = []
    fight_started = evaluate_causes(encounter, cause_lines, after_action=True)
    return StandoffActionResult(
        True,
        f"You study them. {_word(tier)}.",
        success_level=tier,
        revealed=revealed,
        fight_started=fight_started,
        cause_lines=cause_lines,
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
    drives: list[GroupDrive]
    matches: list[MatchedFactionRule]
    mindless_resistance: int
    resist_increment: int
    regard: int = 0
    regard_bands: int = 0

    @property
    def first(self) -> CombatOpponent:
        return self.members[0]

    @property
    def level(self) -> int:
        return max(member.level for member in self.members)

    @property
    def band_shift(self) -> int:
        return band_shift_from(self.matches)

    @property
    def regard_base(self) -> int:
        """The named NPC's regard for the actor, as the shared function's base (#4373)."""
        return DIFFICULTY_BAND_STEP * self.regard_bands


def regard_for(
    group: StandoffGroup, sheet: CharacterSheet, config: StandoffConfig
) -> tuple[int, int]:
    """A named NPC group's ``NpcRegard`` for the actor's presented persona, and its bands.

    Returns ``(regard, bands)``. Bands are positive when the regard hardens a press or
    terms (dislike) and negative when it eases them: one band per full
    ``config.regard_per_band`` points, at most ``config.regard_max_bands``. A creature
    template group has no regard: ``(0, 0)``.
    """
    if group.persona_id is None:
        return 0, 0
    from world.npc_services.regard import get_regard  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    regard = get_regard(group.persona, active_persona_for_sheet(sheet))
    steps = min(config.regard_max_bands, abs(regard) // max(1, config.regard_per_band))
    return regard, (-steps if regard > 0 else steps)


def build_grading_context(
    group: StandoffGroup,
    sheet: CharacterSheet,
    *,
    members: list[CombatOpponent] | None = None,
    matches: list[MatchedFactionRule] | None = None,
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
    regard, regard_bands = regard_for(group, sheet, StandoffConfig.load())
    return GradingContext(
        members=members,
        drives=group_drives(group),
        matches=faction_rule_matches(group, sheet) if matches is None else matches,
        mindless_resistance=0 if has_morale else MINDLESS_MORALE_RESISTANCE,
        resist_increment=resist,
        regard=regard,
        regard_bands=regard_bands,
    )


def press_grade(
    group: StandoffGroup,
    sheet: CharacterSheet,
    approach: StandoffApproach,
    ctx: GradingContext | None = None,
    targeted_by_capability: dict[int, set[int]] | None = None,
) -> tuple[SocialDifficulty, list[tuple[GroupDrive, DriveHit]], set[int]]:
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
        base_difficulty=ctx.regard_base,
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


def morale_terms_ease(members: list[CombatOpponent], config: StandoffConfig) -> int:
    """Bands terms ease because the group's worst member is shaken (broken beats faltering)."""
    states = {morale_state_for(member) for member in members}
    if OpponentMoraleState.BREAK in states:
        return config.terms_ease_broken
    if OpponentMoraleState.FALTER in states:
        return config.terms_ease_faltering
    return 0


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
        base_difficulty=ctx.regard_base,
        target_level=ctx.level,
        mindless_resistance=ctx.mindless_resistance,
        resist_increment=ctx.resist_increment,
        extra_bands=(
            terms.difficulty_shift_bands
            + ctx.band_shift
            - group.terms_ease
            - morale_terms_ease(ctx.members, config)
        ),
    )


def _embolden_on_botch(group: StandoffGroup, config: StandoffConfig) -> None:
    """A botch emboldens the group and ends any GM override of its cause."""
    group.emboldened_bands += config.botch_force_bands
    group.save(update_fields=["emboldened_bands"])
    clear_override(group)


def _share_shifting_angles(
    group: StandoffGroup, sheet: CharacterSheet, targeted_property_ids: set[int]
) -> None:
    """Acting on an angle reveals it: share every matched rule that shifted this roll.

    A drive shift counts when the press aims at that drive, even if the shift took its
    strength to zero and it no longer registers as a hit.
    """
    matches = faction_rule_matches(group, sheet)
    shifted = shifting_rule_ids(matches, targeted_property_ids)
    for match in matches:
        if match.rule.pk in shifted:
            StandoffAngleShare.objects.get_or_create(
                group=group, character_sheet=sheet, faction_rule=match.rule
            )


def _press_check(
    sheet: CharacterSheet,
    approach: StandoffApproach,
    graded: SocialDifficulty,
    technique: Technique | None,
    *,
    confirm_soulfray_risk: bool = False,
) -> tuple[CheckResult | None, TechniqueUseResult | None]:
    """Roll the press. A casting approach casts ``technique`` as the check, harmless.

    Returns ``(None, use)`` when the cast never resolved: the caster carries Soulfray and
    has not accepted the risk (``use.soulfray_warning``), and nothing was spent.
    """
    if technique is None:
        return (
            perform_check(
                sheet.character,
                approach.check_type,
                target_difficulty=graded.difficulty,
                extra_modifiers=collect_check_modifiers(
                    sheet, approach.check_type, extra_contributions=graded.contributions
                ).total,
            ),
            None,
        )
    captured: dict[str, CheckResult] = {}

    def _resolve_fn(*, power: int, ledger: object, extra_modifiers: int = 0) -> DisplayCast:  # noqa: ARG001
        check = perform_check(
            sheet.character,
            approach.check_type,
            target_difficulty=graded.difficulty,
            extra_modifiers=extra_modifiers
            + collect_check_modifiers(
                sheet, approach.check_type, extra_contributions=graded.contributions
            ).total,
        )
        captured["check"] = floor_ultimate_check(check, technique)
        return DisplayCast(check_result=captured["check"])

    use = use_technique(
        character=sheet.character,
        technique=technique,
        resolve_fn=_resolve_fn,
        confirm_soulfray_risk=confirm_soulfray_risk,
        lethal=False,
    )
    return captured.get("check"), use


def _display_morale_line(  # noqa: PLR0913 - the display's full context
    encounter: CombatEncounter,
    sheet: CharacterSheet,
    technique: Technique,
    use: TechniqueUseResult,
    tier: int,
    members: list[CombatOpponent],
) -> str | None:
    """The spectacle credit line for a display; ``None`` when the cast is not a display.

    A display already spent on every witness (the repeat rule) returns ``""``, not ``None``,
    so the caller never substitutes ordinary morale damage for it.
    """
    kind = classify_cast(
        technique=technique,
        runtime_intensity=use.runtime_intensity,
        success_level=tier,
        config=SpectacleConfig.load(),
    )
    if kind is None:
        return None
    spectacle = apply_spectacle(
        encounter=encounter,
        caster_sheet=sheet,
        kind=kind,
        display_name=technique.name,
        success_level=tier,
        technique=technique,
        witnesses=members,
    )
    return " ".join(spectacle.lines)


def _technique_refusal(
    sheet: CharacterSheet, approach: StandoffApproach, technique: Technique | None
) -> str | None:
    """Why the technique does not fit this approach: a display needs one the actor can cast.

    Castable means known (or this Audere's readied ultimate) and performable right now.
    """
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    if not approach.casts_technique:
        return None if technique is None else "That approach does not cast a technique."
    if technique is None:
        return "Choose one of your techniques to display."
    known = CharacterTechnique.objects.filter(character=sheet, technique=technique).exists()
    if not known:
        readied = readied_ultimate(sheet)
        known = readied is not None and readied.technique_id == technique.pk
    if not known:
        return "Choose one of your techniques to display."
    if not technique_performable(sheet, technique):
        return "You cannot perform that technique right now."
    return None


def _soulfray_refusal(warning: SoulfrayWarning) -> StandoffActionResult:
    """The cast stopped at the Soulfray checkpoint: warn, spend nothing, offer to accept."""
    return StandoffActionResult(
        success=False,
        message=f"{warning.stage_description} Accept the Soulfray risk to display anyway.",
        soulfray_warning=warning,
    )


def _press_refusal(  # noqa: PLR0913 - the press's whole pre-roll context
    encounter: CombatEncounter,
    group: StandoffGroup,
    members: list[CombatOpponent],
    sheet: CharacterSheet,
    approach: StandoffApproach,
    technique: Technique | None,
) -> str | None:
    """Why this press cannot be rolled, checked in order; None when it can."""
    refusal = _refusal(encounter, group, sheet)
    if refusal:
        return refusal
    if not members:
        return _MSG_EMPTY
    technique_refusal = _technique_refusal(sheet, approach, technique)
    if technique_refusal:
        return technique_refusal
    if approach.is_verbal:
        return language_refusal(group, sheet, verbal=True) or None
    return None


@flush_cache_on_error(lambda participant, *_, **__: participant.encounter)
@transaction.atomic
def standoff_press(
    participant: CombatParticipant,
    group: StandoffGroup,
    approach: StandoffApproach,
    technique: Technique | None = None,
    *,
    confirm_soulfray_risk: bool = False,
) -> StandoffActionResult:
    """Press a group with a social approach: a success eases terms, a botch emboldens them.

    A casting approach (a display of power) casts ``technique`` as its check; a cast that
    earns a display shakes the group through the spectacle service. A caster carrying
    Soulfray is refused with the warning, spending nothing, until ``confirm_soulfray_risk``.
    """
    encounter, group = _lock(participant.encounter, group)
    sheet = participant.character_sheet
    members = active_members(group)
    refusal = _press_refusal(encounter, group, members, sheet, approach, technique)
    if refusal:
        return _refuse(refusal)
    config = StandoffConfig.load()
    graded, hits, targeted = press_grade(
        group, sheet, approach, build_grading_context(group, sheet, members=members)
    )
    result, use = _press_check(
        sheet, approach, graded, technique, confirm_soulfray_risk=confirm_soulfray_risk
    )
    if result is None:
        return _failed_press(use)
    _share_shifting_angles(group, sheet, targeted)
    tier = result.success_level
    # A gesture or a display is not words (#4373).
    message = "Your words do not move them." if approach.is_verbal else "It does not move them."
    morale_line = ""
    if tier >= 1:
        group.terms_ease += 1
        group.save(update_fields=["terms_ease"])
        display_line = (
            None
            if use is None or technique is None
            else _display_morale_line(encounter, sheet, technique, use, tier, members)
        )
        morale_line = display_line or ""
        if approach.damages_morale and display_line is None:
            morale_line = _press_morale_damage(group, sheet, members, tier)
        message = _press_terms_message(group, hits)
    elif tier <= BOTCH_LEVEL:
        _embolden_on_botch(group, config)
        message = "It goes badly; they grow bolder."
    cause_lines: list[str] = []
    fight_started = evaluate_causes(
        encounter,
        cause_lines,
        provoked=group if tier <= BOTCH_LEVEL else None,
        provocation=REASON_PROVOKED_PRESS,
        after_action=True,
    )
    return StandoffActionResult(
        success=tier >= 1,
        message=f"{_word(tier)}. {message}",
        success_level=tier,
        fight_started=fight_started,
        morale_line=morale_line,
        cause_lines=cause_lines,
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
    return f"{active_persona_for_sheet(sheet).name} shakes {group.referent}: they {word}."


def _drive_revealed(group: StandoffGroup, property_id: int) -> bool:
    return group.reveals.filter(kind=RevealKind.DRIVE, drive_id=property_id).exists()


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
    refusal = _refusal(encounter, group, participant.character_sheet)
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
    spoken_refusal = language_refusal(group, sheet, verbal=False)
    if spoken_refusal:
        return _refuse(spoken_refusal)
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
    _share_shifting_angles(group, sheet, set())
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
        return _terms_refused(encounter, group, config, tier)
    _apply_terms(members, terms, config, sheet, tier)
    return _terms_accepted(encounter, group, terms, result.outcome, tier)


def _terms_refused(
    encounter: CombatEncounter, group: StandoffGroup, config: StandoffConfig, tier: int
) -> StandoffActionResult:
    """Terms failed: a botch emboldens the group and counts as a provocation."""
    botched = tier <= BOTCH_LEVEL
    if botched:
        _embolden_on_botch(group, config)
    cause_lines: list[str] = []
    fight_started = evaluate_causes(
        encounter,
        cause_lines,
        provoked=group if botched else None,
        provocation=REASON_PROVOKED_TERMS,
        after_action=True,
    )
    return StandoffActionResult(
        False,
        f"{_word(tier)}. They refuse your terms.",
        success_level=tier,
        fight_started=fight_started,
        cause_lines=cause_lines,
    )


def _terms_accepted(
    encounter: CombatEncounter,
    group: StandoffGroup,
    terms: StandoffTerms,
    outcome: CheckOutcome,
    tier: int,
) -> StandoffActionResult:
    """Terms held: the group settles; the last settle completes the standoff."""
    group.state = StandoffGroupState.SETTLED
    group.settled_outcome = outcome
    group.save(update_fields=["state", "settled_outcome"])
    close_group_prompts(group, "They accepted terms.")
    settle_empty_groups(encounter)
    cause_lines: list[str] = []
    fight_started = False
    if not encounter.standoff_groups.exclude(state=StandoffGroupState.SETTLED).exists():
        complete_standoff(encounter)
    else:
        fight_started = evaluate_causes(encounter, cause_lines, after_action=True)
    return StandoffActionResult(
        True,
        f"{_word(tier)}. {terms.description or 'They accept.'}",
        success_level=tier,
        settled=True,
        fight_started=fight_started,
        cause_lines=cause_lines,
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
def standoff_share_angle(
    participant: CombatParticipant, group: StandoffGroup, faction_rule: FactionRule
) -> StandoffActionResult:
    """Share what your character feels about this group, if a faction rule applies to you."""
    encounter, group = _lock(participant.encounter, group)
    refusal = _refusal(encounter, group)
    if refusal:
        return _refuse(refusal)
    sheet = participant.character_sheet
    if faction_rule.pk not in {m.rule.pk for m in faction_rule_matches(group, sheet)}:
        return _refuse("That does not apply to you.")
    StandoffAngleShare.objects.get_or_create(
        group=group, character_sheet=sheet, faction_rule=faction_rule
    )
    # Sharing changes none of a cause's inputs, but it is an action: a held cause is tested.
    cause_lines: list[str] = []
    fight_started = evaluate_causes(encounter, cause_lines, after_action=True)
    return StandoffActionResult(
        True,
        "You share what you feel.",
        fight_started=fight_started,
        cause_lines=cause_lines,
    )


def _press_morale_damage(
    group: StandoffGroup, sheet: CharacterSheet, members: list[CombatOpponent], tier: int
) -> str:
    """Apply ordinary press morale damage and report its before/after shift."""
    before = [morale_state_for(member) for member in members]
    for member in members:
        apply_morale_damage(member, tier * DEMORALIZE_MORALE_PER_LEVEL)
    return _morale_shift_line(group, sheet, before, [morale_state_for(m) for m in members])


def _press_terms_message(group: StandoffGroup, hits: list[tuple[GroupDrive, DriveHit]]) -> str:
    """Name only revealed drives and report the updated terms ease."""
    revealed_ids = {
        drive_id for kind, drive_id, _ in _revealed_set(group) if kind == RevealKind.DRIVE
    }
    named = [hit.label for drive, hit in hits if drive.property_id in revealed_ids]
    message = "They soften." if not named else f"They soften: {', '.join(named)}."
    steps = group.terms_ease
    message += f" Terms are now {steps} {'step' if steps == 1 else 'steps'} easier."
    return message


def _failed_press(use: TechniqueUseResult | None) -> StandoffActionResult:
    """Preserve the soulfray warning or ordinary display failure without spending."""
    if use is not None and use.soulfray_warning is not None:
        return _soulfray_refusal(use.soulfray_warning)
    return _refuse("The display falters before it begins.")
