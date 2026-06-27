"""Sanctum player actions — the action.run() seam for the 7 sanctum ops (#1497).

Each Action wraps an existing service in world/magic/services/sanctum_*.py and is
shared by telnet (commands/sanctum.py via dispatch_player_action) and the web
(world/magic/views_sanctum.py via Action().run()). The Action receives the already
-resolved sanctum / resonance / thread / room_profile as kwargs — each surface
resolves them independently (web: URL id; telnet: caller's room) — and never
self-resolves, so the web detail-ops keep their no-presence-check contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType
from world.magic.exceptions import ResonanceInsufficient
from world.magic.services.sanctum_install import (
    AbsorbError,
    DissolutionError,
    SanctificationError,
)
from world.magic.services.sanctum_rituals import (
    HomecomingValidationError,
    PurgingValidationError,
)
from world.magic.services.sanctum_weaving import SanctumWeavingError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

SANCTUM_EXC = (
    SanctificationError,
    DissolutionError,
    AbsorbError,
    HomecomingValidationError,
    PurgingValidationError,
    SanctumWeavingError,
    ResonanceInsufficient,
)


@dataclass
class SanctumActionBase(Action):
    """Shared base for the seven sanctum verbs."""

    key: str = ""
    name: str = ""
    icon: str = ""
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def _persona(self, actor: ObjectDB) -> Any:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None
        return active_persona_for_sheet(sheet)

    def _room_profile(self, actor: ObjectDB) -> Any:
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        if actor.location is None:
            return None
        return RoomProfile.objects.filter(objectdb=actor.location).first()

    def _sanctum_in_room(self, actor: ObjectDB) -> Any:
        from world.magic.models import SanctumDetails  # noqa: PLC0415

        rp = self._room_profile(actor)
        if rp is None:
            return None
        return (
            SanctumDetails.objects.select_related(
                "feature_instance__room_profile", "resonance_type"
            )
            .filter(feature_instance__room_profile=rp)
            .first()
        )

    @staticmethod
    def _fail(message: str) -> ActionResult:
        return ActionResult(success=False, message=message)
