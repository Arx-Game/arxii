"""Court covenant engagement predicates (#1589 Task 5, #1717).

A Court vow ENGAGES while the member is "on the master's business" — EITHER (a)
a participant in an active mission given by the Court's backing organization
(``has_active_court_mission``), OR (b) a persona the Court's leader holds a
nonzero opinion of is co-present in the servant's current scene
(``has_regarded_target_present``, #1717). Both are scene-wide checks, not
per-technique or per-target.

The join chain for ``has_active_court_mission`` (verified against code):
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


def has_regarded_target_present(*, character_sheet: CharacterSheet, covenant: Covenant) -> bool:
    """Whether a persona ``covenant.leader`` holds a nonzero opinion of is co-present.

    Scene-level, same granularity as ``has_active_court_mission`` — checks the
    whole scene, not a specific technique's target. Any nonzero regard counts,
    positive or negative (a courting target counts the same as a hated enemy);
    see #1717 for why per-action-type filtering isn't built here. Presence uses
    the currently-shown persona (``active_persona_for_sheet``), so a disguised
    target correctly does not trigger this — the servant's allies wouldn't
    recognize them either.
    """
    from world.npc_services.regard import get_regard  # noqa: PLC0415
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if covenant.leader_id is None:
        return False
    leader_persona = covenant.leader.primary_persona

    char = character_sheet.character
    location = char.location
    if location is None or get_active_scene(location) is None:
        return False

    for obj in location.contents:
        sheet = obj.character_sheet
        if sheet is None or sheet == character_sheet:
            continue
        target_persona = active_persona_for_sheet(sheet)
        if get_regard(leader_persona, target_persona) != 0:
            return True
    return False
