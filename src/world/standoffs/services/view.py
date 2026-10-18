"""What one participant may see of a standoff.

Privacy is the point of this module. Everything is built for a single viewer: their own
angles, faction rule detail only where it applies to them or was shared, and unread causes,
drives and rules only as a count. A hidden drive still shapes every grade (it is the real
roll math) but is never named.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from world.checks.services import (
    collect_check_modifiers,
    level_opposition,
    preview_check_difficulty,
)
from world.combat.constants import CauseKind, ParticipantStatus
from world.combat.morale import OpponentMoraleState, morale_state_for
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.services import difficulty_indicator_for_rank_difference
from world.progression.selectors import current_path_for_character
from world.standoffs.constants import LIVE_GROUP_STATES, RevealKind
from world.standoffs.models import (
    StandoffAngleShare,
    StandoffApproach,
    StandoffCauseGloss,
    StandoffConfig,
    StandoffGroup,
    StandoffReveal,
    StandoffTerms,
)
from world.standoffs.services.describe import describe_reveals
from world.standoffs.services.faction_rules import (
    MatchedFactionRule,
    faction_rule_matches,
    shifting_rule_ids,
)
from world.standoffs.services.language import group_languages, language_refusal
from world.standoffs.services.profile import GroupDrive, group_cause, group_drives
from world.standoffs.services.state import active_members, is_in_standoff
from world.standoffs.services.verbs import (
    build_grading_context,
    display_cast_terms_for_path,
    hidden_things,
    morale_terms_ease,
    press_grade,
    targeted_properties_by_capability,
    terms_difficulty,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.social_target import SocialDifficulty
    from world.checks.types import ExtraTraitTerm, ModifierContribution
    from world.combat.models import CombatEncounter
    from world.magic.models import Technique


@dataclass(frozen=True)
class DriveView:
    label: str
    strength: str


@dataclass(frozen=True)
class GroupView:
    group_id: int
    name: str
    member_count: int
    state: str
    terms_ease: int
    cause: str | None
    cause_gloss: str | None
    hidden_count: int
    drives: list[DriveView]
    revealed_faction_rules: list[str]
    read_check: str
    read_grade: str
    read_grade_label: str
    morale_state: str = OpponentMoraleState.STEADY
    terms_morale_ease: int = 0
    emboldened: bool = False


@dataclass(frozen=True)
class LeverView:
    """One line saying why an approach may work; ``is_angle`` marks the viewer's own angle."""

    text: str
    is_angle: bool


@dataclass(frozen=True)
class ApproachView:
    approach_id: int
    group_id: int
    name: str
    grade: str
    grade_label: str
    check_caption: str
    levers: list[LeverView]
    hits_revealed_drive: bool
    casts_technique: bool = False
    refusal: str = ""
    # A casting approach's grade per display technique: each technique's skill term changes
    # the roll, so the grade shown for a picked technique must carry it (#4450).
    technique_grades: list[TechniqueGradeView] = field(default_factory=list)


@dataclass(frozen=True)
class TechniqueGradeView:
    """A casting approach's grade when pressed with one display technique."""

    technique_id: int
    grade: str
    grade_label: str


@dataclass(frozen=True)
class AngleView:
    group_id: int
    faction_rule_id: int
    text: str
    shared: bool


@dataclass(frozen=True)
class TermsView:
    terms_id: int
    name: str
    group_id: int
    description: str
    grade: str
    grade_label: str
    critical_label: str = ""
    levers: list[LeverView] = field(default_factory=list)
    refusal: str = ""


@dataclass(frozen=True)
class DisplayTechniqueView:
    """A technique the viewer may cast as a display of power."""

    technique_id: int
    name: str


@dataclass(frozen=True)
class StandoffView:
    place: str = ""
    groups: list[GroupView] = field(default_factory=list)
    approaches: list[ApproachView] = field(default_factory=list)
    terms: list[TermsView] = field(default_factory=list)
    angles: list[AngleView] = field(default_factory=list)
    shared_angles: list[AngleView] = field(default_factory=list)
    display_techniques: list[DisplayTechniqueView] = field(default_factory=list)


def grade_label(grade: str) -> str:
    """The human label of a ``DifficultyIndicator`` value (``very_hard`` -> "Very Hard")."""
    return DifficultyIndicator(grade).label if grade else ""


# A check type's skill terms as a cache key: (trait id, weight) per term.
_TermsKey = tuple[tuple[int, Decimal], ...]


@dataclass
class _Grader:
    """Grades one viewer's checks for one build; its dicts live and die with that build.

    The roll's own modifier total feeds the preview, so the shown grade matches the roll.
    ``base_totals`` holds the viewer's gathered modifiers per (check type, skill terms) and
    ``graded`` the finished grade per (check type, skill terms, difficulty, modifiers). The
    roll adds the social contributions on top of the gathered total as a plain sum.
    """

    sheet: CharacterSheet
    base_totals: dict[tuple[int, _TermsKey], int] = field(default_factory=dict)
    graded: dict[tuple[int, _TermsKey, int, int], str] = field(default_factory=dict)

    def grade(
        self,
        check_type: CheckType,
        difficulty: int,
        contributions: list[ModifierContribution],
        extra_traits: Sequence[ExtraTraitTerm] = (),
    ) -> str:
        """The shown grade. ``extra_traits`` are the roll's skill terms (a display cast's)."""
        terms_key = tuple((term.trait.pk, term.weight) for term in extra_traits)
        base_key = (check_type.pk, terms_key)
        if base_key not in self.base_totals:
            self.base_totals[base_key] = collect_check_modifiers(
                self.sheet, check_type, extra_traits=extra_traits
            ).total
        extra = self.base_totals[base_key] + sum(c.value for c in contributions)
        key = (*base_key, difficulty, extra)
        if key not in self.graded:
            rank = preview_check_difficulty(
                self.sheet.character, check_type, difficulty, extra, extra_traits=extra_traits
            )
            self.graded[key] = difficulty_indicator_for_rank_difference(rank).value
        return self.graded[key]


@dataclass(frozen=True)
class _GroupFacts:
    """One group's reveals and the viewer's matched rules, read once."""

    group: StandoffGroup
    reveals: list[StandoffReveal]
    matches: list[MatchedFactionRule]
    shares: list[StandoffAngleShare]
    drives: list[GroupDrive]

    @property
    def revealed_drive_property_ids(self) -> set[int]:
        return {r.drive_id for r in self.reveals if r.kind == RevealKind.DRIVE and r.drive_id}

    @property
    def revealed_set(self) -> set[tuple[str, int | None, int | None]]:
        return {(r.kind, r.drive_id, r.faction_rule_id) for r in self.reveals}

    @property
    def shared_rule_ids(self) -> set[int]:
        return {s.faction_rule_id for s in self.shares}

    @property
    def revealed_rule_ids(self) -> set[int]:
        return {
            r.faction_rule_id
            for r in self.reveals
            if r.kind == RevealKind.FACTION_RULE and r.faction_rule_id is not None
        }


def _group_view(  # noqa: PLR0913 - one viewer-and-group context, built once per group
    facts: _GroupFacts,
    viewer: CharacterSheet,
    member_count: int,
    hidden_count: int,
    read: tuple[str, str] = ("", ""),
    morale_state: str = OpponentMoraleState.STEADY,
    terms_morale_ease: int = 0,
) -> GroupView:
    group = facts.group
    cause, _margin = group_cause(group)
    cause_known = cause != CauseKind.NONE and any(r.kind == RevealKind.CAUSE for r in facts.reveals)
    strengths = {drive.property_id: drive.strength_label for drive in facts.drives}
    drives = [
        DriveView(r.drive.name, strengths[r.drive_id])
        for r in facts.reveals
        if r.kind == RevealKind.DRIVE and r.drive is not None and r.drive_id in strengths
    ]
    faction_reveals = [r for r in facts.reveals if r.kind == RevealKind.FACTION_RULE]
    return GroupView(
        group_id=group.pk,
        name=group.name,
        member_count=member_count,
        state=group.state,
        terms_ease=group.terms_ease,
        cause=CauseKind(cause).label if cause_known else None,
        cause_gloss=_cause_gloss(cause) if cause_known else None,
        hidden_count=hidden_count,
        drives=drives,
        revealed_faction_rules=describe_reveals(
            group,
            faction_reveals,
            viewer,
            matching_rule_ids={m.rule.pk for m in facts.matches},
            shared_rule_ids=facts.shared_rule_ids,
        ),
        read_check=read[0],
        read_grade=read[1],
        read_grade_label=grade_label(read[1]),
        morale_state=morale_state,
        terms_morale_ease=terms_morale_ease,
        emboldened=group.emboldened_bands > 0,
    )


def _cause_gloss(cause: str) -> str | None:
    """The staff-authored gloss for a cause, or None when none is authored."""
    row = StandoffCauseGloss.objects.filter(cause=cause).first()
    return row.text if row is not None and row.text else None


def _levers(facts: _GroupFacts, hits: list, targeted: set[int]) -> tuple[list[LeverView], bool]:
    """Revealed drives the approach hits, and faction rule text only once that rule was read.

    Returns the lever lines and whether any is a revealed drive hit. Drives read
    "hits <Drive> (<Strength>)"; a faction rule lever is always the viewer's own angle
    (``facts.matches`` are their rules), so it reads "your angle: <revealed text>".

    A shared angle is not a read: auto-sharing after a press must not expose detail the
    group never revealed, and describe_reveals (telnet) gates on the reveal too.
    """
    revealed_props = facts.revealed_drive_property_ids
    hit_levers = [
        LeverView(f"hits {hit.label} ({drive.strength_label})", is_angle=False)
        for drive, hit in hits
        if drive.property_id in revealed_props
    ]
    levers = list(hit_levers)
    revealed_rules = facts.revealed_rule_ids
    shifting = shifting_rule_ids(facts.matches, targeted)
    for match in facts.matches:
        rule = match.rule
        if rule.pk in shifting and rule.pk in revealed_rules and rule.revealed_text:
            levers.append(LeverView(f"your angle: {rule.revealed_text}", is_angle=True))
    return levers, bool(hit_levers)


def regard_lever(group: StandoffGroup, ctx) -> list[LeverView]:
    """A named NPC's regard for the viewer, named when it eased or hardened the grade.

    Only the viewer sees it (the payload is theirs alone), and only its direction: the
    regard value itself stays with the GM.
    """
    if ctx is None or ctx.regard_bands == 0:
        return []
    direction = "easier" if ctx.regard_bands < 0 else "harder"
    return [LeverView(f"{group.name}'s regard for you: {direction}", is_angle=False)]


def _approach_caption(approach: StandoffApproach) -> str:
    """The check, plus the modifier that adds sway to it, if any."""
    if approach.sway_target is None:
        return approach.check_type.name
    return f"{approach.check_type.name} + {approach.sway_target.name}"


def _angles(facts: _GroupFacts, viewer: CharacterSheet) -> tuple[list[AngleView], list[AngleView]]:
    group_id = facts.group.pk
    mine_shared = {s.faction_rule_id for s in facts.shares if s.character_sheet_id == viewer.pk}
    own = [
        AngleView(group_id, m.rule.pk, m.rule.angle_text, m.rule.pk in mine_shared)
        for m in facts.matches
    ]
    own_ids = {s.faction_rule_id for s in own}
    seen: set[int] = set()
    others: list[AngleView] = []
    for share in facts.shares:
        rule = share.faction_rule
        if share.character_sheet_id == viewer.pk or rule.pk in own_ids or rule.pk in seen:
            continue
        seen.add(rule.pk)
        others.append(AngleView(group_id, rule.pk, rule.angle_text, True))
    return own, others


def _worst_morale_state(members: list) -> str:
    """The worst morale state among the group's active members (break, then falter)."""
    states = {morale_state_for(member) for member in members}
    for worst in (OpponentMoraleState.BREAK, OpponentMoraleState.FALTER):
        if worst in states:
            return worst
    return OpponentMoraleState.STEADY


def _display_techniques(viewer: CharacterSheet) -> list[Technique]:
    """The viewer's castable techniques: known ones plus a readied ultimate, performable."""
    from world.magic.models import CharacterTechnique  # noqa: PLC0415
    from world.magic.services.capability_requirements import (  # noqa: PLC0415
        performable_techniques,
    )
    from world.magic.services.ultimates import readied_ultimate  # noqa: PLC0415

    techniques = {
        link.technique_id: link.technique
        for link in CharacterTechnique.objects.filter(character=viewer).select_related(
            "technique__gift"
        )
    }
    readied = readied_ultimate(viewer)
    if readied is not None:
        techniques.setdefault(readied.technique.pk, readied.technique)
    return performable_techniques(viewer, list(techniques.values()))


def build_standoff_view(
    encounter: CombatEncounter, viewer_sheet: CharacterSheet
) -> StandoffView | None:
    """The standoff as ``viewer_sheet`` may see it; None when there is no standoff.

    A casting approach carries one grade per display technique, each graded with that
    technique's skill term, the same term its press rolls with.

    Everything a group needs is read once per (group, viewer) and shared by every
    approach and terms entry, so the query count follows the number of groups, not the
    number of approaches or terms.
    """
    if not is_in_standoff(encounter):
        return None
    config = StandoffConfig.load()
    participants = list(encounter.participants.filter(status=ParticipantStatus.ACTIVE))
    approaches = list(StandoffApproach.objects.select_related("check_type", "sway_target"))
    all_terms = list(StandoffTerms.objects.all())
    capability_ids = [a.capability_id for a in approaches]
    grader = _Grader(viewer_sheet)
    # Only a casting approach (a display of power) offers the technique picker.
    techniques = (
        _display_techniques(viewer_sheet)
        if any(approach.casts_technique for approach in approaches)
        else []
    )
    # The viewer's Path is read once; each technique's skill term follows from it.
    path = current_path_for_character(viewer_sheet.character) if techniques else None
    display_terms = {
        technique.pk: display_cast_terms_for_path(technique, path) for technique in techniques
    }
    view = StandoffView(
        place=encounter.room.db_key if encounter.room is not None else "",
        display_techniques=[DisplayTechniqueView(t.pk, t.name) for t in techniques],
    )
    for group in encounter.standoff_groups.select_related("creature_template", "persona"):
        _append_group_views(
            view,
            group,
            viewer_sheet,
            participants,
            capability_ids,
            approaches,
            all_terms,
            config,
            grader,
            display_terms,
        )
    return view


def _append_group_views(  # noqa: PLR0913 - inputs are the per-view and per-group processing context
    view: StandoffView,
    group: StandoffGroup,
    viewer: CharacterSheet,
    participants: list,
    capability_ids: list[int],
    approaches: list[StandoffApproach],
    all_terms: list[StandoffTerms],
    config: StandoffConfig,
    grader: _Grader,
    display_terms: dict[int, tuple[ExtraTraitTerm, ...]],
) -> None:
    """Add one group's summary, approaches, and terms to the viewer's view."""
    reveals = list(group.reveals.select_related("drive", "faction_rule"))
    shares = list(group.angle_shares.select_related("faction_rule"))
    matches = faction_rule_matches(group, viewer)
    facts = _GroupFacts(group, reveals, matches, shares, group_drives(group))
    members = active_members(group)
    hidden = hidden_things(
        group, participants, revealed=facts.revealed_set, known_matches={viewer.pk: matches}
    )
    is_open = group.state in LIVE_GROUP_STATES and bool(members)
    ctx = (
        build_grading_context(group, viewer, members=members, matches=matches) if is_open else None
    )
    read = _read_grade(config, ctx, grader)
    view.groups.append(
        _group_view(
            facts,
            viewer,
            len(members),
            len(hidden),
            read=read,
            morale_state=_worst_morale_state(members),
            terms_morale_ease=morale_terms_ease(members, config),
        )
    )
    own, others = _angles(facts, viewer)
    view.angles.extend(own)
    view.shared_angles.extend(others)
    if ctx is None:
        return
    targeted = targeted_properties_by_capability(
        capability_ids, [drive.property_id for drive in ctx.drives]
    )
    languages = group_languages(group)
    spoken = _Spoken(
        verbal=language_refusal(group, viewer, verbal=True, languages=languages),
        terms=language_refusal(group, viewer, verbal=False, languages=languages),
        regard=regard_lever(group, ctx),
    )
    _append_approaches(
        view, facts, group, viewer, ctx, approaches, targeted, grader, spoken, display_terms
    )
    _append_terms(view, facts, group, viewer, ctx, all_terms, config, grader, spoken)


@dataclass(frozen=True)
class _Spoken:
    """One group's language refusals for the viewer and its named NPC's regard lever."""

    verbal: str
    terms: str
    regard: list[LeverView]


def _read_grade(config: StandoffConfig, ctx, grader: _Grader) -> tuple[str, str]:
    """Return the configured read check and its grade when a group can be read."""
    check_type = config.read_check_type
    if check_type is None:
        return "", ""
    if ctx is None:
        return check_type.name, ""
    difficulty = level_opposition(check_type, level=ctx.level, character=ctx.first.objectdb)
    return check_type.name, grader.grade(check_type, difficulty, [])


def _append_approaches(  # noqa: PLR0913 - one approach-list build context
    view: StandoffView,
    facts: _GroupFacts,
    group: StandoffGroup,
    viewer: CharacterSheet,
    ctx,
    approaches: list[StandoffApproach],
    targeted_by_capability: dict,
    grader: _Grader,
    spoken: _Spoken,
    display_terms: dict[int, tuple[ExtraTraitTerm, ...]],
) -> None:
    """Add all available approach grades for one group.

    A casting approach also gets a grade per display technique, graded with that technique's
    skill terms (``display_terms``, by technique id): the terms its display cast rolls with.

    A verbal approach the language gate refuses is still listed and graded, with the
    reason, so the player sees why it is closed to them (#4373).
    """
    for approach in approaches:
        graded, hits, targeted = press_grade(group, viewer, approach, ctx, targeted_by_capability)
        grade = grader.grade(approach.check_type, graded.difficulty, graded.contributions)
        technique_grades = (
            [
                _technique_grade(approach, graded, grader, technique_id, terms)
                for technique_id, terms in display_terms.items()
            ]
            if approach.casts_technique
            else []
        )
        levers, hits_drive = _levers(facts, hits, targeted)
        levers.extend(spoken.regard)
        view.approaches.append(
            ApproachView(
                approach_id=approach.pk,
                group_id=group.pk,
                name=approach.name,
                grade=grade,
                grade_label=grade_label(grade),
                check_caption=_approach_caption(approach),
                levers=levers,
                hits_revealed_drive=hits_drive,
                casts_technique=approach.casts_technique,
                refusal=spoken.verbal if approach.is_verbal else "",
                technique_grades=technique_grades,
            )
        )


def _technique_grade(
    approach: StandoffApproach,
    graded: SocialDifficulty,
    grader: _Grader,
    technique_id: int,
    terms: Sequence[ExtraTraitTerm],
) -> TechniqueGradeView:
    """The approach's grade when pressed with the technique whose skill terms are ``terms``."""
    grade = grader.grade(approach.check_type, graded.difficulty, graded.contributions, terms)
    return TechniqueGradeView(technique_id, grade, grade_label(grade))


def _append_terms(  # noqa: PLR0913 - one terms-list build context
    view: StandoffView,
    facts: _GroupFacts,
    group: StandoffGroup,
    viewer: CharacterSheet,
    ctx,
    all_terms: list[StandoffTerms],
    config: StandoffConfig,
    grader: _Grader,
    spoken: _Spoken,
) -> None:
    """Add visible terms grades for one group (a refused one keeps its grade and reason)."""
    check_type = config.terms_check_type
    if check_type is None:
        return
    revealed_props = facts.revealed_drive_property_ids
    for terms in all_terms:
        if terms.required_drive_id is not None and terms.required_drive_id not in revealed_props:
            continue
        graded = terms_difficulty(group, viewer, terms, ctx, config)
        grade = grader.grade(check_type, graded.difficulty, graded.contributions)
        view.terms.append(
            TermsView(
                terms_id=terms.pk,
                name=terms.name,
                group_id=group.pk,
                description=terms.description,
                grade=grade,
                grade_label=grade_label(grade),
                critical_label=terms.get_critical_effect_display(),
                levers=list(spoken.regard),
                refusal=spoken.terms,
            )
        )
