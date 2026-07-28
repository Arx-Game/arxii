"""Org-task and spy-network actions (#2820 telnet/actions layer).

The action.run() seam for the tasking system — shared by the telnet
``network`` command family and the web tasking viewsets (ADR-0001). Every
action resolves the actor's active persona and delegates to the tasking
service layer; no business logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from actions.types import ActionContext
    from world.scenes.models import Persona

_CATEGORY = "tasking"


def _active_persona(actor: ObjectDB) -> Persona | None:
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    return active_persona_for_sheet(sheet)


def _room_profile(actor: ObjectDB):
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    if actor.location is None:
        return None
    return RoomProfile.objects.filter(objectdb=actor.location).first()


def _sitting_post(room_profile):
    from world.tasking.models import ListenerPost  # noqa: PLC0415

    if room_profile is None:
        return None
    return ListenerPost.objects.filter(
        assignment__room_id=room_profile.pk,
        assignment__is_active=True,
    ).first()


_NO_PERSONA = ActionResult(success=False, message="You have no active persona.")


@dataclass
class ListOrgTasksAction(Action):
    """The board hub: tasks, roster, and postings visible to the actor.

    Kwargs:
        org_id: Optional — narrow to one organization.
    """

    key: str = "list_org_tasks"
    name: str = "Task Board"
    icon: str = "clipboard-list"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.societies.models import OrganizationMembership  # noqa: PLC0415
        from world.societies.office_services import overseen_org_ids  # noqa: PLC0415
        from world.tasking.models import ListenerPost, OrgTask  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        member_org_ids = list(
            OrganizationMembership.objects.filter(
                persona=persona,
                left_at__isnull=True,
                exiled_at__isnull=True,
            ).values_list("organization_id", flat=True)
        )
        allowed = set(member_org_ids) | set(overseen_org_ids(persona))
        org_id = kwargs.get("org_id")
        if org_id:
            allowed &= {int(org_id)}

        tasks = (
            OrgTask.objects.filter(org_id__in=allowed)
            .select_related("template", "org")
            .order_by("-created_at")[:20]
        )
        posts = ListenerPost.objects.filter(
            assignment__is_active=True,
            assignment__npc_asset__promoter_org_id__in=allowed,
        ).select_related("assignment__npc_asset__asset_persona") | ListenerPost.objects.filter(
            assignment__is_active=True, handler=persona
        ).select_related("assignment__npc_asset__asset_persona")

        lines = [
            f"#{task.pk} [{task.status}] {task.template.name} ({task.org.name})" for task in tasks
        ]
        for post in posts.distinct():
            asset = post.assignment.npc_asset
            agent = str(asset.asset_persona) if asset else "?"
            pending = post.harvests.filter(collected_at__isnull=True).count()
            ready = f" — {pending} to collect" if pending else ""
            lines.append(
                f"post #{post.pk}: {agent} listening (buzz {post.buzz}/{post.threshold}){ready}"
            )
        if not lines:
            return ActionResult(success=True, message="Your networks report nothing.")
        return ActionResult(success=True, message="\n".join(lines))


@dataclass
class IssueOrgTaskAction(Action):
    """Issue a task from a template (org leadership only).

    Kwargs:
        template_id, org_id, and optional target_room_id / target_org_id /
        target_domain_id / target_persona_id matching the template's kind.
    """

    key: str = "issue_org_task"
    name: str = "Issue Task"
    icon: str = "clipboard-plus"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.houses.models import Domain  # noqa: PLC0415
        from world.societies.houses.services import is_org_leader  # noqa: PLC0415
        from world.societies.models import Organization  # noqa: PLC0415
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415
        from world.tasking.models import TaskTemplate  # noqa: PLC0415
        from world.tasking.services import create_task  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        template = TaskTemplate.objects.filter(pk=kwargs.get("template_id")).first()
        org = Organization.objects.filter(pk=kwargs.get("org_id")).first()
        if template is None or org is None:
            return ActionResult(success=False, message="No such template or organization.")
        if not is_org_leader(persona, org):
            return ActionResult(
                success=False,
                message="Only the organization's leadership can issue tasks.",
            )
        try:
            task = create_task(
                template,
                org,
                persona,
                target_room=RoomProfile.objects.filter(pk=kwargs.get("target_room_id")).first(),
                target_org=Organization.objects.filter(pk=kwargs.get("target_org_id")).first(),
                target_domain=Domain.objects.filter(pk=kwargs.get("target_domain_id")).first(),
                target_persona=Persona.objects.filter(pk=kwargs.get("target_persona_id")).first(),
            )
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValidationError:
            return ActionResult(
                success=False,
                message="That target does not fit the template's target kind.",
            )
        return ActionResult(
            success=True,
            message=f"Task #{task.pk} issued: {template.name}.",
            data={"task_id": task.pk},
        )


@dataclass
class AssignTaskAgentAction(Action):
    """Dispatch an agent on an OPEN task (rolls your dispatch check).

    Kwargs: task_id, npc_asset_id.
    """

    key: str = "assign_task_agent"
    name: str = "Dispatch Agent"
    icon: str = "send"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.assets.models import NPCAsset  # noqa: PLC0415
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415
        from world.tasking.models import OrgTask  # noqa: PLC0415
        from world.tasking.services import assign_agent  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        task = OrgTask.objects.filter(pk=kwargs.get("task_id")).first()
        npc_asset = NPCAsset.objects.filter(pk=kwargs.get("npc_asset_id")).first()
        if task is None or npc_asset is None:
            return ActionResult(success=False, message="No such task or agent.")
        try:
            assign_agent(task, npc_asset, persona)
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=(
                f"{npc_asset.asset_persona} slips away on task #{task.pk}. "
                f"They report back by {task.deadline:%Y-%m-%d %H:%M}."
            ),
        )


@dataclass
class AcceptOrgTaskAction(Action):
    """Pick up a PC-fulfillable task yourself as a mission.

    Kwargs: task_id.
    """

    key: str = "accept_org_task"
    name: str = "Accept Task"
    icon: str = "hand"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415
        from world.tasking.models import OrgTask  # noqa: PLC0415
        from world.tasking.services import accept_task  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        task = OrgTask.objects.filter(pk=kwargs.get("task_id")).first()
        if task is None:
            return ActionResult(success=False, message="No such task.")
        try:
            fulfillment = accept_task(task, persona)
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=(
                f"You take task #{task.pk} yourself. "
                f"See `mission` for your new run (#{fulfillment.mission_instance_id})."
            ),
            data={"mission_instance_id": fulfillment.mission_instance_id},
        )


@dataclass
class PostListenerAction(Action):
    """Post an agent as this room's listener.

    Kwargs: npc_asset_id (room = your location).
    """

    key: str = "post_listener"
    name: str = "Post Listener"
    icon: str = "ear"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.assets.models import NPCAsset  # noqa: PLC0415
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415
        from world.tasking.listener_services import create_listener_post  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        # Explicit room_id is the web anchor; telnet posts where you stand.
        room_id = kwargs.get("room_id")
        if room_id:
            room = RoomProfile.objects.filter(pk=room_id).first()
        else:
            room = _room_profile(actor)
        if room is None:
            return ActionResult(success=False, message="You're not in a room.")
        npc_asset = NPCAsset.objects.filter(pk=kwargs.get("npc_asset_id")).first()
        if npc_asset is None:
            return ActionResult(success=False, message="No such agent.")
        check_type = None
        if kwargs.get("check_type_id"):
            from world.checks.models import CheckType  # noqa: PLC0415

            check_type = CheckType.objects.filter(pk=kwargs["check_type_id"]).first()
        try:
            post = create_listener_post(
                npc_asset,
                room,
                persona,
                check_type=check_type,
                check_difficulty=int(kwargs.get("check_difficulty") or 0),
            )
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{npc_asset.asset_persona} settles in here, ears open (post #{post.pk}).",
            data={"post_id": post.pk},
        )


@dataclass
class CollectHarvestAction(Action):
    """Collect from your listener in this room (you must be present)."""

    key: str = "collect_harvest"
    name: str = "Collect"
    icon: str = "inbox"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415
        from world.tasking.listener_services import collect_harvest  # noqa: PLC0415
        from world.tasking.models import ListenerPost  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        # Explicit post_id is the web anchor; telnet collects where you stand.
        post_id = kwargs.get("post_id")
        if post_id:
            post = ListenerPost.objects.filter(pk=post_id).first()
        else:
            post = _sitting_post(_room_profile(actor))
        if post is None:
            return ActionResult(success=False, message="None of your agents listen here.")
        try:
            clue = collect_harvest(post, persona)
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        if clue is None:
            return ActionResult(
                success=True,
                message="Your agent has little of substance — talk, but nothing solid.",
            )
        return ActionResult(success=True, message=f"Your agent leans close: {clue.name}.")


@dataclass
class SuppressListenerAction(Action):
    """Intimidate this room's sitting listener into silence."""

    key: str = "suppress_listener"
    name: str = "Suppress Listener"
    icon: str = "volume-x"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.tasking.counterplay_services import suppress_listener  # noqa: PLC0415
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        post = _sitting_post(_room_profile(actor))
        if post is None:
            return ActionResult(success=False, message="No one here seems to be listening.")
        try:
            success = suppress_listener(persona, post)
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        if success:
            return ActionResult(success=True, message="They go pale, and quiet.")
        return ActionResult(success=False, message="They don't scare.")


@dataclass
class FlipListenerAction(Action):
    """Seduce this room's sitting listener into a double allegiance."""

    key: str = "flip_listener"
    name: str = "Flip Listener"
    icon: str = "repeat"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.tasking.counterplay_services import flip_listener  # noqa: PLC0415
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        post = _sitting_post(_room_profile(actor))
        if post is None:
            return ActionResult(success=False, message="No one here seems to be listening.")
        try:
            success = flip_listener(persona, post)
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        if success:
            return ActionResult(
                success=True,
                message="Their loyalties quietly change hands. They are yours now.",
            )
        return ActionResult(success=False, message="They resist your charms.")


@dataclass
class PlantRedHerringAction(Action):
    """Queue a false catch on a listener you control.

    Kwargs: post_id, subject_sheet_id, content.
    """

    key: str = "plant_red_herring"
    name: str = "Plant Red Herring"
    icon: str = "fish"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.tasking.counterplay_services import plant_red_herring  # noqa: PLC0415
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415
        from world.tasking.models import ListenerPost  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        post = ListenerPost.objects.filter(pk=kwargs.get("post_id")).first()
        subject = CharacterSheet.objects.filter(pk=kwargs.get("subject_sheet_id")).first()
        content = (kwargs.get("content") or "").strip()
        if post is None or subject is None or not content:
            return ActionResult(success=False, message="Plant what, about whom, where?")
        try:
            plant_red_herring(persona, post, subject_sheet=subject, content=content)
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message="The lie is seeded. Their next collection will carry it.",
        )


@dataclass
class DetectListenersAction(Action):
    """Sweep this room for informants (consentless, defensive)."""

    key: str = "detect_listeners"
    name: str = "Sweep for Listeners"
    icon: str = "scan-eye"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.tasking.counterplay_services import detect_listeners  # noqa: PLC0415
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        room = _room_profile(actor)
        if room is None:
            return ActionResult(success=False, message="You're not in a room.")
        try:
            revealed = detect_listeners(persona, room)
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        if not revealed:
            return ActionResult(success=True, message="You spot nothing out of place.")
        names = ", ".join(r["agent_name"] or "someone" for r in revealed)
        return ActionResult(
            success=True,
            message=f"Someone here is listening: {names}.",
            data={"revealed": revealed},
        )


@dataclass
class ClearRoomListenersAction(Action):
    """Expel listeners from a room you hold authority over."""

    key: str = "clear_room_listeners"
    name: str = "Clear the Room"
    icon: str = "door-open"
    category: str = _CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.tasking.counterplay_services import clear_room_listeners  # noqa: PLC0415
        from world.tasking.exceptions import TaskingError  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return _NO_PERSONA
        room = _room_profile(actor)
        if room is None:
            return ActionResult(success=False, message="You're not in a room.")
        try:
            count = clear_room_listeners(persona, room)
        except TaskingError as exc:
            return ActionResult(success=False, message=exc.user_message)
        if count == 0:
            return ActionResult(success=True, message="No hangers-on to usher out.")
        return ActionResult(success=True, message=f"You clear the room ({count} ushered out).")
