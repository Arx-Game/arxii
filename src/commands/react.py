"""Telnet reaction/favorite namespace command (#1341).

One ``react`` command routes a leading subverb:

- ``react favorite <char> #N``        -> ``ToggleFavoriteAction``
- ``react emoji <char> #N <emoji>``   -> ``ToggleReactionAction``
- ``react <kind> <char> #N [<choice>]`` -> ``ReactToWindowAction``
  (the subverb IS the kind: ``react kudos <char> #1``, ``react entrance <char> #1 <resonance>``)
- bare ``react``                        -> status hub of open reactable events in the scene

``<char> #N`` resolves via the existing ``get_endorseable_poses_in_scene``
(stable per-author, visibility-filtered numbering) -- the same scheme ``endorse``
uses. The active scene is derived from the caller's room (``get_active_scene``).
No business logic in the command: parse, resolve the pose, run the Action.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

# Entrance is the only window kind whose choice is a resonance; the others
# (kudos) use the slug the Action auto-defaults. ``react entrance`` accepts the
# resonance *name* (player-facing) and the command resolves it to ``str(pk)``
# before passing ``choice=`` to ``ReactToWindowAction``.
_ENTRANCE_KIND = "entrance"
# A choice token present beyond the character name marks an explicit choice.
_EXPLICIT_CHOICE_TOKEN_THRESHOLD = 2


class CmdReact(ArxCommand):
    """React to a pose, or favorite one.

    Syntax:
        react favorite <char> #N
        react emoji <char> #N <emoji>
        react kudos <char> #N
        react entrance <char> #N <resonance>
        react

    Use ``poses <char>`` to see position numbers. Bare ``react`` shows open
    reactable events in the current scene.
    """

    key = "react"
    locks = "cmd:all()"
    action = None  # routes to multiple actions

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    # ------------------------------------------------------------------

    def _dispatch(self) -> None:
        args = (self.args or "").strip()
        if not args:
            self._hub()
            return
        tokens: list[str] = list(args.split())
        first = tokens[0].lower()
        rest = tokens[1:]

        if first == "favorite":  # noqa: STRING_LITERAL
            self._favorite(rest)
        elif first == "emoji":  # noqa: STRING_LITERAL
            self._emoji(rest)
        else:
            # The subverb is the kind.
            self._window(kind=first, tokens=rest)

    # ------------------------------------------------------------------
    # Shared resolution

    def _actor_sheet(self) -> Any:
        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        return sheet

    def _active_scene(self) -> Any:
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        scene = get_active_scene(getattr(self.caller, "location", None))  # noqa: GETATTR_LITERAL
        if scene is None:
            msg = "There is no active scene here."
            raise CommandError(msg)
        return scene

    def _resolve_pose(self, char_name: str, pose_n: int, scene: Any) -> Any:
        """Return the Nth visible pose by char_name, or raise CommandError."""
        from world.magic.services.gain import get_endorseable_poses_in_scene  # noqa: PLC0415

        target = self.search_or_raise(
            char_name, not_found_msg=f"No character named '{char_name}' here."
        )
        endorsee_sheet = target.character_sheet
        if endorsee_sheet is None:
            msg = f"'{char_name}' has no character sheet."
            raise CommandError(msg)
        actor_sheet = self._actor_sheet()
        poses = get_endorseable_poses_in_scene(actor_sheet, endorsee_sheet, scene)
        pose_map = dict(poses)
        if not poses:
            msg = f"No visible poses from {char_name} in this scene. Use 'poses {char_name}'."
            raise CommandError(msg)
        if pose_n not in pose_map:
            available = ", ".join(f"#{n}" for n, _ in poses)
            msg = f"No visible pose #{pose_n} from {char_name}. Available: {available}"
            raise CommandError(msg)
        return pose_map[pose_n]

    @staticmethod
    def _pop_pose_n(tokens: list[str]) -> tuple[list[str], int]:
        """Extract the ``#N`` token; return (remaining, n). Defaults to 1."""
        for i, token in enumerate(tokens):
            if token.startswith("#") and token[1:].isdigit():
                return tokens[:i] + tokens[i + 1 :], int(token[1:])
        return tokens, 1

    @staticmethod
    def _resolve_resonance(name: str) -> Any:
        """Resolve a resonance *name* (player-facing) to its Resonance row.

        Entrance reactions take ``str(resonance.pk)`` as the choice slug; the
        command accepts the name players know and resolves it here -- mirroring
        ``CmdEndorse._resolve_resonance``.
        """
        from world.magic.models import Resonance  # noqa: PLC0415

        resonance = Resonance.objects.filter(name__iexact=name).first()
        if resonance is None:
            msg = f"No resonance called '{name}'."
            raise CommandError(msg)
        return resonance

    def _send_result(self, result: Any) -> None:
        if not result.success:
            raise CommandError(result.message or "Action failed")
        if result.message:
            self.msg(result.message)

    # ------------------------------------------------------------------
    # Subverbs

    def _favorite(self, tokens: list[str]) -> None:
        from actions.definitions.scene_reactions import ToggleFavoriteAction  # noqa: PLC0415

        tokens, pose_n = self._pop_pose_n(tokens)
        char_name = " ".join(tokens).strip()
        if not char_name:
            msg = "Favorite whose pose? (react favorite <char> #N)"
            raise CommandError(msg)
        scene = self._active_scene()
        interaction = self._resolve_pose(char_name, pose_n, scene)
        result = ToggleFavoriteAction().run(actor=self.caller, interaction=interaction)
        self._send_result(result)

    def _emoji(self, tokens: list[str]) -> None:
        from actions.definitions.scene_reactions import ToggleReactionAction  # noqa: PLC0415

        tokens, pose_n = self._pop_pose_n(tokens)
        if not tokens:
            msg = "React to whose pose? (react emoji <char> #N <emoji>)"
            raise CommandError(msg)
        emoji = tokens[-1]
        char_name = " ".join(tokens[:-1]).strip()
        if not char_name:
            msg = "React to whose pose? (react emoji <char> #N <emoji>)"
            raise CommandError(msg)
        scene = self._active_scene()
        interaction = self._resolve_pose(char_name, pose_n, scene)
        result = ToggleReactionAction().run(actor=self.caller, interaction=interaction, emoji=emoji)
        self._send_result(result)

    def _window(self, *, kind: str, tokens: list[str]) -> None:
        from actions.definitions.scene_reactions import ReactToWindowAction  # noqa: PLC0415
        from world.scenes.constants import ReactionWindowKind  # noqa: PLC0415

        valid_kinds = {k for k, _ in ReactionWindowKind.choices}
        if kind not in valid_kinds:
            msg = f"Unknown reaction '{kind}'. Try: react favorite|emoji|kudos|entrance ..."
            raise CommandError(msg)
        tokens, pose_n = self._pop_pose_n(tokens)
        if not tokens:
            msg = f"React to whose pose? (react {kind} <char> #N [<choice>])"
            raise CommandError(msg)
        # The last token may be an explicit choice (e.g. entrance <char> #N <resonance>);
        # for single-choice lazy kinds (kudos) the Action defaults the choice, so the
        # caller may omit it.
        if len(tokens) >= _EXPLICIT_CHOICE_TOKEN_THRESHOLD:
            choice = tokens[-1]
            char_name = " ".join(tokens[:-1]).strip()
        else:
            choice = None
            char_name = tokens[0]
        # Entrance is the only kind whose choice is a resonance name; resolve
        # it to the slug (str(pk)) the service expects. Other kinds pass the
        # token through; the Action/service validates it.
        if kind == _ENTRANCE_KIND and choice is not None:  # noqa: STRING_LITERAL
            resonance = self._resolve_resonance(choice)
            choice = str(resonance.pk)
        scene = self._active_scene()
        interaction = self._resolve_pose(char_name, pose_n, scene)
        result = ReactToWindowAction().run(
            actor=self.caller, interaction=interaction, kind=kind, choice=choice
        )
        self._send_result(result)

    # ------------------------------------------------------------------
    # Bare-`react` hub

    def _hub(self) -> None:
        from world.scenes.reaction_models import ReactionWindow  # noqa: PLC0415
        from world.scenes.reaction_services import get_reaction_kind  # noqa: PLC0415

        scene = self._active_scene()
        windows = list(
            ReactionWindow.objects.filter(scene=scene, settled_at__isnull=True)
            .select_related("interaction__persona")
            .order_by("-opened_at")
        )
        if not windows:
            self.msg("No open reactable events in this scene.")
            return
        lines = ["Open reactable events in this scene:"]
        for w in windows:
            try:
                chips = ", ".join(c.label for c in get_reaction_kind(w.kind).choices_for(w))
            except Exception:  # noqa: BLE001
                chips = "(unknown)"
            pose_preview = (w.interaction.content or "")[:40]
            lines.append(f"  #{w.kind} {pose_preview}...  choices: {chips}")
        lines.append("\nUse: react <kind> <char> #N <choice>")
        self.msg("\n".join(lines))
