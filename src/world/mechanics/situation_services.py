"""Situation instantiation — traps-only scope (see #1625).

instantiate_situation mints a SituationInstance and materializes its
authored SituationTrapLink rows into real Trap rows at the target room.
It does NOT mint ChallengeInstances: instantiate_challenge()
(challenge_resolution.py) requires a caller-supplied target_object, and no
generic "what object embodies this challenge" mechanism exists yet — that
is a separate, unresolved design question (see the target_object-sourcing
follow-up), not solved here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.mechanics.models import SituationInstance
from world.room_features.models import Trap

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.mechanics.models import SituationTemplate


def instantiate_situation(template: SituationTemplate, location: ObjectDB) -> SituationInstance:
    """Mint a SituationInstance at ``location`` and materialize its authored traps.

    Raises ``django.core.exceptions.ObjectDoesNotExist`` (unwrapped) if
    ``location`` has no RoomProfile and the template carries trap links —
    this is a real caller error (wrong location passed in), not a case to
    silently skip.
    """
    instance = SituationInstance.objects.create(template=template, location=location)

    trap_links = list(template.trap_links.all())
    if trap_links:
        room_profile = location.room_profile
        for link in trap_links:
            Trap.objects.create(
                room_profile=room_profile,
                name=link.name,
                consequence_pool=link.consequence_pool,
                detect_check_type=link.detect_check_type,
                disarm_check_type=link.disarm_check_type,
                detect_difficulty=link.detect_difficulty,
                disarm_difficulty=link.disarm_difficulty,
                is_hidden=link.is_hidden,
            )

    return instance
