"""Persona telnet command — list / create / switch faces (#1347, #1127).

A single command renders the caller's owned personas (bare ``persona`` / ``persona list``),
creates a new face (``persona create <name>`` durable, ``persona mask <name>`` temporary), or
switches the active persona (``persona <name>``). The switch path dispatches through
``dispatch_player_action`` — the same seam the web PersonaViewSet uses — routing to the REGISTRY
``set_active_persona`` action; the create paths call the validated ``scenes.services`` creation
directly (the same services the web ``create-established`` / ``create-mask`` actions use).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef


_LIST = "list"
_CREATE = "create"
_MASK = "mask"
_PROFILE = "profile"
_GUISE_FIELDS = ("concept", "quote", "personality", "background")
_GUISE_KEY_RE = re.compile(r"\b(concept|quote|personality|background)=")


class CmdPersona(DispatchCommand):
    """List, create, or switch your faces.

    Usage:
        persona               — list your personas; marks the active one
        persona list          — same as bare ``persona``
        persona create <name> — create a new established (durable) identity
        persona mask <name>   — create a temporary anonymous mask and wear it
        persona profile <name> [concept=… quote=… personality=… background=…]
                              — view or author a cover identity's own (fabricated) bio
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
        if verb.lower() == _PROFILE:
            self._handle_profile(rest.strip())
            return
        self._name = raw
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def _create_established(self, name: str) -> None:
        """``persona create <name>`` — mint a durable ESTABLISHED identity via the service."""
        from world.scenes.services import PersonaCreationError, create_persona  # noqa: PLC0415

        if not name:
            self.msg("Usage: persona create <name>")
            return
        # is_staff lives on the Account, not the puppeted Character — the old
        # getattr(self.caller, ...) read was always False, so the staff cap
        # bypass never actually worked (silent-fail audit, tranche 2).
        account = self.caller.account
        bypass = bool(account and account.is_staff)
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

    def _handle_profile(self, rest: str) -> None:
        """``persona profile <name> [field=value ...]`` — view or author a guise bio (#1270).

        A cover identity carries its own fabricated bio so its *absence* doesn't out it as fake.
        With no fields, shows the named persona's current guise bio; with ``concept=`` /
        ``quote=`` / ``personality=`` / ``background=`` (free text to the next key), authors them.
        """
        if not rest:
            self.msg(
                "Usage: persona profile <name> "
                "[concept=... quote=... personality=... background=...]"
            )
            return
        match = _GUISE_KEY_RE.search(rest)
        if match is None:
            name, fields = rest, {}
        else:
            name = rest[: match.start()].strip()
            fields = self._parse_guise_fields(rest[match.start() :])
        if not name:
            self.msg("Usage: persona profile <name> [field=value ...]")
            return
        persona = self._resolve_own_persona(name)
        if persona is None:
            return
        if not fields:
            self._show_guise(persona)
            return
        from world.scenes.services import GuiseProfileError, set_persona_profile  # noqa: PLC0415

        try:
            set_persona_profile(persona, **fields)
        except GuiseProfileError as exc:
            self.msg(exc.user_message)
            return
        self.msg(f"Updated the guise bio for '{persona.name}': {', '.join(fields)}.")

    @staticmethod
    def _parse_guise_fields(text: str) -> dict[str, str]:
        """Split ``field=value …`` where each value runs free until the next known key."""
        parts = _GUISE_KEY_RE.split(text)
        # parts = ['', key1, val1, key2, val2, …] — pre-first-key chunk is empty (we sliced there).
        fields: dict[str, str] = {}
        for index in range(1, len(parts) - 1, 2):
            fields[parts[index]] = parts[index + 1].strip()
        return fields

    def _resolve_own_persona(self, name: str) -> Any:
        """Resolve a name to one of the caller's own personas, or None (already messaged)."""
        from world.scenes.models import Persona  # noqa: PLC0415

        sheet = self.caller.sheet_data
        matches = list(Persona.objects.filter(character_sheet_id=sheet.pk, name__iexact=name))
        if not matches:
            available = ", ".join(
                p.name for p in Persona.objects.filter(character_sheet_id=sheet.pk)
            )
            self.msg(f"No persona named '{name}'. Available: {available}.")
            return None
        if len(matches) > 1:
            self.msg(f"Multiple personas match '{name}'. Be more specific.")
            return None
        return matches[0]

    def _show_guise(self, persona: Any) -> None:
        """Render a persona's current guise bio (or a prompt to author one)."""
        profile = persona.profile
        if profile is None:
            self.msg(
                f"'{persona.name}' has no guise bio yet. Author one with: "
                f"persona profile {persona.name} concept=..."
            )
            return
        lines = [f"|wGuise bio for {persona.name}:|n"]
        for field_name in _GUISE_FIELDS:
            value = getattr(profile, field_name)
            lines.append(f"  {field_name.title()}: {value or '(unset)'}")
        self.msg("\n".join(lines))

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
