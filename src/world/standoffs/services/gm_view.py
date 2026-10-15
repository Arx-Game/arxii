"""The GM's view of a standoff, and the public summary an onlooker sees (#4354).

``build_gm_standoff_view`` is everything a GM needs to run the standoff without computing
anything by hand: each group's whole profile (cause and whether it holds now, drives with
strengths and whether the party has read them), the faction rules with which participants
match them, force on both sides, every member's morale and any pending proposal. It is
served to the scene's GMs (and staff) only.

``build_standoff_summary`` is built from public facts only (group names, counts, morale,
emboldened, settled or fighting) for anyone else in the scene. It never carries a cause, a
drive, a faction rule or an angle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.combat.constants import CauseKind, ParticipantStatus
from world.combat.morale import OpponentMoraleState, morale_state_for, tier_has_morale
from world.predicates.predicates import KEY_LEAF, KEY_OF, KEY_OP, KEY_PARAMS, OP_NOT, OP_OR
from world.standoffs.constants import (
    LIVE_GROUP_STATES,
    DriveStrength,
    RevealKind,
    StandoffGroupState,
)
from world.standoffs.models import StandoffConfig
from world.standoffs.services.faction_rules import faction_rule_matches
from world.standoffs.services.force import (
    cause_fire_reason,
    effective_party_force,
    group_force,
    party_force,
)
from world.standoffs.services.proposals import last_decision, pending_prompts
from world.standoffs.services.state import active_members, is_in_standoff

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter
    from world.standoffs.models import FactionRule, StandoffGroup

_EVERYONE = "matches everyone"


@dataclass(frozen=True)
class GMDriveView:
    label: str
    strength: str
    revealed: bool


@dataclass(frozen=True)
class GMFactionRuleView:
    faction_rule_id: int
    label: str
    angle_text: str
    difficulty_shift_bands: int
    suppresses_cause: bool
    matched_by: list[str]
    revealed: bool


@dataclass(frozen=True)
class GMMemberView:
    opponent_id: int
    name: str
    morale: int
    morale_state: str


@dataclass(frozen=True)
class GMGroupView:
    group_id: int
    name: str
    state: str
    member_count: int
    cause: str
    cause_revealed: bool
    cause_fires: bool
    cause_reason: str
    cause_margin_percent: int
    proposal_reason: str
    pending_prompt_id: int | None
    last_decision: str
    override_standing: bool
    emboldened_bands: int
    terms_ease: int
    has_morale: bool
    morale_state: str
    party_force: float
    effective_party_force: float
    group_force: float
    drives: list[GMDriveView] = field(default_factory=list)
    faction_rules: list[GMFactionRuleView] = field(default_factory=list)
    members: list[GMMemberView] = field(default_factory=list)


@dataclass(frozen=True)
class GMStandoffView:
    place: str
    participants: list[str]
    groups: list[GMGroupView]


@dataclass(frozen=True)
class SummaryGroupView:
    group_id: int
    name: str
    member_count: int
    state: str
    morale_state: str
    emboldened: bool


@dataclass(frozen=True)
class StandoffSummary:
    place: str
    participants: list[str]
    groups: list[SummaryGroupView]


def _node_label(node: dict) -> str:
    """A predicate tree as a short "leaf: value" text, for the GM's eyes only."""
    if not node:
        return ""
    if KEY_OP in node:
        parts = [_node_label(child) for child in node.get(KEY_OF, [])]
        parts = [part for part in parts if part]
        if node[KEY_OP] == OP_NOT:
            return f"not ({parts[0]})" if parts else ""
        joiner = " or " if node[KEY_OP] == OP_OR else " and "
        return joiner.join(parts)
    values = [str(value) for value in (node.get(KEY_PARAMS) or {}).values()]
    return f"{node[KEY_LEAF]}: {', '.join(values)}" if values else str(node[KEY_LEAF])


def faction_rule_label(rule: FactionRule) -> str:
    """A short staff-facing label for what a faction rule tests."""
    parts = [_node_label(rule.rule or {})]
    if rule.deed_archetype_id is not None:
        parts.append(f"known for {rule.deed_archetype.name} deeds")
    parts = [part for part in parts if part]
    return "; ".join(parts) if parts else _EVERYONE


def _worst_state(members: list) -> str:
    states = {morale_state_for(member) for member in members}
    for worst in (OpponentMoraleState.BREAK, OpponentMoraleState.FALTER):
        if worst in states:
            return worst
    return OpponentMoraleState.STEADY


def _active_participants(encounter: CombatEncounter) -> list:
    return list(
        encounter.participants.filter(status=ParticipantStatus.ACTIVE).select_related(
            "character_sheet"
        )
    )


def _presented_name(sheet) -> str:
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    return active_persona_for_sheet(sheet).name


def _gm_group(group: StandoffGroup, participants: list, config: StandoffConfig) -> GMGroupView:
    template = group.creature_template
    members = active_members(group)
    reveals = list(group.reveals.all())
    revealed_drive_ids = {r.drive_id for r in reveals if r.kind == RevealKind.DRIVE}
    revealed_rule_ids = {r.faction_rule_id for r in reveals if r.kind == RevealKind.FACTION_RULE}
    rules = list(template.faction_rules.select_related("deed_archetype").order_by("pk"))
    matched: dict[int, list[str]] = {rule.pk: [] for rule in rules}
    for participant in participants:
        sheet = participant.character_sheet
        for match in faction_rule_matches(group, sheet, rules):
            matched[match.rule.pk].append(_presented_name(sheet))
    live = group.state in LIVE_GROUP_STATES and bool(members)
    reason = cause_fire_reason(group, config, lapse_override=False) if live else None
    prompts = pending_prompts(group) if group.state == StandoffGroupState.PROPOSED else []
    return GMGroupView(
        group_id=group.pk,
        name=template.name,
        state=group.state,
        member_count=len(members),
        cause=CauseKind(template.cause).label,
        cause_revealed=any(r.kind == RevealKind.CAUSE for r in reveals),
        cause_fires=reason is not None,
        cause_reason=reason or "",
        cause_margin_percent=template.cause_margin_percent,
        proposal_reason=group.proposal_reason if prompts else "",
        pending_prompt_id=prompts[0].pk if prompts else None,
        last_decision=last_decision(group),
        override_standing=group.override_party_force is not None,
        emboldened_bands=group.emboldened_bands,
        terms_ease=group.terms_ease,
        has_morale=any(tier_has_morale(member) for member in members),
        morale_state=_worst_state(members),
        party_force=round(party_force(group.encounter, config), 1),
        effective_party_force=round(effective_party_force(group.encounter, group, config), 1),
        group_force=round(group_force(group, config), 1),
        drives=[
            GMDriveView(
                label=drive.property.name,
                strength=DriveStrength(drive.strength).label,
                revealed=drive.pk in revealed_drive_ids,
            )
            for drive in template.drives.select_related("property")
        ],
        faction_rules=[
            GMFactionRuleView(
                faction_rule_id=rule.pk,
                label=faction_rule_label(rule),
                angle_text=rule.angle_text,
                difficulty_shift_bands=rule.difficulty_shift_bands,
                suppresses_cause=rule.suppresses_cause,
                matched_by=matched[rule.pk],
                revealed=rule.pk in revealed_rule_ids,
            )
            for rule in rules
        ],
        members=[
            GMMemberView(
                opponent_id=member.pk,
                name=member.name,
                morale=member.morale,
                morale_state=morale_state_for(member),
            )
            for member in members
        ],
    )


def _place(encounter: CombatEncounter) -> str:
    return encounter.room.db_key if encounter.room is not None else ""


def build_gm_standoff_view(encounter: CombatEncounter) -> GMStandoffView | None:
    """The whole standoff for a GM; None when the encounter is not in its standoff."""
    if not is_in_standoff(encounter):
        return None
    config = StandoffConfig.load()
    participants = _active_participants(encounter)
    return GMStandoffView(
        place=_place(encounter),
        participants=[_presented_name(p.character_sheet) for p in participants],
        groups=[
            _gm_group(group, participants, config)
            for group in encounter.standoff_groups.select_related("creature_template")
        ],
    )


def build_standoff_summary(encounter: CombatEncounter) -> StandoffSummary | None:
    """Public facts only, for an onlooker; None when the encounter is not in its standoff.

    A PROPOSED group shows as open: a pending GM decision is not public.
    """
    if not is_in_standoff(encounter):
        return None
    groups = []
    for group in encounter.standoff_groups.select_related("creature_template"):
        members = active_members(group)
        state = group.state
        if state == StandoffGroupState.PROPOSED:
            state = StandoffGroupState.OPEN
        groups.append(
            SummaryGroupView(
                group_id=group.pk,
                name=group.creature_template.name,
                member_count=len(members),
                state=state,
                morale_state=_worst_state(members),
                emboldened=group.emboldened_bands > 0,
            )
        )
    return StandoffSummary(
        place=_place(encounter),
        participants=[_presented_name(p.character_sheet) for p in _active_participants(encounter)],
        groups=groups,
    )
