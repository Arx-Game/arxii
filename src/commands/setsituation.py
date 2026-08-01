"""Telnet face of SetSituationAction (#1895) and PlaceChallengeAction (#2865).

Thin command: a JUNIOR-tier-or-higher GM (or staff) caller instantiates a
SituationTemplate into their current room. Delegates to SetSituationAction
via action.run() -- the same seam the web quick-action would reach. The
command lock is ``cmd:all()`` -- real authorization lives entirely in the
Action's ``MinimumGMLevelPrerequisite`` (#2117).

``setsituation find <term>`` (#2127) extends the same command with a
STARTING-tier-or-higher browse mode, mirroring ``gm check find``'s shape
(#2118): delegates to ``FindSituationAction`` instead of instantiating
anything.

``setsituation challenge <template>=<target name>`` (#2865) is the lightweight
sibling: place ONE authored challenge against a named thing in the room. A
subverb of the existing command rather than a new broad command key.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.gm_catalog import FindSituationAction
from actions.definitions.situations import PlaceChallengeAction, SetSituationAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.mechanics.models import ChallengeTemplate, SituationTemplate

_FIND_SUBVERB = "find"
_CHALLENGE_SUBVERB = "challenge"
_EDGE_TOKEN = "edge="  # noqa: S105 -- grammar token, not a secret
_SETBACK_TOKEN = "setback="  # noqa: S105 -- grammar token, not a secret


class CmdSetSituation(ArxCommand):
    """Instantiate authored scenario content in your current room, or browse the catalog.

    Requires JUNIOR-tier GM trust or higher (or staff) to place anything. You must
    be standing in the room. Browsing (``find``) only requires STARTING-tier GM
    trust or higher -- it mutates nothing.

    Usage:
      setsituation <name|id>       -- instantiate <name|id> into this room
      setsituation find <term>     -- browse situations/challenges/kinds matching <term>
      setsituation challenge <name|id>=<target name> [edge=<why>|setback=<why>]
                                   -- place one authored challenge on a named thing

    The optional ``edge=``/``setback=`` shifts the placed challenge one difficulty
    band easier or harder. They are mutually exclusive and the reason is required --
    the band never moves without a stated why.
    """

    key = "setsituation"
    aliases: list[str] = []
    locks = "cmd:all()"
    help_category = "Building"
    action = SetSituationAction()
    find_action = FindSituationAction()
    challenge_action = PlaceChallengeAction()

    def _execute(self) -> None:
        raw = (self.args or "").strip()
        tokens = raw.split(maxsplit=1)
        subverb = tokens[0].lower() if tokens else ""
        remainder = tokens[1].strip() if len(tokens) > 1 else ""

        if subverb == _FIND_SUBVERB:
            result = self.find_action.run(actor=self.caller, query=remainder)
            if result.message:
                self.msg(result.message)
            return
        if subverb == _CHALLENGE_SUBVERB:
            self._place_challenge(remainder)
            return
        super()._execute()

    def _place_challenge(self, remainder: str) -> None:
        """Parse ``<name|id>=<target name> [edge=…|setback=…]`` and dispatch."""
        if "=" not in remainder:
            msg = "Usage: setsituation challenge <name|id>=<target name>"
            raise CommandError(msg)

        template_ref, _, rest = remainder.partition("=")
        target_name, edge_reason, setback_reason = _split_shift_tokens(rest.strip())

        template = self.resolve_by_name_or_id(
            ChallengeTemplate,
            template_ref.strip(),
            not_found_msg="No such challenge template.",
        )
        result = self.challenge_action.run(
            actor=self.caller,
            challenge_template_id=template.pk,
            target_object_name=target_name,
            edge_reason=edge_reason,
            setback_reason=setback_reason,
        )
        if result.message:
            self.msg(result.message)

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse ``<name|id>`` into SetSituationAction kwargs."""
        raw = (self.args or "").strip()
        if not raw:
            msg = "Set which situation? (setsituation <name|id>)"
            raise CommandError(msg)

        template = self.resolve_by_name_or_id(
            SituationTemplate,
            raw,
            not_found_msg="No such situation template.",
        )
        return {"situation_template_id": template.pk}


def _split_shift_tokens(text: str) -> tuple[str, str, str]:
    """Split ``<target name> [edge=…|setback=…]`` into its three parts.

    The target name runs free up to the first ``edge=``/``setback=`` token, so a
    multi-word name ("the barred gate") needs no quoting. Both tokens present is
    left for the Action to refuse -- one refusal message, not two.
    """
    lowered = text.lower()
    cut = len(text)
    for token in (_EDGE_TOKEN, _SETBACK_TOKEN):
        index = lowered.find(token)
        if index != -1:
            cut = min(cut, index)

    target_name = text[:cut].strip()
    edge_reason = _reason_after(text[cut:], _EDGE_TOKEN)
    setback_reason = _reason_after(text[cut:], _SETBACK_TOKEN)
    return target_name, edge_reason, setback_reason


def _reason_after(text: str, token: str) -> str:
    """Return the free text following *token*, up to the other shift token."""
    lowered = text.lower()
    index = lowered.find(token)
    if index == -1:
        return ""
    start = index + len(token)
    other = _SETBACK_TOKEN if token == _EDGE_TOKEN else _EDGE_TOKEN
    end = lowered.find(other, start)
    return (text[start:] if end == -1 else text[start:end]).strip()
