"""Persona telnet command — list / create / switch faces (#1347, #1127).

A single command renders the caller's owned personas (bare ``persona`` / ``persona list``),
creates a new face (``persona create <name>`` durable, ``persona mask <name>`` temporary), or
switches the active persona (``persona <name>``). The switch path dispatches through
``dispatch_player_action`` — the same seam the web PersonaViewSet uses — routing to the REGISTRY
``set_active_persona`` action; the create paths call the validated ``scenes.services`` creation
directly (the same services the web ``create-established`` / ``create-mask`` actions use).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef


_LIST = "list"
_CREATE = "create"
_MASK = "mask"


class CmdPersona(DispatchCommand):
    """List, create, or switch your faces.

    Usage:
        persona               — list your personas; marks the active one
        persona list          — same as bare ``persona``
        persona create <name> — create a new established (durable) identity
        persona mask <name>   — create a temporary anonymous mask and wear it
        persona <name>        — switch your active face to the named persona
        wear-face <name>      — alias for persona <name>
    """

    key = "persona"
    aliases = ["wear-face"]
    locks = "cmd:all()"

    _name: str = ""

    def func(self) -> None:
        """Route: bare/list → listing; create/mask → service create; named → dispatch switch."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _LIST:
            self._show_listing()
            return
        verb, _, rest = raw.partition(" ")
        if verb.lower() == _CREATE:
            self._create_established(rest.strip())
            return
        if verb.lower() == _MASK:
            self._create_mask(rest.strip())
            return
        self._name = raw
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def _create_established(self, name: str) -> None:
        """``persona create <name>`` — mint a durable ESTABLISHED identity via the service."""
        from world.scenes.services import PersonaCreationError, create_persona  # noqa: PLC0415

        if not name:
            self.msg("Usage: persona create <name>")
            return
        bypass = bool(getattr(self.caller, "is_staff", False))  # noqa: GETATTR_LITERAL
        try:
            persona = create_persona(
                self.caller.sheet_data, name=name, persona_type="established", bypass_cap=bypass
            )
        except PersonaCreationError as exc:
            self.msg(exc.user_message)
            return
        self.msg(
            f"Created established identity '{persona.name}'. Switch with: persona {persona.name}"
        )

    def _create_mask(self, name: str) -> None:
        """``persona mask <name>`` — create a TEMPORARY anonymous mask and wear it."""
        from world.scenes.services import PersonaCreationError, create_mask  # noqa: PLC0415

        if not name:
            self.msg("Usage: persona mask <name>")
            return
        try:
            mask = create_mask(self.caller.sheet_data, name=name)
        except PersonaCreationError as exc:
            self.msg(exc.user_message)
            return
        self.msg(f"You don a mask: '{mask.name}'. You are now presenting as it.")

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
