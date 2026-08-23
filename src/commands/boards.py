"""Telnet bulletin board command (#3286).

One ``board`` command, scoped to the LOCATION board in the caller's current
room — the telnet parity surface for a play verb (org boards are read/posted
from the web OrgPage Board tab; the underlying Actions are shared either
way). No business logic here: parse, resolve, call ``action.run()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.boards.models import Board, BoardPost


class CmdBoard(ArxCommand):
    """Read and post to the notice board in your current room.

    Syntax:
        board
        board read <#>
        board post <title>=<body>
        board remove <#>
    """

    key = "board"
    locks = "cmd:all()"
    action = None  # routes to multiple actions

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        args = (self.args or "").strip()
        if not args:
            self._list()
            return
        tokens = args.split(None, 1)
        first = tokens[0].lower()
        rest = tokens[1] if len(tokens) > 1 else ""

        if first == "read":  # noqa: STRING_LITERAL
            self._read(rest.strip())
        elif first == "post":  # noqa: STRING_LITERAL
            self._post(rest)
        elif first == "remove":  # noqa: STRING_LITERAL
            self._remove(rest.strip())
        else:
            msg = "Usage: board [read <#>|post <title>=<body>|remove <#>]"
            raise CommandError(msg)

    # ------------------------------------------------------------------
    # Resolution helpers

    def _current_board(self) -> Board:
        from world.areas.services import get_room_profile  # noqa: PLC0415
        from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
        from world.room_features.services import active_hub_feature  # noqa: PLC0415

        location = self.caller.location
        if location is None:
            msg = "You're not anywhere."
            raise CommandError(msg)
        room_profile = get_room_profile(location)
        hub = active_hub_feature(room_profile)
        if (
            hub is None
            or hub.feature_kind.service_strategy != RoomFeatureServiceStrategy.NOTICE_BOARD
        ):
            msg = "There is no board here."
            raise CommandError(msg)

        from world.boards.services import get_or_create_location_board  # noqa: PLC0415

        return get_or_create_location_board(room_profile)

    def _visible_posts(self, board: Board) -> list[BoardPost]:
        from world.boards.services import (  # noqa: PLC0415
            exclude_blocked_and_muted_board_authors,
            visible_posts_for_board,
        )

        posts = visible_posts_for_board(board)
        account = self.caller.account
        posts = exclude_blocked_and_muted_board_authors(posts, viewer_account=account)
        return list(posts)

    def _resolve_index(self, board: Board, token: str) -> BoardPost:
        if not token.isdigit():
            msg = "Which posting? Use a number from the board listing."
            raise CommandError(msg)
        posts = self._visible_posts(board)
        index = int(token)
        if index < 1 or index > len(posts):
            msg = "No posting with that number."
            raise CommandError(msg)
        return posts[index - 1]

    def _author_display(self, post: BoardPost) -> str:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from world.scenes.persona_display import (  # noqa: PLC0415
            resolve_display_for_viewer,
            viewer_context_for_account,
        )

        account = self.caller.account
        viewer_persona_ids: set[int] = set()
        viewer_sheet_ids: set[int] = set()
        if account is not None:
            viewer_persona_ids, viewer_sheet_ids = viewer_context_for_account(account)
        name, _ = resolve_display_for_viewer(
            post.author_persona,
            viewer_persona_ids=viewer_persona_ids,
            viewer_sheet_ids=viewer_sheet_ids,
            is_staff=is_staff_observer(self.caller),
        )
        return name

    # ------------------------------------------------------------------
    # Subverb handlers

    def _list(self) -> None:
        board = self._current_board()
        posts = self._visible_posts(board)
        if not posts:
            self.msg(f"{board.name} carries no notices right now.")
            return
        lines = [f"|w{board.name}|n"]
        for i, post in enumerate(posts, start=1):
            lines.append(f"  {i}. {post.title} (by {self._author_display(post)})")
        self.msg("\n".join(lines))

    def _read(self, token: str) -> None:
        board = self._current_board()
        post = self._resolve_index(board, token)
        self.msg(f"|w{post.title}|n\nBy {self._author_display(post)}\n\n{post.body}")

    def _post(self, rest: str) -> None:
        from actions.definitions.boards import PostToBoardAction  # noqa: PLC0415

        if "=" not in rest:
            msg = "Usage: board post <title>=<body>"
            raise CommandError(msg)
        title, body = rest.split("=", 1)
        board = self._current_board()
        result = PostToBoardAction().run(
            actor=self.caller,
            board_id=board.pk,
            title=title.strip(),
            body=body.strip(),
        )
        self.msg(result.message)

    def _remove(self, token: str) -> None:
        from actions.definitions.boards import RemoveBoardPostAction  # noqa: PLC0415

        board = self._current_board()
        post = self._resolve_index(board, token)
        result = RemoveBoardPostAction().run(actor=self.caller, post_id=post.pk)
        self.msg(result.message)
