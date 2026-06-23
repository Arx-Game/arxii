"""Non-combat technique cast command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.scenes.models import Persona


_USAGE = "Usage: attempt <technique> [at <target>]"


class CmdAttempt(ArxCommand):
    """Attempt to cast a non-combat technique.

    Usage:
        attempt <technique> [at <target>]

    Requires an active scene in your location. Consent, hostility, and
    targeting logic live in cast_services — this command is a thin parse/
    dispatch shell.
    """

    key = "attempt"

    _technique_name: str | None = None
    _target_name: str | None = None
    _parsed: bool = False

    def _parse_args(self) -> None:
        if self._parsed:
            return
        raw = (self.args or "").strip()
        if not raw:
            raise CommandError(_USAGE)
        at_index = raw.lower().find(" at ")
        if at_index != -1:
            self._technique_name = raw[:at_index].strip()
            self._target_name = raw[at_index + len(" at ") :].strip()
        else:
            self._technique_name = raw.strip()
            self._target_name = None
        if not self._technique_name:
            raise CommandError(_USAGE)
        self._parsed = True

    def _resolve_technique_id(self) -> int:
        from world.magic.models import CharacterTechnique  # noqa: PLC0415

        name = self._technique_name or ""
        ct = (
            CharacterTechnique.objects.filter(
                character=self.caller.sheet_data,
                technique__name__iexact=name,
            )
            .select_related("technique")
            .first()
        )
        if ct is None:
            msg = f"You don't know a technique called '{name}'."
            raise CommandError(msg)
        return ct.technique_id

    def _resolve_target_persona(self) -> Persona | None:
        if not self._target_name:
            return None
        from world.scenes.models import Persona  # noqa: PLC0415

        persona = Persona.objects.filter(name__iexact=self._target_name).first()
        if persona is None:
            msg = f"No persona named '{self._target_name}' found."
            raise CommandError(msg)
        return persona

    def _dispatch(self) -> str:
        """Core dispatch; raises CommandError or ValidationError on failure."""
        from world.magic.models import Technique  # noqa: PLC0415
        from world.scenes.cast_services import request_technique_cast  # noqa: PLC0415
        from world.scenes.models import Scene  # noqa: PLC0415
        from world.scenes.services import (  # noqa: PLC0415
            MissingPrimaryPersonaError,
            persona_for_character,
        )

        self._parse_args()

        location = self.caller.location
        if location is None:
            msg = "You must be somewhere to cast a technique."
            raise CommandError(msg)

        scene = Scene.objects.filter(location=location, is_active=True).first()
        if scene is None:
            msg = "There is no active scene here."
            raise CommandError(msg)

        try:
            persona = persona_for_character(self.caller)
        except MissingPrimaryPersonaError:
            msg = "You don't have a primary persona."
            raise CommandError(msg)  # noqa: B904

        technique_id = self._resolve_technique_id()
        technique = Technique.objects.get(pk=technique_id)
        target_persona = self._resolve_target_persona()

        cast_result = request_technique_cast(
            scene=scene,
            initiator_persona=persona,
            target_persona=target_persona,
            technique=technique,
        )
        if cast_result.result is not None:
            return "Your technique resolves."
        return "Your cast is pending."

    def func(self) -> None:
        try:
            message = self._dispatch()
        except CommandError as exc:
            self.msg(str(exc))
            return
        except ValidationError as exc:
            messages = exc.messages if hasattr(exc, "messages") else [str(exc)]
            self.msg("; ".join(messages))
            return
        self.msg(message)
