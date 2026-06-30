"""Mission-driven engagement predicate for Court covenants (#1589 Task 5).

A Court vow ENGAGES only while the member is "on the master's business" — a
participant in an active mission given by the Court's backing organization.
The mission, not co-presence, is the gate.

The join chain (verified against code):
  ``MissionInstance.participants`` (related_name) -> ``MissionParticipant.character``
    (FK -> ``objects.ObjectDB``, hence the filter is on ``character_sheet.character``)
  ``MissionInstance.status == MissionStatus.ACTIVE``
  ``MissionInstance.source_offer`` -> ``NPCServiceOffer.role``
    -> ``NPCRole.faction_affiliation`` matched against ``covenant.organization_id``.

A NULL ``source_offer`` (trigger/legacy/staff-seeded runs) simply never matches
the org — correct, those are not Court missions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import Covenant


def has_active_court_mission(*, character_sheet: CharacterSheet, covenant: Covenant) -> bool:
    """Whether ``character_sheet``'s servant is on an active mission for ``covenant``'s org.

    Single ``.exists()`` query — no query-in-loop. ``world.missions`` is
    lazy-imported to avoid a covenants -> missions import cycle.
    """
    from world.missions.constants import MissionStatus  # noqa: PLC0415
    from world.missions.models import MissionInstance  # noqa: PLC0415

    return MissionInstance.objects.filter(
        participants__character=character_sheet.character,
        status=MissionStatus.ACTIVE,
        source_offer__role__faction_affiliation_id=covenant.organization_id,
    ).exists()
