"""Flee mechanic for story-critical NPCs (#1874).

When an external actor tries to kill a story-critical NPC, the NPC flees
instead of dying. The NPC's health is floored, status set to FLED, and the
NPC is moved out of the room. An OOC message goes to the attacker; online
staff get a detailed notification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB as ObjectDBModel

from world.combat.constants import OpponentStatus
from world.stories.models import StoryNPCDependency

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatOpponent


def flee_story_critical_npc(
    opponent: CombatOpponent,
    attacker: ObjectDB | None,
) -> None:
    """Execute the flee mechanic for a story-critical NPC.

    Floors the opponent's health, sets FLED status, moves the NPC's ObjectDB
    out of the room, and sends notifications.

    Args:
        opponent: The CombatOpponent whose death was prevented.
        attacker: The attacking character's ObjectDB, or None.
    """
    # Floor health at 1 (non-lethal)
    opponent.health = max(1, opponent.health)
    opponent.status = OpponentStatus.FLED
    opponent.save(update_fields=["health", "status"])

    # Resolve the NPC's ObjectDB and move it out of the room
    npc_obj = None
    if opponent.objectdb_id is not None:
        npc_obj = ObjectDBModel.objects.get(pk=opponent.objectdb_id)

    if npc_obj is not None:
        destination = npc_obj.db_home
        if destination is None:
            # Fallback: Limbo (pk=1) if no home set. May not exist in test envs.
            destination = ObjectDBModel.objects.filter(pk=1).first()
        if destination is not None:
            npc_obj.move_to(destination, quiet=False)
        elif npc_obj.location is not None:
            # No destination available — clear location so the NPC leaves the room
            npc_obj.location = None
            npc_obj.save(update_fields=["location"])

    # Resolve the NPC's CharacterSheet for notification
    npc_sheet: CharacterSheet | None = None
    if npc_obj is not None:
        try:
            npc_sheet = npc_obj.sheet_data
        except AttributeError:
            npc_sheet = None

    # Send OOC message to attacker
    if attacker is not None:
        attacker.msg(
            "This NPC cannot be removed from play due to ties to another "
            "story. They have fled the scene — please narrate a plausible "
            "reason for their survival."
        )

    # Notify online staff
    if npc_sheet is not None:
        _notify_staff_of_story_flee(npc_sheet)


def _notify_staff_of_story_flee(npc_sheet: CharacterSheet) -> None:
    """Notify online staff that a story-critical NPC fled from combat.

    Lists the affected stories so staff can adjudicate crossover climaxes.

    Args:
        npc_sheet: The NPC's CharacterSheet.
    """
    affected = list(
        StoryNPCDependency.objects.filter(
            npc_sheet=npc_sheet,
            is_active=True,
        ).select_related("story")
    )

    story_names = [dep.story.title for dep in affected]
    story_list = ", ".join(story_names) if story_names else "unknown stories"

    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    staff = AccountDB.objects.filter(is_staff=True)
    for account in staff:
        if not account.sessions.all():
            continue
        account.msg(
            f"[Staff] Story-critical NPC '{npc_sheet}' fled from combat. "
            f"Affected stories: {story_list}. Please adjudicate if needed."
        )
