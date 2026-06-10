"""Mission-run lifecycle services — share + staff-assign.

The NPC-mediated accept flow now lives on the unified offer framework:
``world.missions.services.offer_handler.issue_mission`` is the MISSION
effect handler dispatched by ``world.npc_services.services.resolve_offer``
once the player selects a MISSION-kind ``NPCServiceOffer``. Per #686.

This module retains ``staff_assign_mission`` (staff-power drop without a
giver context — used by the Phase-D staff-assign action) and
``share_mission`` (the non-contract-holder participant add).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from evennia_extensions.models import RoomProfile
from world.missions.models import (
    MissionInstance,
    MissionNode,
    MissionParticipant,
)
from world.missions.services.resolution import enter_node

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionTemplate


def _entry_node(template: MissionTemplate) -> MissionNode:
    """Return the template's unique entry node.

    The single-entry-node invariant is enforced by ``MissionNode.clean()``,
    so this is a safe ``.get()``. Missing entry node is an authoring error
    and surfaces here as ``MissionNode.DoesNotExist`` — loud, not silent.
    """
    return MissionNode.objects.get(template=template, is_entry=True)


def anchor_room_for(character: ObjectDB) -> RoomProfile | None:
    """The grant-time anchor: the RoomProfile of the character's location (#885).

    Uniform across all three grant paths — the trigger grant happens while
    standing in the trigger room, the NPC offer in the NPC's room, the
    staff assign wherever the character is. ``None`` (no location, or a
    location with no profile — non-room containers) means a placeless
    grant: ANCHOR-mode options simply never fire for that run.
    """
    location = character.location
    if location is None:
        return None
    try:
        return location.room_profile
    except RoomProfile.DoesNotExist:
        return None


@transaction.atomic
def staff_assign_mission(template: MissionTemplate, character: ObjectDB) -> MissionInstance:
    """Staff-power: drop a mission on a character without a giver context.

    Bypasses all availability filters (predicate / cooldown / level band /
    access tier). Used by the staff-assign action so operators can hand-
    place missions for testing, narrative reasons, or recovery scenarios.

    Wrapped in ``@transaction.atomic`` so a failure in ``enter_node`` rolls
    back the half-created MissionInstance + MissionParticipant.
    """
    instance = MissionInstance.objects.create(
        template=template,
        anchor_room=anchor_room_for(character),
    )
    MissionParticipant.objects.create(
        instance=instance,
        character=character,
        is_contract_holder=True,
    )
    enter_node(instance, _entry_node(template))
    return instance


def share_mission(
    instance: MissionInstance,
    other_character: ObjectDB,
) -> MissionParticipant:
    """Add ``other_character`` as a non-holder participant to ``instance``.

    Design §10: sharees are full participants but never bear the
    contractual consequence — no cooldown row, no giver linkage.
    """
    return MissionParticipant.objects.create(
        instance=instance,
        character=other_character,
        is_contract_holder=False,
    )
