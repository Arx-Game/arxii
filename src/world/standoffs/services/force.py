"""Force comparison: whether a group's cause makes it open the fight."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CauseKind, OpponentTier, ParticipantStatus
from world.covenants.mentorship import effective_combat_level
from world.standoffs.constants import StandoffGroupState
from world.standoffs.services.regard import suppressed_for_all_participants
from world.standoffs.services.state import (
    active_members,
    end_standoff_into_fight,
    settle_empty_groups,
)

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter
    from world.standoffs.models import StandoffConfig, StandoffGroup


def party_force(encounter: CombatEncounter) -> int:
    """Sum of the active participants' effective combat levels."""
    return sum(
        effective_combat_level(participant.character_sheet)
        for participant in encounter.participants.filter(
            status=ParticipantStatus.ACTIVE
        ).select_related("character_sheet")
    )


def _tier_weight(tier: str, config: StandoffConfig) -> int:
    return {
        OpponentTier.SWARM: config.swarm_weight,
        OpponentTier.MOOK: config.mook_weight,
        OpponentTier.ELITE: config.elite_weight,
        OpponentTier.BOSS: config.boss_weight,
        OpponentTier.HERO_KILLER: config.hero_killer_weight,
    }[tier]


def group_force(group: StandoffGroup, config: StandoffConfig) -> int:
    """Sum of active members' level times their tier weight (percent)."""
    return (
        sum(member.level * _tier_weight(member.tier, config) for member in active_members(group))
        // 100
    )


def effective_party_force(
    encounter: CombatEncounter, group: StandoffGroup, config: StandoffConfig
) -> int:
    """Party force, less what the group's emboldening has cost it."""
    penalty = config.band_force_percent * group.emboldened_bands
    return max(0, party_force(encounter) * (100 - penalty) // 100)


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
    """Settle empty groups; if an OPEN group's cause fires, the fight begins."""
    from world.standoffs.models import StandoffConfig  # noqa: PLC0415

    settle_empty_groups(encounter)
    config = StandoffConfig.load()
    for group in encounter.standoff_groups.filter(state=StandoffGroupState.OPEN).select_related(
        "creature_template"
    ):
        if cause_fires(group, config):
            end_standoff_into_fight(encounter, initiated_by_pc_side=False)
            return True
    return False
