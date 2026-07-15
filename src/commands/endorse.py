"""Telnet endorsement commands — thin shells over the endorsement Actions (#1340).

CmdPoses:  ``poses <char>``                           — list visible poses
CmdEndorse: ``endorse pose <char> [#N] resonance=<name> [confirm]``
            ``endorse entry <char> resonance=<name>``
            ``endorse style <char> resonance=<name>``

Both commands derive the active scene from the caller's room
(``get_active_scene``), exactly like CmdIntimidate / CmdAccept.
All eligibility and creation logic lives in the actions + service functions.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdPoses(ArxCommand):
    """List endorseable poses from a character in the current scene.

    Syntax:
        poses <character name>

    Shows all poses from <character> in the active scene that you are
    allowed to endorse, with their stable absolute position numbers.
    Use these numbers with ``endorse pose <char> #N resonance=<name>``.
    """

    key = "poses"
    locks = "cmd:all()"
    action = None  # listing command — no action

    def func(self) -> None:
        try:
            self._list_poses()
        except CommandError as err:
            self.msg(str(err))

    def _list_poses(self) -> None:
        from world.magic.services.gain import get_endorseable_poses_in_scene  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        char_name = (self.args or "").strip()
        if not char_name:
            msg = "Whose poses? (poses <character name>)"
            raise CommandError(msg)

        target = self.search_or_raise(
            char_name,
            not_found_msg=f"No character named '{char_name}' here.",
        )
        endorsee_sheet = target.character_sheet
        if endorsee_sheet is None:
            msg = f"'{char_name}' has no character sheet."
            raise CommandError(msg)

        endorser_sheet = self.caller.character_sheet
        if endorser_sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)

        scene = get_active_scene(self.caller.location)
        if scene is None:
            msg = "There is no active scene here."
            raise CommandError(msg)

        poses = get_endorseable_poses_in_scene(endorser_sheet, endorsee_sheet, scene)

        if not poses:
            self.msg(f"No endorseable poses from {char_name} visible to you in this scene.")
            return

        try:
            persona_name = endorsee_sheet.primary_persona.name
        except Exception:  # noqa: BLE001
            persona_name = char_name

        _PREVIEW_LEN = 80
        lines = [f"Endorseable poses from {persona_name} in this scene:"]
        for n, interaction in poses:
            content = interaction.content or ""
            preview = content[:_PREVIEW_LEN] + ("..." if len(content) > _PREVIEW_LEN else "")
            lines.append(f"  #{n}: {preview}")
        lines.append("\nUse: endorse pose <char> #N resonance=<name>")
        self.msg("\n".join(lines))


class CmdEndorse(ArxCommand):
    """Endorse a character's pose, scene entry, or style for resonance gain.

    Syntax:
        endorse pose <char> [#N] resonance=<name>
        endorse pose <char> [#N] resonance=<name> confirm
        endorse entry <char> resonance=<name>
        endorse style <char> resonance=<name>

    For pose endorsements, the first invocation shows a preview of the pose.
    Add ``confirm`` to commit. Use ``poses <char>`` to see position numbers.
    Scene-entry and style endorsements are one-shot (no confirmation needed).

    Examples:
        endorse pose Alice resonance=Embers
        endorse pose Alice #2 resonance=Embers confirm
        endorse entry Alice resonance=Embers
        endorse style Alice resonance=Embers
    """

    key = "endorse"
    locks = "cmd:all()"
    action = None  # dispatches to multiple actions

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        args = (self.args or "").strip()
        if not args:
            msg = "Endorse what? Usage: endorse pose/entry/style <char> resonance=<name>"
            raise CommandError(msg)
        raw_tokens = args.split()
        subtype = raw_tokens[0].lower()
        if subtype not in ("pose", "entry", "style"):  # noqa: STRING_LITERAL
            msg = "Specify pose, entry, or style: endorse pose/entry/style <char> resonance=<name>"
            raise CommandError(msg)
        rest: list[str] = list(raw_tokens[1:])
        if subtype == "pose":  # noqa: STRING_LITERAL
            self._endorse_pose(rest)
        elif subtype == "entry":  # noqa: STRING_LITERAL
            self._endorse_entry(rest)
        else:
            self._endorse_style(rest)

    # ------------------------------------------------------------------
    # Shared parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pop_resonance(tokens: list[str]) -> tuple[list[str], str]:
        """Remove ``resonance=<name>`` token; return (remaining, resonance_name)."""
        resonance_name = ""
        remaining = [t for t in tokens if not t.lower().startswith("resonance=")]
        for token in tokens:
            if token.lower().startswith("resonance="):
                resonance_name = token.split("=", 1)[1].strip()
                break
        if not resonance_name:
            msg = "Specify a resonance: resonance=<name>"
            raise CommandError(msg)
        return remaining, resonance_name

    @staticmethod
    def _resolve_resonance(name: str) -> Any:
        from world.magic.models import Resonance  # noqa: PLC0415

        resonance = Resonance.objects.filter(name__iexact=name).first()
        if resonance is None:
            msg = f"No resonance called '{name}'."
            raise CommandError(msg)
        return resonance

    def _resolve_endorsee(self, char_name: str) -> Any:
        target = self.search_or_raise(
            char_name,
            not_found_msg=f"No character named '{char_name}' here.",
        )
        sheet = target.character_sheet
        if sheet is None:
            msg = f"'{char_name}' has no character sheet."
            raise CommandError(msg)
        return sheet

    def _active_scene(self) -> Any:
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        scene = get_active_scene(self.caller.location)
        if scene is None:
            msg = "There is no active scene here."
            raise CommandError(msg)
        return scene

    def _send_result(self, result: Any) -> None:
        if result.success:
            if result.message:
                self.msg(result.message)
        else:
            raise CommandError(result.message or "Action failed")

    # ------------------------------------------------------------------
    # Per-subtype handlers
    # ------------------------------------------------------------------

    def _endorse_pose(self, tokens: list[str]) -> None:
        from actions.definitions.endorsements import PoseEndorseAction  # noqa: PLC0415
        from world.magic.services.gain import get_endorseable_poses_in_scene  # noqa: PLC0415

        confirm = tokens[-1].lower() == "confirm" if tokens else False  # noqa: STRING_LITERAL
        if confirm:
            tokens = tokens[:-1]

        tokens, resonance_name = self._pop_resonance(tokens)
        resonance = self._resolve_resonance(resonance_name)

        # Extract optional #N
        pose_n = 1
        n_idx = None
        for i, token in enumerate(tokens):
            if token.startswith("#") and token[1:].isdigit():
                pose_n = int(token[1:])
                n_idx = i
                break
        if n_idx is not None:
            tokens = [t for i, t in enumerate(tokens) if i != n_idx]

        char_name = " ".join(tokens).strip()
        if not char_name:
            msg = "Endorse whose pose? (endorse pose <char> [#N] resonance=<name>)"
            raise CommandError(msg)

        endorsee_sheet = self._resolve_endorsee(char_name)
        endorser_sheet = self.caller.character_sheet
        if endorser_sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)

        scene = self._active_scene()
        poses = get_endorseable_poses_in_scene(endorser_sheet, endorsee_sheet, scene)
        pose_map = dict(poses)

        if not poses:
            msg = (
                f"No endorseable poses from {char_name} visible to you in this scene. "
                "Use 'poses <char>' to check."
            )
            raise CommandError(msg)
        if pose_n not in pose_map:
            available = ", ".join(f"#{n}" for n, _ in poses)
            msg = f"No visible pose #{pose_n} from {char_name}. Available: {available}"
            raise CommandError(msg)

        result = PoseEndorseAction().run(
            actor=self.caller,
            interaction=pose_map[pose_n],
            resonance=resonance,
            confirm=confirm,
        )
        self._send_result(result)

    def _endorse_entry(self, tokens: list[str]) -> None:
        from actions.definitions.endorsements import SceneEntryEndorseAction  # noqa: PLC0415

        tokens, resonance_name = self._pop_resonance(tokens)
        resonance = self._resolve_resonance(resonance_name)
        char_name = " ".join(tokens).strip()
        if not char_name:
            msg = "Endorse whose scene entry? (endorse entry <char> resonance=<name>)"
            raise CommandError(msg)
        endorsee_sheet = self._resolve_endorsee(char_name)
        scene = self._active_scene()
        result = SceneEntryEndorseAction().run(
            actor=self.caller,
            endorsee_sheet=endorsee_sheet,
            scene=scene,
            resonance=resonance,
        )
        self._send_result(result)

    def _endorse_style(self, tokens: list[str]) -> None:
        from actions.definitions.endorsements import StylePresentationEndorseAction  # noqa: PLC0415

        tokens, resonance_name = self._pop_resonance(tokens)
        resonance = self._resolve_resonance(resonance_name)
        char_name = " ".join(tokens).strip()
        if not char_name:
            msg = "Endorse whose style? (endorse style <char> resonance=<name>)"
            raise CommandError(msg)
        endorsee_sheet = self._resolve_endorsee(char_name)
        scene = self._active_scene()
        result = StylePresentationEndorseAction().run(
            actor=self.caller,
            endorsee_sheet=endorsee_sheet,
            scene=scene,
            resonance=resonance,
        )
        self._send_result(result)
