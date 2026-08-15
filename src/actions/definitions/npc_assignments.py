"""NPC role assignment actions: GUARD (#2178), SERVANT/DOORMAN (#2989).

Owner-gated actions to assign/unassign NPCs to a room role and view current
assignments. Shared by telnet (``CmdGuard``/``CmdServant``/``CmdDoorman``)
and the web dispatcher. All nine action classes below are thin dataclass
wrappers over the three shared `_assign_npc_role`/`_unassign_npc_role`/
`_list_npc_role` helpers — one implementation of "assign/unassign/list an
NPC role," parameterized by `role`/message wording, not nine near-duplicate
`execute()` bodies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import IsRoomOwnerPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from actions.types import ActionContext


@dataclass
class AssignGuardAction(Action):
    """Assign a Functionary or NPCAsset as a guard to the actor's room.

    Kwargs:
        source_type: ``"functionary"`` or ``"npc_asset"``.
        npc_id: The pk of the Functionary or NPCAsset.
        room_id: Optional web canvas anchor (defaults to actor.location).
    """

    key: str = "assign_guard"
    name: str = "Assign Guard"
    icon: str = "shield"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _assign_npc_role(actor, kwargs, role="guard", on_duty_label="on guard duty")


@dataclass
class UnassignGuardAction(Action):
    """Retire the active guard assignment in the actor's room.

    Kwargs:
        room_id: Optional web canvas anchor (defaults to actor.location).
    """

    key: str = "unassign_guard"
    name: str = "Unassign Guard"
    icon: str = "shield-off"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _unassign_npc_role(actor, kwargs, role="guard", noun="guard")


@dataclass
class ListGuardAssignmentsAction(Action):
    """List active guard assignments in the actor's room.

    Kwargs:
        room_id: Optional web canvas anchor (defaults to actor.location).
    """

    key: str = "list_guard_assignments"
    name: str = "Guard Assignments"
    icon: str = "list"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _list_npc_role(actor, kwargs, role="guard", noun="guard")


@dataclass
class AssignServantAction(Action):
    """Assign a Functionary or NPCAsset as household SERVANT staff (#2989).

    Mirrors ``AssignGuardAction`` — same owner gate, same one-active-per-room
    shape — with ``assignment_role=SERVANT``. Powers servant fetch (#2276)
    and the pampering ambience (meal/bath prep, ``servant_ambience.py``).

    Kwargs:
        source_type: ``"functionary"`` or ``"npc_asset"``.
        npc_id: The pk of the Functionary or NPCAsset.
        room_id: Optional web canvas anchor (defaults to actor.location).
    """

    key: str = "assign_servant"
    name: str = "Assign Servant"
    icon: str = "user-check"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _assign_npc_role(actor, kwargs, role="servant", on_duty_label="on household duty")


@dataclass
class UnassignServantAction(Action):
    """Retire the active SERVANT assignment in the actor's room (#2989)."""

    key: str = "unassign_servant"
    name: str = "Unassign Servant"
    icon: str = "user-x"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _unassign_npc_role(actor, kwargs, role="servant", noun="servant")


@dataclass
class ListServantAssignmentsAction(Action):
    """List active SERVANT assignments in the actor's room (#2989)."""

    key: str = "list_servant_assignments"
    name: str = "Servant Assignments"
    icon: str = "list"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _list_npc_role(actor, kwargs, role="servant", noun="servant")


@dataclass
class AssignDoormanAction(Action):
    """Assign a Functionary or NPCAsset as DOORMAN (#2989).

    Mirrors ``AssignGuardAction`` — same owner gate, same one-active-per-room
    shape — with ``assignment_role=DOORMAN``. Powers arrival announcement
    (``doorman_services.announce_arrival``, wired at ``Character.at_post_move``).

    Kwargs:
        source_type: ``"functionary"`` or ``"npc_asset"``.
        npc_id: The pk of the Functionary or NPCAsset.
        room_id: Optional web canvas anchor (defaults to actor.location).
    """

    key: str = "assign_doorman"
    name: str = "Assign Doorman"
    icon: str = "door-open"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _assign_npc_role(actor, kwargs, role="doorman", on_duty_label="posted at the door")


@dataclass
class UnassignDoormanAction(Action):
    """Retire the active DOORMAN assignment in the actor's room (#2989)."""

    key: str = "unassign_doorman"
    name: str = "Unassign Doorman"
    icon: str = "door-closed"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _unassign_npc_role(actor, kwargs, role="doorman", noun="doorman")


@dataclass
class ListDoormanAssignmentsAction(Action):
    """List active DOORMAN assignments in the actor's room (#2989)."""

    key: str = "list_doorman_assignments"
    name: str = "Doorman Assignments"
    icon: str = "list"
    category: str = "npc_services"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _list_npc_role(actor, kwargs, role="doorman", noun="doorman")


def _assign_npc_role(
    actor: ObjectDB,
    kwargs: dict[str, Any],
    *,
    role: str,
    on_duty_label: str,
) -> ActionResult:
    """Shared assign logic for SERVANT/DOORMAN — mirrors ``AssignGuardAction.execute``."""
    from django.utils import timezone  # noqa: PLC0415

    from world.npc_services.models import NPCAssignment, NPCSourceType  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    room = _resolve_room(actor, kwargs)
    if room is None:
        return ActionResult(success=False, message=_no_room_message(kwargs))

    source_type = kwargs.get("source_type", "")
    npc_id = kwargs.get("npc_id")

    if source_type == NPCSourceType.FUNCTIONARY.value:
        from world.npc_services.models import Functionary  # noqa: PLC0415

        npc = Functionary.objects.filter(pk=npc_id).first()
        if npc is None:
            return ActionResult(success=False, message="No such functionary.")
        source_type_enum = NPCSourceType.FUNCTIONARY
    elif source_type == NPCSourceType.NPC_ASSET.value:
        from world.assets.models import NPCAsset  # noqa: PLC0415

        npc = NPCAsset.objects.filter(pk=npc_id).first()
        if npc is None:
            return ActionResult(success=False, message="No such NPC asset.")
        source_type_enum = NPCSourceType.NPC_ASSET
    else:
        return ActionResult(success=False, message="Invalid source type.")

    profile = _room_profile_for(room)
    if profile is None:
        return ActionResult(success=False, message="This room has no profile.")

    persona = active_persona_for_sheet(actor.sheet_data)

    NPCAssignment.objects.filter(
        room=profile,
        assignment_role=role,
        is_active=True,
    ).update(is_active=False, ended_at=timezone.now())

    assignment = NPCAssignment.objects.create(
        source_type=source_type_enum,
        functionary=npc if source_type_enum == NPCSourceType.FUNCTIONARY else None,
        npc_asset=npc if source_type_enum == NPCSourceType.NPC_ASSET else None,
        room=profile,
        assignment_role=role,
        assigned_by=persona,
    )
    return ActionResult(
        success=True,
        message=f"{assignment.get_active_target_name()} is now {on_duty_label}.",
    )


def _unassign_npc_role(
    actor: ObjectDB,
    kwargs: dict[str, Any],
    *,
    role: str,
    noun: str,
) -> ActionResult:
    """Shared unassign logic for SERVANT/DOORMAN — mirrors ``UnassignGuardAction.execute``."""
    from django.utils import timezone  # noqa: PLC0415

    from world.npc_services.models import NPCAssignment  # noqa: PLC0415

    room = _resolve_room(actor, kwargs)
    if room is None:
        return ActionResult(success=False, message=_no_room_message(kwargs))

    profile = _room_profile_for(room)
    if profile is None:
        return ActionResult(success=False, message="This room has no profile.")

    updated = NPCAssignment.objects.filter(
        room=profile,
        assignment_role=role,
        is_active=True,
    ).update(is_active=False, ended_at=timezone.now())

    if updated == 0:
        return ActionResult(success=False, message=f"There is no {noun} assigned here.")
    return ActionResult(success=True, message=f"{noun.capitalize()} unassigned.")


def _list_npc_role(
    actor: ObjectDB,
    kwargs: dict[str, Any],
    *,
    role: str,
    noun: str,
) -> ActionResult:
    """Shared list logic for SERVANT/DOORMAN — mirrors ``ListGuardAssignmentsAction.execute``."""
    from world.npc_services.models import NPCAssignment  # noqa: PLC0415

    room = _resolve_room(actor, kwargs)
    if room is None:
        return ActionResult(success=False, message=_no_room_message(kwargs))

    profile = _room_profile_for(room)
    if profile is None:
        return ActionResult(
            success=True, message=f"No {noun} assignments.", data={"assignments": []}
        )

    assignments = NPCAssignment.objects.filter(
        room=profile,
        assignment_role=role,
        is_active=True,
    ).select_related("functionary", "npc_asset")

    if not assignments:
        return ActionResult(
            success=True, message=f"No {noun} assignments.", data={"assignments": []}
        )

    data = [
        {
            "id": a.pk,
            "name": a.get_active_target_name(),
            "role": a.assignment_role,
            "source_type": a.source_type,
        }
        for a in assignments
    ]
    return ActionResult(
        success=True,
        message=f"{len(data)} {noun}(s) assigned.",
        data={"assignments": data},
    )


def _resolve_room(actor: ObjectDB, kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the anchor room: explicit room_id (web) else actor.location."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    room_id = kwargs.get("room_id")
    if room_id:
        profile = RoomProfile.objects.filter(objectdb_id=room_id).select_related("objectdb").first()
        return profile.objectdb if profile else None
    return actor.location


def _room_profile_for(room: ObjectDB):
    """Resolve the RoomProfile for a room ObjectDB."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    return RoomProfile.objects.filter(objectdb=room).first()


def _no_room_message(kwargs: dict[str, Any]) -> str:
    return "No such room." if kwargs.get("room_id") else "You're not in a room."
