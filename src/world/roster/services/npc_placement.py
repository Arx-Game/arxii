"""Putting a GM's story NPC into a scene (#4418).

A story NPC is in a scene's cast list when it stands in the scene's room
(``world.scenes.cast_list_services``). The GM's NPC form places a new or existing NPC
there without anyone having to puppet and walk it in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.roster.models import RosterEntry
    from world.scenes.models import Scene

NOT_A_STORY_NPC_MESSAGE = "Only a story NPC can be placed in a scene."
NOT_YOURS_MESSAGE = "That NPC isn't yours to place."
LENT_OUT_MESSAGE = "That NPC is lent to someone else right now."
NO_ROOM_MESSAGE = "That scene isn't held anywhere."
SCENE_OVER_MESSAGE = "That scene has ended."


class NPCPlacementError(Exception):
    """A placement the rules refuse; ``user_message`` is safe to show the player."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


@transaction.atomic
def place_npc_in_scene(*, entry: RosterEntry, scene: Scene, by: AccountDB) -> None:
    """Move ``entry``'s character into ``scene``'s room.

    ``by`` must own the NPC (``created_by_account``) or be staff, and the NPC must not
    be lent to someone else: whoever is playing it decides where it stands. Which
    scenes ``by`` may place into is the caller's check.
    """
    from world.roster.services.activity import is_story_npc  # noqa: PLC0415
    from world.roster.services.npc_lending import active_loan_for  # noqa: PLC0415

    sheet = entry.character_sheet
    if not is_story_npc(sheet):
        raise NPCPlacementError(NOT_A_STORY_NPC_MESSAGE)
    if not (by.is_staff or entry.created_by_account_id == by.pk):
        raise NPCPlacementError(NOT_YOURS_MESSAGE)
    loan = active_loan_for(entry)
    if loan is not None and loan.borrower_id != by.pk:
        raise NPCPlacementError(LENT_OUT_MESSAGE)
    if not scene.is_active:
        raise NPCPlacementError(SCENE_OVER_MESSAGE)
    room = scene.room
    if room is None:
        raise NPCPlacementError(NO_ROOM_MESSAGE)
    character = sheet.character
    if character.db_location_id == room.pk:
        return
    character.location = room
    character.save(update_fields=["db_location"])
