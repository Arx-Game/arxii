"""Persona telnet command — list faces + wear-face switch (#1347).

A single command renders the caller's owned personas (bare ``persona`` or
``persona list``) or switches the active persona (``persona <name>``). The
switch path dispatches through ``dispatch_player_action`` — the same seam the
web PersonaViewSet uses — routing to the REGISTRY ``set_active_persona`` action.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef


class CmdPersona(DispatchCommand):
    """List or switch your active face.

    Usage:
        persona              — list your personas; marks the active one
        persona list         — same as bare ``persona``
        persona <name>       — switch your active face to the named persona
        wear-face <name>     — alias for persona <name>
    """

    key = "persona"
    aliases = ["wear-face"]
    locks = "cmd:all()"

    _name: str = ""

    def func(self) -> None:
        """Route: bare/list → listing; named → DispatchCommand dispatch."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == "list":  # noqa: STRING_LITERAL
            self._show_listing()
            return
        self._name = raw
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for ``set_active_persona``."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key="set_active_persona")

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve ``self._name`` to a Persona pk scoped to the caller's sheet."""
        from world.scenes.models import Persona  # noqa: PLC0415

        sheet = self.caller.sheet_data
        matches = list(
            Persona.objects.filter(
                character_sheet_id=sheet.pk,
                name__iexact=self._name,
            )
        )
        if not matches:
            available = ", ".join(
                p.name for p in Persona.objects.filter(character_sheet_id=sheet.pk)
            )
            msg = f"No persona named '{self._name}'. Available: {available}."
            raise CommandError(msg)
        if len(matches) > 1:
            names = ", ".join(p.name for p in matches)
            msg = f"Multiple personas match '{self._name}': {names}. Be more specific."
            raise CommandError(msg)
        return {"persona_id": matches[0].pk}

    # -- helpers ------------------------------------------------------------------

    def _show_listing(self) -> None:
        """Render the caller's personas, marking the active one."""
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = self.caller.sheet_data
        active = active_persona_for_sheet(sheet)
        personas = list(sheet.personas.all())
        if not personas:
            self.msg("You have no personas.")
            return
        lines = []
        for persona in personas:
            ptype = persona.get_persona_type_display()
            ftier = persona.get_fame_tier_display()
            label = f"{persona.name} ({ptype}, {ftier})"
            if active is not None and persona.pk == active.pk:
                label += " ◄ active"
            lines.append(label)
        self.msg("\n".join(lines))
