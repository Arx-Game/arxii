"""Exit permission predicates shared by inspection and execution."""

from typing import TYPE_CHECKING, cast

from evennia_extensions.constants import ExitKind
from evennia_extensions.models import ExitProfile
from flows.object_states.base_state import BaseState

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB
    from evennia.objects.objects import DefaultObject


def _actor_lacks_room_standing(actor_obj: "ObjectDB", room: "ObjectDB") -> bool:
    from world.locations.constants import LocationRole  # noqa: PLC0415
    from world.locations.services import has_standing  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = actor_obj.character_sheet
    if sheet is None:
        return True
    persona = active_persona_for_sheet(sheet)
    return not has_standing(persona, cast("DefaultObject", room), at_least=LocationRole.GUEST)


def builtin_traversal_allowed(exit_obj: "ObjectDB", actor_obj: "ObjectDB | None" = None) -> bool:
    """Check the existing window, lock, bars and publication gates in order."""
    profile = ExitProfile.objects.filter(objectdb=exit_obj).first()
    if profile and profile.exit_kind == ExitKind.WINDOW and not profile.is_open:
        return False
    if actor_obj is None:
        return True
    if _standing_gate_refuses(exit_obj, actor_obj, profile):
        return False
    if actor_obj.is_story_runner:
        return True
    destination = exit_obj.destination
    if destination is None:
        return True
    destination_profile = destination.room_profile_or_none
    return destination_profile is None or destination_profile.published_at is not None


def _standing_gate_refuses(
    exit_obj: "ObjectDB", actor_obj: "ObjectDB", profile: ExitProfile | None
) -> bool:
    """Retain lock-before-bars evaluation and each gate's current room lookup."""
    from world.room_features.models import ExitBarsDetails  # noqa: PLC0415

    if exit_obj.db.locked:
        room = exit_obj.location
        if room is not None and _actor_lacks_room_standing(actor_obj, room):
            return True
    if profile is None:
        return False
    bars = ExitBarsDetails.objects.filter(exit_profile=profile).active().first()
    if bars is None:
        return False
    room = exit_obj.location
    return room is not None and _actor_lacks_room_standing(actor_obj, room)


class ExitState(BaseState):
    """State wrapper for exit objects."""

    def can_move(self, actor: BaseState | None = None, dest: BaseState | None = None) -> bool:
        """Prevent moving exits."""
        return False

    def can_traverse(self, actor: BaseState | None = None) -> bool:
        """Run built-in gates before the unchanged ordered execution hooks."""
        if not builtin_traversal_allowed(self.obj, None if actor is None else actor.obj):
            return False
        result = self._run_package_hook("can_traverse", actor)
        return bool(result) if result is not None else True
