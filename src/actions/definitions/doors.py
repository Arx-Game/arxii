"""Door lock/unlock Actions (#1866) and pick/break Actions (#2176).

Lock state is a plain Evennia attribute on the Exit object (``db.locked``)
— no new Django model, no migration. Room-owner/tenant gated, not
key-item gated (user decision, spec #1866): the simplest option reusing the
existing room-ownership substrate.

``PickLockAction`` and ``BreakExitAction`` (#2176) are the intruder path past
those locks: pick is quiet and check-gated (Wits + Larceny), break is loud
and always succeeds but damages building condition. Both leave crime-tagged
Legend deeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import (
    HasCharacterSheetPrerequisite,
    IsExitRoomOwnerPrerequisite,
    Prerequisite,
)
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class LockAction(Action):
    """Lock an exit, blocking traversal for anyone but the room's owner/tenant."""

    key: str = "lock_exit"
    name: str = "Lock Exit"
    icon: str = "lock"
    category: str = "locations"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsExitRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        exit_obj = kwargs.get("exit")
        if exit_obj is None:
            return ActionResult(success=False, message="Lock which exit?")
        exit_obj.db.locked = True
        return ActionResult(success=True, message=f"You lock {exit_obj.key}.")


@dataclass
class UnlockAction(Action):
    """Unlock an exit."""

    key: str = "unlock_exit"
    name: str = "Unlock Exit"
    icon: str = "lock-open"
    category: str = "locations"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsExitRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        exit_obj = kwargs.get("exit")
        if exit_obj is None:
            return ActionResult(success=False, message="Unlock which exit?")
        exit_obj.db.locked = False
        return ActionResult(success=True, message=f"You unlock {exit_obj.key}.")


# ---------------------------------------------------------------------------
# Intruder Actions (#2176)
# ---------------------------------------------------------------------------


def _resolve_exit_obj(actor: ObjectDB, kwargs: dict) -> ObjectDB | None:
    """Resolve an exit from kwargs — ObjectDB (telnet) or exit_id int (web).

    Follows the same dual-path pattern as ``_resolve_room`` in
    ``definitions/locations.py``: accept a resolved ObjectDB from telnet or
    a raw int pk from web dispatch.
    """
    exit_obj = kwargs.get("exit")
    if exit_obj is not None and hasattr(exit_obj, "pk"):
        return exit_obj
    exit_id = kwargs.get("exit_id")
    if exit_id is not None:
        from evennia.objects.models import ObjectDB as _ObjectDB  # noqa: PLC0415

        return _ObjectDB.objects.filter(pk=exit_id, db_location=actor.location).first()
    return None


def _burglary_crime_kind():
    """Lazy CrimeKind row for break-ins (mirrors _theft_crime_kind idiom)."""
    from world.justice.models import CrimeKind  # noqa: PLC0415

    kind, _ = CrimeKind.objects.get_or_create(
        slug="burglary",
        defaults={
            "name": "Burglary",
            "description": "Breaking in to take — walls breached, locks forced.",
        },
    )
    return kind


def _crime_source_type():
    """Lazy LegendSourceType row (mirrors _theft_source_type idiom)."""
    from world.societies.models import LegendSourceType  # noqa: PLC0415

    source_type, _ = LegendSourceType.objects.get_or_create(
        name="Crime",
        defaults={"description": "Personal antagonistic acts against another persona."},
    )
    return source_type


def _record_breakin_deed(
    actor: ObjectDB,
    exit_obj: ObjectDB,
    *,
    title_prefix: str,
    concealed: bool,
    base_value: int,
) -> None:
    """Create a crime-tagged Legend deed for a pick/break attempt.

    Mirrors ``_record_theft_deed`` in ``flows/service_functions/inventory.py``:
    resolve persona + scene from the actor, then call ``create_solo_deed``
    with ``crime_kinds=[burglary]`` and the requested concealment.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.societies.services import create_solo_deed  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return

    persona = active_persona_for_sheet(sheet)
    scene = get_active_scene(actor.location)
    create_solo_deed(
        persona,
        f"{title_prefix} at {exit_obj.key}",
        _crime_source_type(),
        base_value,
        scene=scene,
        crime_kinds=[_burglary_crime_kind()],
        concealed=concealed,
    )


@dataclass
class PickLockAction(Action):
    """Pick a locked exit — quiet, check-gated (Wits + Larceny).

    On success, unlocks the exit (``db.locked = False``). Either way,
    creates a concealed Legend deed tagged with the ``burglary`` CrimeKind
    so the justice/heat system tracks the attempt.
    """

    key: str = "pick_lock"
    name: str = "Pick Lock"
    icon: str = "key"
    category: str = "locations"
    target_type: TargetType = TargetType.SELF

    intent_event: str | None = "before_pick_lock"
    result_event: str | None = "pick_lock"

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        exit_obj = _resolve_exit_obj(actor, kwargs)
        if exit_obj is None:
            return ActionResult(success=False, message="Pick which exit?")

        if not exit_obj.db.locked:
            return ActionResult(success=False, message="That exit isn't locked.")

        from world.checks.models import CheckType  # noqa: PLC0415
        from world.checks.services import perform_check  # noqa: PLC0415

        check_type = CheckType.objects.filter(name="Lockpicking", is_active=True).first()
        if check_type is None:
            return ActionResult(success=False, message="Lockpicking isn't available right now.")

        check_result = perform_check(actor, check_type, target_difficulty=0)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)

        if check_result.outcome and check_result.outcome.success_level > 0:
            exit_obj.db.locked = False
            message_location(
                actor_state,
                "$You() $conj(pick) the lock on {target}.",
                mapping={"target": exit_obj},
            )
            success = True
            message = f"You pick the lock on {exit_obj.key}."
        else:
            message_location(
                actor_state,
                "$You() $conj(fumble) with the lock on {target}.",
                mapping={"target": exit_obj},
            )
            success = False
            message = f"You fail to pick the lock on {exit_obj.key}."

        _record_breakin_deed(
            actor, exit_obj, title_prefix="Lockpicking", concealed=True, base_value=5
        )

        return ActionResult(success=success, message=message)


@dataclass
class BreakExitAction(Action):
    """Break through a locked exit — loud, always succeeds.

    Unlocks the exit (``db.locked = False``), damages the building's
    condition tier by 1 (floored at DECAYED), emits a loud room echo,
    and creates a non-concealed Legend deed tagged with ``burglary``.
    """

    key: str = "break_exit"
    name: str = "Break Exit"
    icon: str = "hammer"
    category: str = "locations"
    target_type: TargetType = TargetType.SELF

    intent_event: str | None = "before_break_exit"
    result_event: str | None = "break_exit"

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        exit_obj = _resolve_exit_obj(actor, kwargs)
        if exit_obj is None:
            return ActionResult(success=False, message="Break which exit?")

        if not exit_obj.db.locked:
            return ActionResult(success=False, message="That exit isn't locked.")

        exit_obj.db.locked = False

        from world.buildings.constants import ConditionTier  # noqa: PLC0415
        from world.buildings.room_services import building_for_room  # noqa: PLC0415
        from world.buildings.upkeep_services import set_condition_tier  # noqa: PLC0415

        building = building_for_room(exit_obj.location)
        if building is not None:
            new_tier = max(ConditionTier.DECAYED, building.condition_tier - 1)
            set_condition_tier(building, new_tier)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(
            actor_state,
            "$You() $conj(break) through the lock on {target}!"
            " A loud crack echoes through the area.",
            mapping={"target": exit_obj},
        )

        _record_breakin_deed(
            actor, exit_obj, title_prefix="Break-in", concealed=False, base_value=10
        )

        return ActionResult(success=True, message=f"You break through the lock on {exit_obj.key}!")
