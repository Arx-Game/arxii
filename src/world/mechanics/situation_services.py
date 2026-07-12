"""Situation instantiation (see #1625, #1895).

instantiate_situation mints a SituationInstance and materializes its
authored SituationTrapLink and SituationChallengeLink rows into real Trap
and ChallengeInstance rows at the target location. For challenges, it
auto-creates a bare ObjectDB per link (named from the link's authored
target_object_name) and delegates to the existing instantiate_challenge().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from evennia.objects.models import ObjectDB

from world.mechanics.challenge_resolution import instantiate_challenge
from world.mechanics.models import SituationInstance
from world.room_features.models import Trap

if TYPE_CHECKING:
    from world.mechanics.models import SituationTemplate

_TARGET_OBJECT_TYPECLASS = "typeclasses.objects.Object"


def instantiate_situation(template: SituationTemplate, location: ObjectDB) -> SituationInstance:
    """Mint a SituationInstance at ``location`` and materialize its authored content.

    Raises ``django.core.exceptions.ObjectDoesNotExist`` (unwrapped) if
    ``location`` has no RoomProfile and the template carries trap links —
    this is a real caller error (wrong location passed in), not a case to
    silently skip. Challenges have no such requirement (ChallengeInstance
    doesn't need a RoomProfile). The instance and all its traps/challenges
    are created atomically: if materialization fails partway (including the
    RoomProfile lookup), no orphaned SituationInstance survives.
    """
    with transaction.atomic():
        instance = SituationInstance.objects.create(template=template, location=location)

        trap_links = list(template.trap_links.all())
        if trap_links:
            from evennia_extensions.models import RoomProfile  # noqa: PLC0415

            room_profile = RoomProfile.objects.filter(objectdb=location).first()
            if room_profile is None:
                msg = "location has no RoomProfile"
                raise ObjectDoesNotExist(msg)
            for trap_link in trap_links:
                Trap.objects.create(
                    room_profile=room_profile,
                    name=trap_link.name,
                    consequence_pool=trap_link.consequence_pool,
                    detect_check_type=trap_link.detect_check_type,
                    disarm_check_type=trap_link.disarm_check_type,
                    detect_difficulty=trap_link.detect_difficulty,
                    disarm_difficulty=trap_link.disarm_difficulty,
                    is_hidden=trap_link.is_hidden,
                )

        for challenge_link in template.challenge_links.all():
            target = ObjectDB.objects.create(
                db_key=challenge_link.target_object_name,
                db_typeclass_path=_TARGET_OBJECT_TYPECLASS,
            )
            instantiate_challenge(
                challenge_link.challenge_template,
                location=location,
                target_object=target,
            )

    return instance
