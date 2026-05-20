"""Mission-run lifecycle services (Phase 5a) — accept / share.

These are the public service functions called by the front-door flow once
a character has chosen one of the templates returned by
``world.missions.services.availability.offer_missions``. They are
deliberately small: instance-create + participant-create + Phase-3
``enter_node`` for accept, single-participant insert for share.

The contract holder is the accepting character (design §10) and bears the
giver cooldown; sharees never get a cooldown row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.missions.models import (
    MissionGiverCooldown,
    MissionInstance,
    MissionNode,
    MissionParticipant,
)
from world.missions.services.resolution import enter_node

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionGiver, MissionTemplate


def _entry_node(template: MissionTemplate) -> MissionNode:
    """Return the template's unique entry node.

    The single-entry-node invariant is enforced by ``MissionNode.clean()``,
    so this is a safe ``.get()``. Missing entry node is an authoring error
    and surfaces here as ``MissionNode.DoesNotExist`` — loud, not silent.
    """
    return MissionNode.objects.get(template=template, is_entry=True)


@transaction.atomic
def accept_mission(
    giver: MissionGiver,
    template: MissionTemplate,
    character: ObjectDB,
) -> MissionInstance:
    """Create a live instance for ``character`` taking ``template`` from ``giver``.

    Side effects (atomic):
      * Create a :class:`MissionInstance` (status ACTIVE).
      * Create one :class:`MissionParticipant` with ``is_contract_holder=True``.
      * Call Phase-3 ``enter_node`` to write the entry-node snapshot and
        set ``instance.current_node``.
      * Upsert the giver cooldown to ``now + template.cooldown``.

    Returns the new instance.
    """
    instance = MissionInstance.objects.create(template=template)
    MissionParticipant.objects.create(
        instance=instance,
        character=character,
        is_contract_holder=True,
    )
    enter_node(instance, _entry_node(template))
    MissionGiverCooldown.objects.update_or_create(
        giver=giver,
        character=character,
        defaults={"available_at": timezone.now() + template.cooldown},
    )
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
