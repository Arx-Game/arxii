"""Combat encounter → area quality erosion (#1889).

Flow-callable invoked by an ENCOUNTER_COMPLETED trigger. Only
OPEN_ENCOUNTER erodes area quality — duels and party combat do not.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.areas.cleanup_services import erode_area_quality
from world.combat.constants import EncounterType

if TYPE_CHECKING:
    from world.areas.models import Area

logger = logging.getLogger(__name__)

# Encounter types that erode area quality when completed.
ERODING_ENCOUNTER_TYPES = frozenset({EncounterType.OPEN_ENCOUNTER})


def erode_on_encounter_completed(
    *,
    encounter_type: str,
    area: Area | None,
) -> None:
    """Erode area quality when an OPEN_ENCOUNTER completes in the area.

    Gates on encounter_type — only OPEN_ENCOUNTER (street brawls) erodes.
    DUEL and PARTY_COMBAT do not. Mirrors the gate pattern in
    battles/duel_wiring.py:46.
    """
    if area is None:
        return
    if encounter_type not in ERODING_ENCOUNTER_TYPES:
        return
    erode_area_quality(area)
    logger.info("area %s quality eroded by %s encounter.", area.pk, encounter_type)
