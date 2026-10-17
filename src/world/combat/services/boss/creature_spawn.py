"""Spawning opponents from creature templates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat import services as _svc
from world.combat.models import CombatEncounter, CombatOpponent, CreatureTemplate
from world.combat.services.boss.boss_phase_config import _clone_authored_phases

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.areas.positioning.models import Position
    from world.standoffs.services.placement import OpponentLine


def spawn_from_creature_template(
    encounter: CombatEncounter,
    template: CreatureTemplate,
    *,
    position: Position | None = None,
    acting_account: AccountDB | None = None,
    line: OpponentLine | None = None,
) -> CombatOpponent:
    """Spawn a CombatOpponent from a CreatureTemplate bestiary entry (#2016).

    Thin wrapper over add_opponent. Clones CreaturePhaseTemplate rows into
    BossPhase rows on the spawned opponent if present. Stamps break-bar
    config and vulnerability fields from BreakBarConfig.

    Stamps the standoff profile (#4361): cause, margin, affiliation, switched-off faction
    rules and drives, from the template and ``line``'s placement edits when the opponent
    comes from an authored opponent line.
    """
    from world.combat.models import CreaturePhaseTemplate  # noqa: PLC0415
    from world.standoffs.services.placement import (  # noqa: PLC0415
        draft_from_line,
        line_persona,
        placement_profile,
        stamp_opponent,
    )

    has_authored_phases = CreaturePhaseTemplate.objects.filter(creature_template=template).exists()
    # A named NPC line (#4373) stands the persona's own character with the template's stats.
    persona = line_persona(line)
    if persona is not None and persona.character_sheet.character.db_location_id != (
        encounter.room_id
    ):
        # The NPC is not in the encounter's room, so a position there cannot hold them.
        position = None

    opp = _svc.add_opponent(
        encounter,
        name=persona.name if persona is not None else template.name,
        persona=persona,
        tier=template.tier,
        threat_pool=template.threat_pool,
        soak_value=template.soak_override,
        probing_threshold=template.probing_override,
        auto_phases=not has_authored_phases,
        position=position,
        acting_account=acting_account,
    )
    opp.creature_template = template
    opp.save(update_fields=["creature_template"])
    stamp_opponent(opp, placement_profile(template, draft_from_line(line), persona=persona))

    if has_authored_phases:
        _clone_authored_phases(encounter, opp, template)

    return opp
