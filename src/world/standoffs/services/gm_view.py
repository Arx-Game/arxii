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
    RevealKind,
    StandoffGroupState,
)
from world.standoffs.models import StandoffConfig
from world.standoffs.services.faction_rules import faction_rule_matches
from world.standoffs.services.force import (
    cause_clock,
    cause_fire_reason,
    effective_party_force,
    group_force,
    party_force,
)
from world.standoffs.services.language import group_languages
from world.standoffs.services.profile import (
    group_cause,
    group_drives,
    group_organization,
    group_rules,
)
from world.standoffs.services.proposals import last_decision, pending_prompts
from world.standoffs.services.state import active_members, is_in_standoff
from world.standoffs.services.verbs import regard_for

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter
    from world.standoffs.models import FactionRule, StandoffGroup

_EVERYONE = "matches everyone"
# How the GM view words a named NPC's regard for a participant (#4373).
REGARD_POSITIVE = "positive"
REGARD_NEGATIVE = "negative"
REGARD_NEUTRAL = "neutral"


@dataclass(frozen=True)
class GMDriveView:
    label: str
    strength: str
    revealed: bool
    edited: bool = False


@dataclass(frozen=True)
class GMFactionRuleView:
    faction_rule_id: int
    label: str
    angle_text: str
    difficulty_shift_bands: int
    cause_effect: str
    matched_by: list[str]
    revealed: bool
    source: str = ""


@dataclass(frozen=True)
class GMMemberView:
    opponent_id: int
    name: str
    morale: int
    morale_state: str


@dataclass(frozen=True)
class GMRegardView:
    """A named NPC's ``NpcRegard`` for one participant's presented persona (#4373)."""

    participant: str
    regard: int
    label: str
    bands: int


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
    cause_clock: str
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
    affiliation: str = ""
    cause_edited: bool = False
    affiliation_edited: bool = False
    drives: list[GMDriveView] = field(default_factory=list)
    faction_rules: list[GMFactionRuleView] = field(default_factory=list)
    members: list[GMMemberView] = field(default_factory=list)
    is_named_npc: bool = False
    speaks: list[str] = field(default_factory=list)
    regards: list[GMRegardView] = field(default_factory=list)


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


def _regard_label(regard: int) -> str:
    if regard > 0:
        return REGARD_POSITIVE
    if regard < 0:
        return REGARD_NEGATIVE
    return REGARD_NEUTRAL


def _regards(group: StandoffGroup, participants: list, config: StandoffConfig) -> list:
    """The named NPC's regard for each participant who has one, as the GM reads it.

    A participant the NPC holds no opinion of is left out, as the demo's "Their regard" row
    lists only the characters it matters for; a template group has none.
    """
    if group.persona_id is None:
        return []
    views = []
    for participant in participants:
        regard, bands = regard_for(group, participant.character_sheet, config)
        if regard == 0:
            continue
        views.append(
            GMRegardView(
                participant=_presented_name(participant.character_sheet),
                regard=regard,
                label=_regard_label(regard),
                bands=bands,
            )
        )
    return views


def _gm_group(group: StandoffGroup, participants: list, config: StandoffConfig) -> GMGroupView:
    template = group.creature_template
    members = active_members(group)
    reveals = list(group.reveals.all())
    revealed_drive_ids = {r.drive_id for r in reveals if r.kind == RevealKind.DRIVE}
    revealed_rule_ids = {r.faction_rule_id for r in reveals if r.kind == RevealKind.FACTION_RULE}
    rules = group_rules(group)
    matched: dict[int, list[str]] = {entry.rule.pk: [] for entry in rules}
    for participant in participants:
        sheet = participant.character_sheet
        for match in faction_rule_matches(group, sheet, rules):
            matched[match.rule.pk].append(_presented_name(sheet))
    cause, margin = group_cause(group)
    organization = group_organization(group)
    # A named NPC's drives are its persona's own (ADR-4373-A): nothing there is "edited".
    compares_template = template is not None and group.persona_id is None
    template_strengths = (
        {drive.property_id: drive.strength for drive in template.drives.all()}
        if compares_template
        else {}
    )
    live = group.state in LIVE_GROUP_STATES and bool(members)
    reason = cause_fire_reason(group, config, lapse_override=False) if live else None
    prompts = pending_prompts(group) if group.state == StandoffGroupState.PROPOSED else []
    return GMGroupView(
        group_id=group.pk,
        name=group.name,
        state=group.state,
        member_count=len(members),
        cause=CauseKind(cause).label,
        cause_revealed=any(r.kind == RevealKind.CAUSE for r in reveals),
        cause_fires=reason is not None,
        cause_reason=reason or "",
        cause_margin_percent=margin,
        cause_clock=cause_clock(group, config) if live else "",
        affiliation=organization.name if organization is not None else "",
        cause_edited=template is not None and cause != template.cause,
        affiliation_edited=template is not None and organization != template.organization,
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
                strength=drive.strength_label,
                revealed=drive.property_id in revealed_drive_ids,
                edited=compares_template
                and template_strengths.get(drive.property_id) != drive.strength,
            )
            for drive in group_drives(group)
        ],
        faction_rules=[
            GMFactionRuleView(
                faction_rule_id=entry.rule.pk,
                label=faction_rule_label(entry.rule),
                angle_text=entry.rule.angle_text,
                difficulty_shift_bands=entry.rule.difficulty_shift_bands,
                cause_effect=entry.rule.cause_effect,
                matched_by=matched[entry.rule.pk],
                revealed=entry.rule.pk in revealed_rule_ids,
                source=entry.source,
            )
            for entry in rules
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
        is_named_npc=group.persona_id is not None,
        speaks=[language.name for language in group_languages(group)],
        regards=_regards(group, participants, config),
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
            for group in encounter.standoff_groups.select_related("creature_template", "persona")
        ],
    )


def build_standoff_summary(encounter: CombatEncounter) -> StandoffSummary | None:
    """Public facts only, for an onlooker; None when the encounter is not in its standoff.

    A PROPOSED group shows as open: a pending GM decision is not public.
    """
    if not is_in_standoff(encounter):
        return None
    groups = []
    for group in encounter.standoff_groups.select_related("creature_template", "persona"):
        members = active_members(group)
        state = group.state
        if state == StandoffGroupState.PROPOSED:
            state = StandoffGroupState.OPEN
        groups.append(
            SummaryGroupView(
                group_id=group.pk,
                name=group.name,
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
