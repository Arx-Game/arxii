"""Player-postable bulletin board REGISTRY actions (#3286).

Thin wrappers over ``world.boards.services`` — permission logic lives there
(``BoardError`` -> failure ``ActionResult(exc.user_message)``, mirroring the
``world.covenants`` shape). Shared by telnet ``CmdBoard`` (``commands/boards.py``)
and the web dispatch seam (OrgPage Board tab, room panel post dialog).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.boards.models import Board, BoardPost


def _actor_persona(actor: ObjectDB):
    """Resolve the actor's active persona, or None (no character sheet)."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    return active_persona_for_sheet(sheet)


def _actor_room_profile(actor: ObjectDB):
    """The RoomProfile for the actor's current location, or None."""
    if actor.location is None:
        return None
    from world.areas.services import get_room_profile  # noqa: PLC0415

    return get_room_profile(actor.location)


def _resolve_target_board(actor: ObjectDB, kwargs: dict[str, Any]) -> tuple[Board | None, str]:
    """Resolve the board a post/edit/remove kwarg set targets.

    Explicit ``board_id`` wins (web: OrgPage Board tab, room panel). Otherwise
    resolve the LOCATION board for the actor's current room, lazily
    get-or-creating it when the room carries an active NOTICE_BOARD feature
    (#3286 Decision — lazy get_or_create at first post).
    """
    from world.boards.models import Board  # noqa: PLC0415
    from world.boards.types import BoardError  # noqa: PLC0415

    board_id = kwargs.get("board_id")
    if board_id is not None:
        board = (
            Board.objects.filter(pk=board_id).select_related("room_profile", "organization").first()
        )
        if board is None:
            return None, "No such board."
        return board, ""

    room_profile = _actor_room_profile(actor)
    if room_profile is None:
        return None, BoardError.NO_BOARD

    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.services import active_hub_feature  # noqa: PLC0415

    hub = active_hub_feature(room_profile)
    if hub is None or hub.feature_kind.service_strategy != RoomFeatureServiceStrategy.NOTICE_BOARD:
        return None, BoardError.NO_BOARD

    from world.boards.services import get_or_create_location_board  # noqa: PLC0415

    return get_or_create_location_board(room_profile), ""


@dataclass
class PostToBoardAction(Action):
    """Pin a new notice to a board (LOCATION or ORG, #3286)."""

    key: str = "post_to_board"
    name: str = "Post to Board"
    icon: str = "pin"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.boards.services import create_board_post  # noqa: PLC0415
        from world.boards.types import BoardError  # noqa: PLC0415

        persona = _actor_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="No active character.")

        board, error = _resolve_target_board(actor, kwargs)
        if board is None:
            return ActionResult(success=False, message=error)

        title = (kwargs.get("title") or "").strip()
        body = (kwargs.get("body") or "").strip()
        if not title or not body:
            return ActionResult(success=False, message="A notice needs both a title and a body.")

        try:
            post = create_board_post(
                board=board,
                author_persona=persona,
                title=title,
                body=body,
                actor_room_profile=_actor_room_profile(actor),
            )
        except BoardError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"You pin '{post.title}' to {board.name}.",
            data={"post_id": post.pk, "board_id": board.pk},
        )


def _resolve_target_post(kwargs: dict[str, Any]) -> tuple[BoardPost | None, str]:
    from world.boards.models import BoardPost  # noqa: PLC0415

    post_id = kwargs.get("post_id")
    if post_id is None:
        return None, "No post specified."
    post = BoardPost.objects.filter(pk=post_id).select_related("board", "author_persona").first()
    if post is None:
        return None, "No such post."
    return post, ""


@dataclass
class EditBoardPostAction(Action):
    """Edit the title/body of your own notice (#3286)."""

    key: str = "edit_board_post"
    name: str = "Edit Board Post"
    icon: str = "pencil"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.boards.services import edit_board_post  # noqa: PLC0415
        from world.boards.types import BoardError  # noqa: PLC0415

        persona = _actor_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="No active character.")

        post, error = _resolve_target_post(kwargs)
        if post is None:
            return ActionResult(success=False, message=error)

        title = (kwargs.get("title") or "").strip()
        body = (kwargs.get("body") or "").strip()
        if not title or not body:
            return ActionResult(success=False, message="A notice needs both a title and a body.")

        try:
            edited = edit_board_post(post=post, editor_persona=persona, title=title, body=body)
        except BoardError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"You revise '{edited.title}'.")


@dataclass
class RemoveBoardPostAction(Action):
    """Remove a notice — own post, org moderator, or staff (#3286)."""

    key: str = "remove_board_post"
    name: str = "Remove Board Post"
    icon: str = "trash"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from world.boards.services import remove_board_post  # noqa: PLC0415
        from world.boards.types import BoardError  # noqa: PLC0415

        persona = _actor_persona(actor)
        if persona is None:
            return ActionResult(success=False, message="No active character.")

        post, error = _resolve_target_post(kwargs)
        if post is None:
            return ActionResult(success=False, message=error)

        try:
            remove_board_post(
                post=post,
                remover_persona=persona,
                actor_room_profile=_actor_room_profile(actor),
                is_staff=is_staff_observer(actor),
            )
        except BoardError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"You take down '{post.title}'.")
