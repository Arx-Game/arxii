"""Telnet command for scene administration.

Thin telnet face of scene-lifecycle Actions:
    ``scene start [name]``               — StartSceneAction
    ``scene finish``                     — FinishSceneAction
    ``scene round <mode> [knobs]``       — SetRoundModeAction
    ``scene succor <ally>``              — SuccorSceneAction (#1744)
    ``scene interpose <ally>``           — InterposeSceneAction (#1316)
    ``scene`` / ``scene status``         — one-line status read-out (no action)
    ``scene <unknown>``                  — usage message

The web path calls the same actions directly. No business logic lives here.
"""

from __future__ import annotations

from commands.command import ArxCommand
from world.scenes.constants import SceneRoundMode

# Maps the user's mode token to the TextChoices value.
_MODE_TOKENS = {
    "open": SceneRoundMode.OPEN,
    "pose_order": SceneRoundMode.POSE_ORDER,
    "strict": SceneRoundMode.STRICT,
}
_LOCK_ON = {"on", "true", "yes", "1"}

_USAGE = (
    "Usage: scene <subcommand>\n"
    "  scene start [name]                — start a scene here\n"
    "  scene finish                      — finish the active scene\n"
    "  scene round [open|pose_order|strict] [quorum=<pct>] [cap=<n>] [lock=on/off]\n"
    "  scene succor <ally>               — shelter an ally from a hazard this round\n"
    "  scene interpose <ally>            — guard an ally from sudden non-combat harm this round\n"
    "  scene / scene status              — show active scene + round status"
)


def _parse_round_args(rest: str) -> dict:
    """Parse ``scene round <mode> [quorum=<n>] [cap=<n>] [lock=on/off]``."""
    tokens = rest.split()
    out: dict = {}
    if tokens and tokens[0].lower() in _MODE_TOKENS:
        out["mode"] = _MODE_TOKENS[tokens[0].lower()].value
        tokens = tokens[1:]
    for tok in tokens:
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        k = k.lower()
        if k == "quorum":  # noqa: STRING_LITERAL
            out["advance_quorum_pct"] = int(v)
        elif k == "cap":  # noqa: STRING_LITERAL
            out["max_actions_per_round"] = int(v)
        elif k == "lock":  # noqa: STRING_LITERAL
            out["per_target_repeat_lock"] = v.lower() in _LOCK_ON
    return out


class CmdScene(ArxCommand):
    """Manage a scene in your current room.

    **Start a scene:**
        ``scene start [name]``

    **Finish the active scene:**
        ``scene finish``

    **Set the round mode:**
        ``scene round [open|pose_order|strict] [quorum=<pct>] [cap=<n>] [lock=on/off]``
        Example: ``scene round strict quorum=70 cap=2 lock=on``

    **Shelter an ally:**
        ``scene succor <ally>`` — shelter an ally from an environmental hazard this round.

    **Guard an ally:**
        ``scene interpose <ally>`` — guard an ally from sudden non-combat harm this round.

    **Show scene status:**
        ``scene`` or ``scene status``
    """

    key = "scene"
    locks = "cmd:all()"
    action = None  # Routing is done in func(); subcommands pick their own action.

    def func(self) -> None:
        """Route the first token of self.args to the appropriate action."""
        raw = (self.args or "").strip()
        first = raw.split()[0].lower() if raw.split() else ""
        rest = raw[len(first) :].strip() if first else ""

        if first in ("", "status"):  # noqa: STRING_LITERAL
            self._handle_status()
        elif first == "start":  # noqa: STRING_LITERAL
            self._handle_start(rest)
        elif first == "finish":  # noqa: STRING_LITERAL
            self._handle_finish()
        elif first == "round":  # noqa: STRING_LITERAL
            self._handle_round(rest)
        elif first == "succor":  # noqa: STRING_LITERAL
            self._handle_succor(rest)
        elif first == "interpose":  # noqa: STRING_LITERAL
            self._handle_interpose(rest)
        else:
            self.msg(_USAGE)

    # ------------------------------------------------------------------
    # Subcommand handlers
    # ------------------------------------------------------------------

    def _handle_start(self, rest: str) -> None:
        """Dispatch StartSceneAction, forwarding an optional scene name."""
        from actions.definitions.scenes import StartSceneAction  # noqa: PLC0415

        kwargs = {}
        name = rest.strip()
        if name:
            kwargs["name"] = name
        result = StartSceneAction().run(actor=self.caller, **kwargs)
        if result.message:
            self.msg(result.message)

    def _handle_finish(self) -> None:
        """Dispatch FinishSceneAction."""
        from actions.definitions.scenes import FinishSceneAction  # noqa: PLC0415

        result = FinishSceneAction().run(actor=self.caller)
        if result.message:
            self.msg(result.message)

    def _handle_round(self, rest: str) -> None:
        """Parse round args and dispatch SetRoundModeAction."""
        from actions.definitions.rounds import SetRoundModeAction  # noqa: PLC0415

        try:
            kwargs = _parse_round_args(rest)
        except ValueError:
            self.msg("Quorum and cap must be numbers.")
            return
        result = SetRoundModeAction().run(actor=self.caller, **kwargs)
        if result.message:
            self.msg(result.message)

    def _handle_succor(self, rest: str) -> None:
        """Dispatch SuccorSceneAction, forwarding the named ally."""
        from actions.definitions.rounds import SuccorSceneAction  # noqa: PLC0415

        ally_name = rest.strip()
        if not ally_name:
            self.msg("Usage: scene succor <ally>.")
            return
        result = SuccorSceneAction().run(actor=self.caller, ally_name=ally_name)
        if result.message:
            self.msg(result.message)

    def _handle_interpose(self, rest: str) -> None:
        """Dispatch InterposeSceneAction, forwarding the named ally."""
        from actions.definitions.rounds import InterposeSceneAction  # noqa: PLC0415

        ally_name = rest.strip()
        if not ally_name:
            self.msg("Usage: scene interpose <ally>.")
            return
        result = InterposeSceneAction().run(actor=self.caller, ally_name=ally_name)
        if result.message:
            self.msg(result.message)

    def _handle_status(self) -> None:
        """Show a one-line status for the active scene + round in this room."""
        from world.scenes.constants import ACTIVE_SCENE_ROUND_STATUSES  # noqa: PLC0415
        from world.scenes.models import Scene, SceneRound  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            self.msg("You are not in a room.")
            return

        scene = Scene.objects.filter(location=room, is_active=True).first()
        if scene is None:
            self.msg("No active scene here.")
            return

        rnd = SceneRound.objects.filter(
            room=room,
            status__in=ACTIVE_SCENE_ROUND_STATUSES,
        ).first()

        if rnd is None:
            self.msg(f"Scene: {scene.name or '(unnamed)'}. No active round.")
        else:
            self.msg(f"Scene: {scene.name or '(unnamed)'}. Round {rnd.round_number} ({rnd.mode}).")
