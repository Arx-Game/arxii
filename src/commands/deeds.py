"""Telnet ``deed`` command — spread a tale or save a deed story (#1503).

A single namespace command dispatches to two SCENE_ADAPTIVE Actions:
``SpreadTaleAction`` (``deed spread ...``) and ``SaveDeedStoryAction``
(``deed story ...``). Eligibility, scene participation, and deed awareness
all live in the Actions, just like the web endpoints.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# Subverb -> registry action key. Kept in a single mapping so the grammar tokens
# are declared once; individual comparisons still need noqa because they parse the
# player's bare subverb against the command's grammar.
_SUBVERBS: dict[str, str] = {
    "spread": "spread_tale",
    "story": "save_deed_story",
}


class CmdDeed(DispatchCommand):
    """Record or spread word of deeds your persona knows.

    Usage:
        deed spread <deed name or id>
            [effort=<low|medium|high>]
            [specialization=<name or id>]
            [pose=<in-character text>]
        deed story <deed name or id>=<written account>

    Examples:
        deed spread The Sinking of the Argent
        deed spread 47 effort=high pose=Singing a mournful ballad.
        deed story The Sinking of the Argent=I was there when she went down.
    """

    key = "deed"
    locks = "cmd:all()"

    _sub_verb: str = ""
    _rest: str = ""

    # Tokens that begin an optional keyword argument for ``deed spread``.
    _SPREAD_KWARG_RE = re.compile(
        r"\s+(?=effort\s*=|specialization\s*=|spec\s*=|pose\s*=)",
        flags=re.IGNORECASE,
    )

    def func(self) -> None:
        """Parse sub-verb, then hand off to DispatchCommand for dispatch."""
        raw = (self.args or "").strip()
        if not raw:
            msg = self._usage()
            raise CommandError(msg)

        head, _, tail = raw.partition(" ")
        self._sub_verb = head.lower()
        self._rest = tail.strip()
        if self._sub_verb not in _SUBVERBS:
            msg = self._usage()
            raise CommandError(msg)

        super().func()

    def resolve_action_ref(self) -> ActionRef:
        """Return the SCENE_ADAPTIVE ref for the parsed sub-verb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(
            backend=ActionBackend.SCENE_ADAPTIVE,
            registry_key=_SUBVERBS[self._sub_verb],
        )

    def resolve_action_args(self) -> dict[str, Any]:
        """Build kwargs for whichever Action the sub-verb selected."""
        if self._sub_verb == "spread":  # noqa: STRING_LITERAL
            return self._resolve_spread_args()
        return self._resolve_story_args()

    # -- spread ----------------------------------------------------------------

    def _resolve_spread_args(self) -> dict[str, Any]:
        """Parse ``deed spread <deed> [effort=...] [specialization=...] [pose=...]``."""
        if not self._rest:
            msg = "Spread what deed? (deed spread <deed name or id>)"
            raise CommandError(msg)

        parts = self._SPREAD_KWARG_RE.split(self._rest)
        deed_value = parts[0].strip()
        if not deed_value:
            msg = "Spread what deed? (deed spread <deed name or id>)"
            raise CommandError(msg)

        effort = "medium"
        specialization_id: int | None = None
        pose_text = ""

        for token in parts[1:]:
            key, sep, value = token.partition("=")
            if not sep:
                continue
            key = key.strip().lower()
            value = value.strip()
            if key in ("specialization", "spec"):  # noqa: STRING_LITERAL
                specialization_id = self._resolve_specialization(value).pk
            elif key == "effort":  # noqa: STRING_LITERAL
                effort = self._normalize_effort(value)
            elif key == "pose":  # noqa: STRING_LITERAL
                pose_text = value

        persona = self._active_persona()
        deed = self._resolve_deed(persona, deed_value)
        scene_id = self._current_scene_id()

        return {
            "persona_id": persona.pk,
            "scene_id": scene_id,
            "deed_id": deed.pk,
            "effort_level": effort,
            "specialization_id": specialization_id,
            "pose_text": pose_text,
        }

    # -- story -----------------------------------------------------------------

    def _resolve_story_args(self) -> dict[str, Any]:
        """Parse ``deed story <deed>=<text>``."""
        if "=" not in self._rest:
            msg = "Record a story how? (deed story <deed name or id>=<written account>)"
            raise CommandError(msg)
        deed_value, _, text = self._rest.partition("=")
        deed_value = deed_value.strip()
        text = text.strip()
        if not deed_value:
            msg = "Record a story about which deed?"
            raise CommandError(msg)
        if not text:
            msg = "You must write something."
            raise CommandError(msg)

        persona = self._active_persona()
        deed = self._resolve_deed(persona, deed_value)

        return {
            "persona_id": persona.pk,
            "deed_id": deed.pk,
            "text": text,
        }

    # -- helpers ---------------------------------------------------------------

    def _active_persona(self) -> Any:
        """Return the caller's active/worn persona."""
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = self.caller.sheet_data
        persona = active_persona_for_sheet(sheet)
        if persona is None:
            msg = "You have no active persona."
            raise CommandError(msg)
        return persona

    def _current_scene_id(self) -> int:
        """Return the active scene for the caller's current location."""
        from world.scenes.interaction_services import _get_active_scene  # noqa: PLC0415

        scene = _get_active_scene(self.caller.location)
        if scene is None:
            msg = "There is no active scene here."
            raise CommandError(msg)
        account = self.caller.account
        if account is None or not scene.participants.filter(pk=account.pk).exists():
            msg = "You are not a participant in this scene."
            raise CommandError(msg)
        return scene.pk

    def _resolve_deed(self, persona: Any, value: str) -> Any:
        """Resolve a deed the persona can spread, by name or id."""
        from world.societies.spread_services import get_spreadable_deeds  # noqa: PLC0415

        qs = get_spreadable_deeds(persona)
        if value.isdigit():
            deed = qs.filter(pk=int(value)).first()
        else:
            deed = qs.filter(title__iexact=value).first()
        if deed is None:
            msg = f"You don't know a deed matching '{value}'."
            raise CommandError(msg)
        return deed

    def _resolve_specialization(self, value: str) -> Any:
        """Resolve a Performance specialization usable for spreading tales."""
        from world.societies.spread_services import get_spread_specializations  # noqa: PLC0415

        qs = get_spread_specializations()
        if value.isdigit():
            spec = qs.filter(pk=int(value)).first()
        else:
            spec = qs.filter(name__iexact=value).first()
        if spec is None:
            msg = f"No usable specialization matching '{value}'."
            raise CommandError(msg)
        return spec

    @staticmethod
    def _normalize_effort(value: str) -> str:
        """Return a lowercase effort level the action accepts."""
        clean = value.lower()
        if clean not in ("low", "medium", "high"):
            msg = "Effort must be low, medium, or high."
            raise CommandError(msg)
        return clean

    def _usage(self) -> str:
        return "Usage: deed spread <deed> [...] | deed story <deed>=<text>"
