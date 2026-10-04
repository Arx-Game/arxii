"""What one participant may see of a standoff.

Privacy is the point of this module. Everything is built for a single viewer: their own
sparks, regard detail only where it applies to them or was shared, and unread causes,
drives and rules only as a count. A hidden drive still shapes every grade (it is the real
roll math) but is never named.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.checks.services import collect_check_modifiers, preview_check_difficulty
from world.combat.constants import CauseKind, ParticipantStatus
from world.mechanics.services import difficulty_indicator_for_rank_difference
from world.standoffs.constants import DriveStrength, RevealKind, StandoffGroupState
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
from world.standoffs.services.verbs import hidden_things, press_grade, terms_difficulty

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
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
    hidden_count: int
    drives: list[DriveView]
    revealed_regard: list[str]


@dataclass(frozen=True)
class ApproachView:
    approach_id: int
    group_id: int
    name: str
    grade: str
    levers: list[str]


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
    grade: str


@dataclass(frozen=True)
class StandoffView:
    groups: list[GroupView] = field(default_factory=list)
    approaches: list[ApproachView] = field(default_factory=list)
    terms: list[TermsView] = field(default_factory=list)
    sparks: list[SparkView] = field(default_factory=list)
    shared_sparks: list[SparkView] = field(default_factory=list)
    # Reserved for mission owner-only options; always empty in this slice.
    owner_options: list[str] = field(default_factory=list)


def _grade(sheet: CharacterSheet, check_type, difficulty: int, contributions: list) -> str:
    """The roll's own modifier total feeds the preview, so the shown grade matches the roll."""
    extra = collect_check_modifiers(sheet, check_type, extra_contributions=contributions).total
    rank = preview_check_difficulty(sheet.character, check_type, difficulty, extra)
    return difficulty_indicator_for_rank_difference(rank).value


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
    def revealed_rule_ids(self) -> set[int]:
        return {
            r.regard_rule_id
            for r in self.reveals
            if r.kind == RevealKind.REGARD and r.regard_rule_id is not None
        }


def _group_view(
    facts: _GroupFacts, viewer: CharacterSheet, member_count: int, hidden_count: int
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
        hidden_count=hidden_count,
        drives=drives,
        revealed_regard=describe_reveals(group, regard, viewer),
    )


def _levers(facts: _GroupFacts, hits: list, targeted: set[int]) -> list[str]:
    """Revealed drives the approach hits and revealed regard the viewer may see."""
    revealed_props = facts.revealed_drive_property_ids
    levers = [hit.label for drive, hit in hits if drive.property_id in revealed_props]
    revealed_rules = facts.revealed_rule_ids
    shared_rules = {s.regard_rule_id for s in facts.shares}
    for match in facts.matches:
        rule = match.rule
        shifts = rule.difficulty_shift_bands != 0 or (
            rule.drive_shift != 0 and rule.drive_id in targeted
        )
        if (shifts and rule.pk in revealed_rules and rule.revealed_text) or (
            shifts and rule.pk in shared_rules and rule.revealed_text
        ):
            levers.append(rule.revealed_text)
    return levers


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
    """The standoff as ``viewer_sheet`` may see it; None when there is no standoff."""
    if not is_in_standoff(encounter):
        return None
    config = StandoffConfig.load()
    participants = list(encounter.participants.filter(status=ParticipantStatus.ACTIVE))
    approaches = list(StandoffApproach.objects.select_related("check_type"))
    all_terms = list(StandoffTerms.objects.all())
    view = StandoffView()
    for group in encounter.standoff_groups.select_related("creature_template"):
        reveals = list(group.reveals.select_related("drive__property", "regard_rule"))
        shares = list(group.spark_shares.select_related("regard_rule"))
        facts = _GroupFacts(group, reveals, regard_matches(group, viewer_sheet), shares)
        members = active_members(group)
        view.groups.append(
            _group_view(facts, viewer_sheet, len(members), len(hidden_things(group, participants)))
        )
        own, others = _sparks(facts, viewer_sheet)
        view.sparks.extend(own)
        view.shared_sparks.extend(others)
        if group.state != StandoffGroupState.OPEN or not members:
            continue
        for approach in approaches:
            graded, hits, targeted = press_grade(group, viewer_sheet, approach)
            view.approaches.append(
                ApproachView(
                    approach_id=approach.pk,
                    group_id=group.pk,
                    name=approach.name,
                    grade=_grade(
                        viewer_sheet,
                        approach.check_type,
                        graded.difficulty,
                        graded.contributions,
                    ),
                    levers=_levers(facts, hits, targeted),
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
            graded = terms_difficulty(group, viewer_sheet, terms)
            view.terms.append(
                TermsView(
                    terms_id=terms.pk,
                    name=terms.name,
                    group_id=group.pk,
                    grade=_grade(
                        viewer_sheet,
                        config.terms_check_type,
                        graded.difficulty,
                        graded.contributions,
                    ),
                )
            )
    return view
