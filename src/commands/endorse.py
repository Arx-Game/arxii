"""Telnet endorsement commands — thin shells over the endorsement Actions (#1340).

CmdPoses:  ``poses <char>``                           — list visible poses
CmdEndorse: ``endorse pose <char> [#N] resonance=<name> [confirm]``
            ``endorse entry <char> resonance=<name>``
            ``endorse style <char> resonance=<name>``
            ``endorse accept <char> [#N]`` / ``endorse decline <char> [#N]`` (#5327)
            ``endorse withdraw <char> [#N]`` (#5327)

Both commands derive the active scene from the caller's room
(``get_active_scene``), exactly like CmdIntimidate / CmdAccept.
All eligibility and creation logic lives in the actions + service functions.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist

from commands.command import ArxCommand
from commands.exceptions import CommandError

_SUBTYPES = ("pose", "entry", "style", "accept", "decline", "withdraw")  # noqa: STRING_LITERAL


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
        except ObjectDoesNotExist:
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
        endorse pose <char> [#N] [confirm]
        endorse entry <char> resonance=<name>
        endorse style <char> resonance=<name>
        endorse accept <char> [#N]
        endorse decline <char> [#N]
        endorse withdraw <char> [#N]

    On a pose whose author named no resonance, the resonance you pick waits for the author to
    accept it, and pays only if they do. Type the command again with another resonance to
    change your pick. Use ``poses <char>`` to see the numbers.
    A pose whose author reached for a resonance (``pose/reach``) is endorsed for that
    resonance, so you leave ``resonance=`` off: the first invocation shows a preview of the
    pose, and ``confirm`` commits. Scene-entry and style endorsements are one-shot.
    When someone proposes a resonance on your pose, ``endorse accept <char> #N`` lets it pay
    at the weekly settlement and ``endorse decline <char> #N`` turns it down.
    ``endorse withdraw <char> #N`` takes back your own endorsement of <char>'s pose before the
    weekly settlement pays it.

    Examples:
        endorse pose Alice resonance=Embers
        endorse pose Alice #2 resonance=Grief
        endorse accept Ilsa #1
        endorse withdraw Brannoc #1
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
            msg = (
                "Endorse what? Usage: endorse pose/entry/style <char> resonance=<name> | "
                "endorse accept/decline/withdraw <char> [#N]"
            )
            raise CommandError(msg)
        raw_tokens = args.split()
        subtype = raw_tokens[0].lower()
        if subtype not in _SUBTYPES:
            msg = (
                "Specify pose, entry, style, accept, decline or withdraw: "
                "endorse pose/entry/style <char> resonance=<name> | "
                "endorse accept/decline/withdraw <char> [#N]"
            )
            raise CommandError(msg)
        rest: list[str] = list(raw_tokens[1:])
        if subtype == "pose":  # noqa: STRING_LITERAL
            self._endorse_pose(rest)
        elif subtype == "entry":  # noqa: STRING_LITERAL
            self._endorse_entry(rest)
        elif subtype == "style":  # noqa: STRING_LITERAL
            self._endorse_style(rest)
        elif subtype == "withdraw":  # noqa: STRING_LITERAL
            self._withdraw(rest)
        else:
            self._answer_proposal(rest, accept=subtype == "accept")  # noqa: STRING_LITERAL

    # ------------------------------------------------------------------
    # Shared parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pop_resonance(tokens: list[str], *, required: bool = True) -> tuple[list[str], str]:
        """Remove ``resonance=<name>`` token; return (remaining, resonance_name).

        With ``required`` false a missing token returns an empty name: a pose whose author
        reached for a resonance (#5308) is endorsed without naming one, and the action asks
        "Which resonance?" for a pose that did not.
        """
        resonance_name = ""
        remaining = [t for t in tokens if not t.lower().startswith("resonance=")]
        for token in tokens:
            if token.lower().startswith("resonance="):
                resonance_name = token.split("=", 1)[1].strip()
                break
        if not resonance_name and required:
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

        tokens, resonance_name = self._pop_resonance(tokens, required=False)
        resonance = self._resolve_resonance(resonance_name) if resonance_name else None

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
            pose_number=pose_n,
            change_pick=True,
        )
        self._send_result(result)

    def _answer_proposal(self, tokens: list[str], *, accept: bool) -> None:
        """``endorse accept|decline <char> [#N]``: answer the resonance <char> proposed on one of
        the caller's poses. The pick is named by who proposed it and on which pose, so two
        waiting picks are never confused; with no number, a lone pick from <char> is the one."""
        from actions.definitions.endorsements import AnswerPoseProposalAction  # noqa: PLC0415
        from world.magic.services.gain import waiting_picks_from  # noqa: PLC0415

        number = None
        rest = []
        for token in tokens:
            if token.startswith("#") and token[1:].isdigit() and number is None:
                number = int(token[1:])
            else:
                rest.append(token)
        verb = "accept" if accept else "decline"  # noqa: STRING_LITERAL
        char_name = " ".join(rest).strip()
        if not char_name:
            msg = f"Whose proposal? (endorse {verb} <char> [#N])"
            raise CommandError(msg)
        witness_sheet = self._resolve_endorsee(char_name)
        poser_sheet = self.caller.character_sheet
        if poser_sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        waiting = waiting_picks_from(witness_sheet, poser_sheet, self._active_scene())
        if number is not None:
            waiting = [pair for pair in waiting if pair[0] == number]
        if not waiting:
            msg = f"{char_name} has no proposal waiting on that pose of yours."
            raise CommandError(msg)
        if len(waiting) > 1:
            numbers = ", ".join(f"#{n}" for n, _ in waiting)
            msg = f"{char_name} proposed on more than one pose of yours: {numbers}."
            raise CommandError(msg)
        pose_n, pick = waiting[0]
        result = AnswerPoseProposalAction().run(
            actor=self.caller, endorsement=pick, accept=accept, pose_number=pose_n
        )
        self._send_result(result)

    def _withdraw(self, tokens: list[str]) -> None:
        """``endorse withdraw <char> [#N]``: take back the caller's own endorsement of one of
        <char>'s poses (the pose number ``poses <char>`` gives; #1 when none is named), until
        the weekly settlement pays it."""
        from actions.definitions.endorsements import WithdrawPoseEndorsementAction  # noqa: PLC0415
        from world.magic.models import PoseEndorsement  # noqa: PLC0415
        from world.magic.services.gain import get_endorseable_poses_in_scene  # noqa: PLC0415

        number = None
        rest = []
        for token in tokens:
            if token.startswith("#") and token[1:].isdigit() and number is None:
                number = int(token[1:])
            else:
                rest.append(token)
        char_name = " ".join(rest).strip()
        if not char_name:
            msg = "Withdraw your endorsement of whose pose? (endorse withdraw <char> [#N])"
            raise CommandError(msg)
        endorsee_sheet = self._resolve_endorsee(char_name)
        endorser_sheet = self.caller.character_sheet
        if endorser_sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        poses = dict(
            get_endorseable_poses_in_scene(endorser_sheet, endorsee_sheet, self._active_scene())
        )
        mine = {
            row.interaction_id: row
            for row in PoseEndorsement.objects.filter(
                endorser_sheet=endorser_sheet,
                interaction_id__in=[pose.pk for pose in poses.values()],
                settled_at__isnull=True,
            ).select_related("resonance", "interaction__persona")
        }
        picks = [(n, mine[pose.pk]) for n, pose in sorted(poses.items()) if pose.pk in mine]
        if number is not None:
            picks = [pair for pair in picks if pair[0] == number]
        if not picks:
            msg = f"You have no endorsement waiting on that pose of {char_name}."
            raise CommandError(msg)
        if len(picks) > 1:
            numbers = ", ".join(f"#{n}" for n, _ in picks)
            msg = f"You endorsed more than one pose of {char_name}: {numbers}. Name one."
            raise CommandError(msg)
        pose_n, pick = picks[0]
        result = WithdrawPoseEndorsementAction().run(
            actor=self.caller, endorsement=pick, pose_number=pose_n
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
