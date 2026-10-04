"""Force comparison: whether a group's cause makes it open the fight."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.combat.constants import CauseKind, ParticipantStatus
from world.combat.models import OpponentTierTemplate
from world.combat.morale import OpponentMoraleState, morale_state_for
from world.covenants.mentorship import effective_combat_level
from world.standoffs.constants import StandoffGroupState
from world.standoffs.services.regard import suppressed_for_all_participants
from world.standoffs.services.state import (
    active_members,
    end_standoff_into_fight,
    settle_empty_groups,
)
from world.stories.services.stakes import LEVELS_PER_TIER

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant
    from world.standoffs.models import StandoffConfig, StandoffGroup

MIN_PARTY_FORCE_PERCENT = 25  # an under-levelled party never counts for less than this


def _health_fraction(health: int, max_health: int) -> float:
    """Current over maximum health, clamped to 0..1; no maximum counts as whole."""
    if max_health <= 0:
        return 1.0
    return max(0.0, min(1.0, health / max_health))


def _participant_health_fraction(participant: CombatParticipant) -> float:
    try:
        vitals = participant.character_sheet.vitals
    except ObjectDoesNotExist:
        # A character with no vitals row has no wounds recorded: counts as whole.
        return 1.0
    return _health_fraction(vitals.health, vitals.max_health)


def over_level_factor(encounter: CombatEncounter, config: StandoffConfig) -> float:
    """How the party's average level against the content's level band scales its force.

    A mission standoff has a band (``level_band_min``..``level_band_max``). Each
    ``LEVELS_PER_TIER`` levels the party average stands above the band's top adds
    ``config.over_level_percent_per_tier`` percent; each tier below its bottom takes the
    same off, never under a quarter of the base. A standoff with no mission has no band,
    so the factor is 1.0.
    """
    if encounter.scenario_deed_id is None:
        return 1.0
    band = encounter.scenario_deed.instance.template
    levels = [
        effective_combat_level(participant.character_sheet)
        for participant in encounter.participants.filter(
            status=ParticipantStatus.ACTIVE
        ).select_related("character_sheet")
    ]
    if not levels:
        return 1.0
    average = sum(levels) / len(levels)
    if average > band.level_band_max:
        tiers = int((average - band.level_band_max) // LEVELS_PER_TIER)
    elif average < band.level_band_min:
        tiers = -int((band.level_band_min - average) // LEVELS_PER_TIER)
    else:
        tiers = 0
    return max(MIN_PARTY_FORCE_PERCENT, 100 + config.over_level_percent_per_tier * tiers) / 100


def party_force(encounter: CombatEncounter, config: StandoffConfig) -> float:
    """Active participants' effective levels, each times current health, over-level scaled."""
    base = sum(
        effective_combat_level(participant.character_sheet)
        * _participant_health_fraction(participant)
        for participant in encounter.participants.filter(
            status=ParticipantStatus.ACTIVE
        ).select_related("character_sheet__vitals")
    )
    return base * over_level_factor(encounter, config)


def _morale_percent(
    member: CombatOpponent, templates: dict[str, OpponentTierTemplate], config: StandoffConfig
) -> int:
    """A faltering or broken member counts for less; a mindless tier is always steady."""
    if not templates[member.tier].has_morale:
        return 100
    state = morale_state_for(member)
    if state == OpponentMoraleState.BREAK:
        return config.break_force_percent
    if state == OpponentMoraleState.FALTER:
        return config.falter_force_percent
    return 100


def group_force(group: StandoffGroup, config: StandoffConfig) -> float:
    """Active members' level x tier weight x health x morale, summed."""
    templates = {tpl.tier: tpl for tpl in OpponentTierTemplate.objects.all()}
    return sum(
        member.level
        * templates[member.tier].force_weight_percent
        / 100
        * _health_fraction(member.health, member.max_health)
        * _morale_percent(member, templates, config)
        / 100
        for member in active_members(group)
    )


def effective_party_force(
    encounter: CombatEncounter, group: StandoffGroup, config: StandoffConfig
) -> float:
    """Party force, less what the group's emboldening has cost it."""
    penalty = config.band_force_percent * group.emboldened_bands
    return max(0.0, party_force(encounter, config) * (100 - penalty) / 100)


def cause_fires(group: StandoffGroup, config: StandoffConfig) -> bool:
    """Predation fires when the party does not outweigh the group by its margin."""
    if group.creature_template.cause != CauseKind.PREDATION:
        return False
    margin = 100 + group.creature_template.cause_margin_percent
    weak = effective_party_force(group.encounter, group, config) * 100 <= (
        group_force(group, config) * margin
    )
    return weak and not suppressed_for_all_participants(group)


def evaluate_causes(encounter: CombatEncounter) -> bool:
    """Settle empty groups; if an OPEN group's cause fires, the fight begins.

    Settling the last OPEN group (its members fled or were removed) leaves nothing to
    negotiate, so the standoff completes as a victory, as when the last terms are accepted.
    """
    from world.standoffs.models import StandoffConfig  # noqa: PLC0415

    if (
        settle_empty_groups(encounter)
        and not encounter.standoff_groups.exclude(state=StandoffGroupState.SETTLED).exists()
    ):
        from world.standoffs.services.routing import complete_standoff  # noqa: PLC0415

        complete_standoff(encounter)
        return False
    config = StandoffConfig.load()
    for group in encounter.standoff_groups.filter(state=StandoffGroupState.OPEN).select_related(
        "creature_template"
    ):
        if cause_fires(group, config):
            return end_standoff_into_fight(encounter, initiated_by_pc_side=False)
    return False
