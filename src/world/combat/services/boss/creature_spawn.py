"""Spawning opponents from creature templates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat import services as _svc
from world.combat.models import CombatEncounter, CombatOpponent, CreatureTemplate
from world.combat.services.boss.boss_phase_config import _clone_authored_phases

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.areas.positioning.models import Position


def spawn_from_creature_template(
    encounter: CombatEncounter,
    template: CreatureTemplate,
    *,
    position: Position | None = None,
    acting_account: AccountDB | None = None,
) -> CombatOpponent:
    """Spawn a CombatOpponent from a CreatureTemplate bestiary entry (#2016).

    Thin wrapper over add_opponent. Clones CreaturePhaseTemplate rows into
    BossPhase rows on the spawned opponent if present. Stamps break-bar
    config and vulnerability fields from BreakBarConfig.
    """
    from world.combat.models import CreaturePhaseTemplate  # noqa: PLC0415

    has_authored_phases = CreaturePhaseTemplate.objects.filter(creature_template=template).exists()

    opp = _svc.add_opponent(
        encounter,
        name=template.name,
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

    if has_authored_phases:
        _clone_authored_phases(encounter, opp, template)

    return opp
