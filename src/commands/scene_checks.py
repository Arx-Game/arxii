"""Telnet face of scene check invocation (#3295): self-checks, GM calls, proposals.

``check`` (player-facing) covers discovery, self-invocation, answering/declining a
GM's call, and proposing a new catalog entry. ``callcheck`` (GM-gated) covers the
call itself. Both are thin ``action.run()`` dispatchers over
``actions/definitions/scene_checks.py`` -- catalog-only resolution lives there
(``world.checks.catalog_invocation``), never here. ``check find``/``check`` (bare)
is the one read-only exception: a pure catalog browse with no state change and no
permission gate beyond being logged in, so it reads the shared catalog core
directly rather than round-tripping through an Action.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_character_sheet_in_room
from world.scenes.action_constants import DifficultyChoice

_USAGE_CHECK = (
    "Usage: check [find <term>] | check <name> [at <band>] | check propose <name>=<intent>"
    " | check answer <call-id> | check decline <call-id>"
)
_USAGE_CALLCHECK = "Usage: callcheck <name>=<target1>,<target2>,... [at <band>]"
_SUBVERB_FIND = "find"
_SUBVERB_PROPOSE = "propose"
_SUBVERB_ANSWER = "answer"
_SUBVERB_DECLINE = "decline"


def _default_band(raw: str) -> str:
    """Telnet convenience default: an omitted band reads as NORMAL.

    The Action itself never defaults -- ``resolve_band`` in
    ``world.checks.catalog_invocation`` requires an explicit ``DifficultyChoice``
    value from every caller. This is a telnet-grammar-only convenience for the
    documented ``[at <band>]`` optional suffix; the web picker always requires an
    explicit band select.
    """
    band = raw.strip().lower()
    return band or DifficultyChoice.NORMAL


class CmdCheck(ArxCommand):
    """
    Roll a catalog check on yourself, or manage the catalog/proposal pipeline.

    Usage:
      check
      check find <term>
      check <name> [at <band>]
      check propose <name>=<intent>
      check answer <call-id>
      check decline <call-id>

    Bands: trivial, easy, normal, hard, daunting, harrowing. Every check is an
    authored catalog entry -- there is no freeform stat/skill/difficulty roll.
    If the catalog is missing something, propose it instead of inventing it.
    """

    key = "check"
    locks = "cmd:all()"
    help_category = "General"

    def func(self) -> None:
        try:
            raw = (self.args or "").strip()
            tokens = raw.split(maxsplit=1)
            first = tokens[0].lower() if tokens else ""
            rest = tokens[1].strip() if len(tokens) > 1 else ""
            if first in ("", _SUBVERB_FIND):
                self._find(rest)
            elif first == _SUBVERB_PROPOSE:
                self._propose(rest)
            elif first == _SUBVERB_ANSWER:
                self._answer(rest)
            elif first == _SUBVERB_DECLINE:
                self._decline(rest)
            else:
                self._invoke(raw)
        except CommandError as err:
            self.msg(str(err))

    def _find(self, query: str) -> None:
        from world.checks.catalog_invocation import (  # noqa: PLC0415
            render_catalog_listing,
            search_catalog,
        )

        sheet = self.caller.character_sheet
        matches = search_catalog(query, owner_sheet=sheet)
        self.msg(render_catalog_listing(query, matches))

    def _invoke(self, raw: str) -> None:
        from actions.definitions.scene_checks import SceneSelfCheckAction  # noqa: PLC0415

        name_part, _, band_part = raw.rpartition(" at ")
        check_type_ref = (name_part or raw).strip()
        if not check_type_ref:
            raise CommandError(_USAGE_CHECK)

        result = SceneSelfCheckAction().run(
            actor=self.caller,
            check_type_ref=check_type_ref,
            difficulty=_default_band(band_part),
        )
        if result.message:
            self.msg(result.message)

    def _propose(self, rest: str) -> None:
        from actions.definitions.scene_checks import ProposeCheckAction  # noqa: PLC0415

        name, _, intent = rest.partition("=")
        proposed_name = name.strip()
        intent = intent.strip()
        if not proposed_name or not intent:
            raise CommandError(_USAGE_CHECK)

        result = ProposeCheckAction().run(
            actor=self.caller,
            proposed_name=proposed_name,
            intent=intent,
            situation_text=intent,
        )
        if result.message:
            self.msg(result.message)

    def _answer(self, rest: str) -> None:
        from actions.definitions.scene_checks import AnswerCheckCallAction  # noqa: PLC0415

        if not rest.isdigit():
            raise CommandError(_USAGE_CHECK)
        result = AnswerCheckCallAction().run(actor=self.caller, call_id=int(rest))
        if result.message:
            self.msg(result.message)

    def _decline(self, rest: str) -> None:
        from actions.definitions.scene_checks import DeclineCheckCallAction  # noqa: PLC0415

        if not rest.isdigit():
            raise CommandError(_USAGE_CHECK)
        result = DeclineCheckCallAction().run(actor=self.caller, call_id=int(rest))
        if result.message:
            self.msg(result.message)


class CmdCallCheck(ArxCommand):
    """
    Call for a catalog check from one or more co-located characters.

    Usage:
      callcheck <name>=<target1>,<target2>,... [at <band>]

    Requires Junior GM trust or higher. Each named target gets a room-visible
    prompt and answers (or declines) it themselves via `check answer`/`check
    decline`.
    """

    key = "callcheck"
    locks = "cmd:all()"
    help_category = "GM"

    def func(self) -> None:
        try:
            self._call(self.args or "")
        except CommandError as err:
            self.msg(str(err))

    def _call(self, raw: str) -> None:
        from actions.definitions.scene_checks import CallForCheckAction  # noqa: PLC0415

        raw = raw.strip()
        if "=" not in raw:
            raise CommandError(_USAGE_CALLCHECK)
        name_part, _, rest = raw.partition("=")
        check_type_ref = name_part.strip()
        targets_part, _, band_part = rest.rpartition(" at ")
        targets_part = (targets_part or rest).strip()
        if not check_type_ref or not targets_part:
            raise CommandError(_USAGE_CALLCHECK)

        room = self.caller.location
        if room is None:
            msg = "You are not in a room."
            raise CommandError(msg)

        targets: list[Any] = []
        for raw_name in targets_part.split(","):
            target_name = raw_name.strip()
            if not target_name:
                continue
            sheet = resolve_character_sheet_in_room(self.caller, target_name, room=room)
            targets.append(sheet.character)

        result = CallForCheckAction().run(
            actor=self.caller,
            check_type_ref=check_type_ref,
            difficulty=_default_band(band_part),
            targets=targets,
        )
        if result.message:
            self.msg(result.message)
