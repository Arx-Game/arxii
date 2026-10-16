"""Force comparison: whether a group's cause makes it open the fight."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.combat.constants import CauseKind, ParticipantStatus
from world.combat.models import OpponentTierTemplate
from world.combat.morale import OpponentMoraleState, morale_state_for
from world.covenants.mentorship import effective_combat_level
from world.standoffs.constants import (
    LIVE_GROUP_STATES,
    REASON_OUTWEIGHED,
    StandoffGroupState,
)
from world.standoffs.services.faction_rules import suppressed_for_all_participants
from world.standoffs.services.profile import group_cause
from world.standoffs.services.state import (
    active_members,
    end_standoff_into_fight,
    settle_empty_groups,
)
from world.stories.services.stakes import LEVELS_PER_TIER

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant
    from world.standoffs.models import StandoffConfig, StandoffGroup

DEFAULT_FORCE_WEIGHT_PERCENT = 100  # a tier with no template row counts as one level each
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


def _morale_percent(member: CombatOpponent, config: StandoffConfig) -> int:
    """A faltering or broken member counts for less, mindless or not.

    ``morale_state_for`` reads the raw morale on purpose: a mindless opponent whose morale
    has been driven low still falters and breaks, so the tier's ``has_morale`` is not read.
    """
    state = morale_state_for(member)
    if state == OpponentMoraleState.BREAK:
        return config.break_force_percent
    if state == OpponentMoraleState.FALTER:
        return config.falter_force_percent
    return 100


def group_force(group: StandoffGroup, config: StandoffConfig) -> float:
    """Active members' level x tier weight x health x morale, summed.

    A tier with no ``OpponentTierTemplate`` row weighs in at 100 percent, the same
    "a missing template changes nothing" convention as ``tier_has_morale``.
    """
    weights = {tpl.tier: tpl.force_weight_percent for tpl in OpponentTierTemplate.objects.all()}
    return sum(
        member.level
        * weights.get(member.tier, DEFAULT_FORCE_WEIGHT_PERCENT)
        / 100
        * _health_fraction(member.health, member.max_health)
        * _morale_percent(member, config)
        / 100
        for member in active_members(group)
    )


def effective_party_force(
    encounter: CombatEncounter, group: StandoffGroup, config: StandoffConfig
) -> float:
    """Party force, less what the group's emboldening has cost it."""
    penalty = config.band_force_percent * group.emboldened_bands
    return max(0.0, party_force(encounter, config) * (100 - penalty) / 100)


FORCE_CAUSES = frozenset({CauseKind.PREDATION, CauseKind.ORDERS})
PROVOKED_CAUSES = frozenset({CauseKind.ORDERS})


def _override_stands(
    group: StandoffGroup, party: float, theirs: float, *, lapse: bool = True
) -> bool:
    """True while a GM override holds: force has not moved since the GM overrode the cause.

    The first time force differs, the override lapses (its snapshot is cleared) and the
    cause is tested again. A botch clears it separately (``clear_override``).
    """
    if group.override_party_force is None or group.override_group_force is None:
        return False
    if math.isclose(party, group.override_party_force) and math.isclose(
        theirs, group.override_group_force
    ):
        return True
    if lapse:
        clear_override(group)
    return False


def clear_override(group: StandoffGroup) -> None:
    """Forget a GM override so the group's cause is tested again."""
    if group.override_party_force is None and group.override_group_force is None:
        return
    group.override_party_force = None
    group.override_group_force = None
    group.save(update_fields=["override_party_force", "override_group_force"])


def cause_fire_reason(
    group: StandoffGroup,
    config: StandoffConfig,
    provocation: str = "",
    *,
    lapse_override: bool = True,
) -> str | None:
    """Why the group's cause fires now, or None when it holds back.

    Predation fires when the party does not outweigh the group by its margin. Orders fires
    the same way, and also on ``provocation`` (the reason text of a botched press or terms
    against this group, passed only on the action that botched). A faction rule that
    suppresses the cause for every active participant stops either, and a standing GM
    override stops both until force moves. A read-only caller (the GM view) passes
    ``lapse_override=False`` so asking never clears an override that force has outgrown.
    """
    cause, margin = group_cause(group)
    if cause not in FORCE_CAUSES:
        return None
    party = effective_party_force(group.encounter, group, config)
    theirs = group_force(group, config)
    if _override_stands(group, party, theirs, lapse=lapse_override):
        return None
    reason = None
    if provocation and cause in PROVOKED_CAUSES:
        reason = provocation
    elif party * 100 <= theirs * (100 + margin):
        reason = REASON_OUTWEIGHED
    if reason is None or suppressed_for_all_participants(group):
        return None
    return reason


def cause_fires(group: StandoffGroup, config: StandoffConfig, provocation: str = "") -> bool:
    """True when the group's cause fires now (see ``cause_fire_reason``)."""
    return cause_fire_reason(group, config, provocation) is not None


def evaluate_causes(
    encounter: CombatEncounter,
    attack_sink: list[str] | None = None,
    *,
    provoked: StandoffGroup | None = None,
    provocation: str = "",
) -> bool:
    """Settle empty groups, then test every live group's cause.

    Settling the last live group (its members fled or were removed) leaves nothing to
    negotiate, so the standoff completes as a victory, as when the last terms are accepted.

    A firing cause starts the fight on its own when nobody runs the scene (missions, as in
    slice 1). In a GM-run standoff it becomes a proposal instead: the group goes PROPOSED
    and the GM gets a prompt; a group already PROPOSED just has its reason restated.
    ``provoked`` and ``provocation`` name the group a botch landed on this action and why.
    ``attack_sink`` is handed to ``end_standoff_into_fight`` (see there). True when the
    fight began.
    """
    from world.standoffs.models import StandoffConfig  # noqa: PLC0415
    from world.standoffs.services.proposals import (  # noqa: PLC0415
        propose,
        restate_proposal,
        standoff_is_gm_run,
    )

    if (
        settle_empty_groups(encounter)
        and not encounter.standoff_groups.exclude(state=StandoffGroupState.SETTLED).exists()
    ):
        from world.standoffs.services.routing import complete_standoff  # noqa: PLC0415

        complete_standoff(encounter)
        return False
    config = StandoffConfig.load()
    gm_run: bool | None = None
    for group in encounter.standoff_groups.filter(state__in=LIVE_GROUP_STATES).select_related(
        "creature_template"
    ):
        own_provocation = provocation if provoked is not None and group.pk == provoked.pk else ""
        reason = cause_fire_reason(group, config, own_provocation)
        if reason is None:
            continue
        if group.state == StandoffGroupState.PROPOSED:
            restate_proposal(group, reason)
            continue
        if gm_run is None:
            gm_run = standoff_is_gm_run(encounter)
        if gm_run and propose(group, reason):
            continue
        return end_standoff_into_fight(
            encounter, initiated_by_pc_side=False, attack_sink=attack_sink
        )
    return False
