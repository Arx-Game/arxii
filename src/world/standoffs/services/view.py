"""What one participant may see of a standoff.

Privacy is the point of this module. Everything is built for a single viewer: their own
sparks, regard detail only where it applies to them or was shared, and unread causes,
drives and rules only as a count. A hidden drive still shapes every grade (it is the real
roll math) but is never named.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.checks.services import (
    collect_check_modifiers,
    level_opposition,
    preview_check_difficulty,
)
from world.combat.constants import CauseKind, ParticipantStatus
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.services import difficulty_indicator_for_rank_difference
from world.standoffs.constants import (
    CAUSE_GLOSSES,
    DriveStrength,
    RevealKind,
    StandoffGroupState,
)
from world.standoffs.models import (
    StandoffApproach,
    StandoffConfig,
    StandoffGroup,
    StandoffReveal,
    StandoffSparkShare,
    StandoffTerms,
)
from world.standoffs.services.describe import describe_reveals
from world.standoffs.services.regard import MatchedRegard, regard_matches
from world.standoffs.services.state import active_members, is_in_standoff
from world.standoffs.services.verbs import (
    build_grading_context,
    hidden_things,
    press_grade,
    targeted_properties_by_capability,
    terms_difficulty,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import ModifierContribution
    from world.combat.models import CombatEncounter


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
    revealed_regard: list[str]
    read_check: str
    read_grade: str
    read_grade_label: str


@dataclass(frozen=True)
class LeverView:
    """One line saying why an approach may work; ``is_spark`` marks the viewer's own spark."""

    text: str
    is_spark: bool


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


@dataclass(frozen=True)
class SparkView:
    group_id: int
    regard_rule_id: int
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


@dataclass(frozen=True)
class StandoffView:
    place: str = ""
    groups: list[GroupView] = field(default_factory=list)
    approaches: list[ApproachView] = field(default_factory=list)
    terms: list[TermsView] = field(default_factory=list)
    sparks: list[SparkView] = field(default_factory=list)
    shared_sparks: list[SparkView] = field(default_factory=list)


def grade_label(grade: str) -> str:
    """The human label of a ``DifficultyIndicator`` value (``very_hard`` -> "Very Hard")."""
    return DifficultyIndicator(grade).label if grade else ""


@dataclass
class _Grader:
    """Grades one viewer's checks for one build; its dicts live and die with that build.

    The roll's own modifier total feeds the preview, so the shown grade matches the roll.
    ``base_totals`` holds the viewer's gathered modifiers per check type and ``graded``
    the finished grade per (check type, difficulty, modifiers). The roll adds the social
    contributions on top of the gathered total as a plain sum.
    """

    sheet: CharacterSheet
    base_totals: dict[int, int] = field(default_factory=dict)
    graded: dict[tuple[int, int, int], str] = field(default_factory=dict)

    def grade(
        self,
        check_type: CheckType,
        difficulty: int,
        contributions: list[ModifierContribution],
    ) -> str:
        if check_type.pk not in self.base_totals:
            self.base_totals[check_type.pk] = collect_check_modifiers(self.sheet, check_type).total
        extra = self.base_totals[check_type.pk] + sum(c.value for c in contributions)
        key = (check_type.pk, difficulty, extra)
        if key not in self.graded:
            rank = preview_check_difficulty(self.sheet.character, check_type, difficulty, extra)
            self.graded[key] = difficulty_indicator_for_rank_difference(rank).value
        return self.graded[key]


@dataclass(frozen=True)
class _GroupFacts:
    """One group's reveals and the viewer's matched rules, read once."""

    group: StandoffGroup
    reveals: list[StandoffReveal]
    matches: list[MatchedRegard]
    shares: list[StandoffSparkShare]

    @property
    def revealed_drive_property_ids(self) -> set[int]:
        return {
            r.drive.property_id
            for r in self.reveals
            if r.kind == RevealKind.DRIVE and r.drive is not None
        }

    @property
    def revealed_set(self) -> set[tuple[str, int | None, int | None]]:
        return {(r.kind, r.drive_id, r.regard_rule_id) for r in self.reveals}

    @property
    def shared_rule_ids(self) -> set[int]:
        return {s.regard_rule_id for s in self.shares}

    @property
    def revealed_rule_ids(self) -> set[int]:
        return {
            r.regard_rule_id
            for r in self.reveals
            if r.kind == RevealKind.REGARD and r.regard_rule_id is not None
        }


def _group_view(
    facts: _GroupFacts,
    viewer: CharacterSheet,
    member_count: int,
    hidden_count: int,
    read: tuple[str, str] = ("", ""),
) -> GroupView:
    group = facts.group
    template = group.creature_template
    cause_known = template.cause != CauseKind.NONE and any(
        r.kind == RevealKind.CAUSE for r in facts.reveals
    )
    drives = [
        DriveView(r.drive.property.name, DriveStrength(r.drive.strength).label)
        for r in facts.reveals
        if r.kind == RevealKind.DRIVE and r.drive is not None
    ]
    regard = [r for r in facts.reveals if r.kind == RevealKind.REGARD]
    return GroupView(
        group_id=group.pk,
        name=template.name,
        member_count=member_count,
        state=group.state,
        terms_ease=group.terms_ease,
        cause=CauseKind(template.cause).label if cause_known else None,
        cause_gloss=CAUSE_GLOSSES.get(template.cause) if cause_known else None,
        hidden_count=hidden_count,
        drives=drives,
        revealed_regard=describe_reveals(
            group,
            regard,
            viewer,
            matching_rule_ids={m.rule.pk for m in facts.matches},
            shared_rule_ids=facts.shared_rule_ids,
        ),
        read_check=read[0],
        read_grade=read[1],
        read_grade_label=grade_label(read[1]),
    )


def _levers(facts: _GroupFacts, hits: list, targeted: set[int]) -> tuple[list[LeverView], bool]:
    """Revealed drives the approach hits, and regard text only once that rule was read.

    Returns the lever lines and whether any is a revealed drive hit. Drives read
    "hits <Drive> (<Strength>)"; a regard lever is always the viewer's own spark
    (``facts.matches`` are their rules), so it reads "your spark: <revealed text>".

    A shared spark is not a read: auto-sharing after a press must not expose detail the
    group never revealed, and describe_reveals (telnet) gates on the reveal too.
    """
    revealed_props = facts.revealed_drive_property_ids
    hit_levers = [
        LeverView(f"hits {hit.label} ({DriveStrength(drive.strength).label})", is_spark=False)
        for drive, hit in hits
        if drive.property_id in revealed_props
    ]
    levers = list(hit_levers)
    revealed_rules = facts.revealed_rule_ids
    for match in facts.matches:
        rule = match.rule
        shifts = rule.difficulty_shift_bands != 0 or (
            rule.drive_shift != 0 and rule.drive_id in targeted
        )
        if shifts and rule.pk in revealed_rules and rule.revealed_text:
            levers.append(LeverView(f"your spark: {rule.revealed_text}", is_spark=True))
    return levers, bool(hit_levers)


def _approach_caption(approach: StandoffApproach) -> str:
    """The check, plus the modifier that adds sway to it, if any."""
    if approach.sway_target is None:
        return approach.check_type.name
    return f"{approach.check_type.name} + {approach.sway_target.name}"


def _sparks(facts: _GroupFacts, viewer: CharacterSheet) -> tuple[list[SparkView], list[SparkView]]:
    group_id = facts.group.pk
    mine_shared = {s.regard_rule_id for s in facts.shares if s.character_sheet_id == viewer.pk}
    own = [
        SparkView(group_id, m.rule.pk, m.rule.spark_text, m.rule.pk in mine_shared)
        for m in facts.matches
    ]
    own_ids = {s.regard_rule_id for s in own}
    seen: set[int] = set()
    others: list[SparkView] = []
    for share in facts.shares:
        rule = share.regard_rule
        if share.character_sheet_id == viewer.pk or rule.pk in own_ids or rule.pk in seen:
            continue
        seen.add(rule.pk)
        others.append(SparkView(group_id, rule.pk, rule.spark_text, True))
    return own, others


def build_standoff_view(
    encounter: CombatEncounter, viewer_sheet: CharacterSheet
) -> StandoffView | None:
    """The standoff as ``viewer_sheet`` may see it; None when there is no standoff.

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
    view = StandoffView(place=encounter.room.db_key if encounter.room is not None else "")
    for group in encounter.standoff_groups.select_related("creature_template"):
        reveals = list(group.reveals.select_related("drive__property", "regard_rule"))
        shares = list(group.spark_shares.select_related("regard_rule"))
        matches = regard_matches(group, viewer_sheet)
        facts = _GroupFacts(group, reveals, matches, shares)
        members = active_members(group)
        hidden = hidden_things(
            group,
            participants,
            revealed=facts.revealed_set,
            known_matches={viewer_sheet.pk: matches},
        )
        is_open = group.state == StandoffGroupState.OPEN and bool(members)
        ctx = (
            build_grading_context(group, viewer_sheet, members=members, matches=matches)
            if is_open
            else None
        )
        read = ("", "")
        if config.read_check_type is not None:
            read = (config.read_check_type.name, "")
            if ctx is not None:
                difficulty = level_opposition(
                    config.read_check_type, level=ctx.level, character=ctx.first.objectdb
                )
                read = (read[0], grader.grade(config.read_check_type, difficulty, []))
        view.groups.append(
            _group_view(
                facts,
                viewer_sheet,
                len(members),
                len(hidden),
                read=read,
            )
        )
        own, others = _sparks(facts, viewer_sheet)
        view.sparks.extend(own)
        view.shared_sparks.extend(others)
        if ctx is None:
            continue
        targeted_by_capability = targeted_properties_by_capability(
            capability_ids, [drive.property_id for drive in ctx.drives]
        )
        for approach in approaches:
            graded, hits, targeted = press_grade(
                group, viewer_sheet, approach, ctx, targeted_by_capability
            )
            grade = grader.grade(approach.check_type, graded.difficulty, graded.contributions)
            levers, hits_drive = _levers(facts, hits, targeted)
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
                )
            )
        if config.terms_check_type is None:
            continue
        revealed_props = facts.revealed_drive_property_ids
        for terms in all_terms:
            if (
                terms.required_drive_id is not None
                and terms.required_drive_id not in revealed_props
            ):
                continue
            graded = terms_difficulty(group, viewer_sheet, terms, ctx, config)
            grade = grader.grade(config.terms_check_type, graded.difficulty, graded.contributions)
            view.terms.append(
                TermsView(
                    terms_id=terms.pk,
                    name=terms.name,
                    group_id=group.pk,
                    description=terms.description,
                    grade=grade,
                    grade_label=grade_label(grade),
                )
            )
    return view
