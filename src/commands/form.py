"""Form (alternate self) telnet namespace command (#1111 slice 4).

A single ``form`` command lists the caller's alternate selves (bare ``form`` or
``form list``), shifts into one (``form shift <name|id>``), or reverts to the
true self (``form revert``). The shift/revert paths dispatch through
``dispatch_player_action`` — the same seam the web form dispatcher uses —
routing to the REGISTRY ``shift_form`` / ``revert_form`` actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef


class CmdForm(DispatchCommand):
    """List, shift into, or revert your alternate selves.

    Usage:
        form                       — list your alternate selves; marks the active one
        form list                  — same as bare ``form``
        form shift <name|id>       — assume the named alternate self
        form revert                — revert to your true self
    """

    key = "form"
    aliases = []
    locks = "cmd:all()"

    _name: str = ""
    _registry_key: str = ""

    def func(self) -> None:
        """Route: bare/list → hub; shift/revert → DispatchCommand dispatch."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == "list":  # noqa: STRING_LITERAL
            self._show_hub()
            return

        tokens = raw.split()
        subverb = tokens[0].lower()
        rest = tokens[1:]

        if subverb == "shift":  # noqa: STRING_LITERAL
            if not rest:
                msg = "Shift into which alternate self? Usage: form shift <name|id>."
                raise CommandError(msg)
            self._name = " ".join(rest)
            self._registry_key = "shift_form"
            super().func()
            return

        if subverb == "revert":  # noqa: STRING_LITERAL
            self._registry_key = "revert_form"
            super().func()
            return

        msg = "Usage: form [list|shift <name|id>|revert]."
        raise CommandError(msg)

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the resolved subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=self._registry_key)

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve ``self._name`` to an owned AlternateSelf pk for shift."""
        if self._registry_key == "revert_form":  # noqa: STRING_LITERAL
            return {}

        from world.forms.models import AlternateSelf  # noqa: PLC0415

        sheet = self.caller.sheet_data
        matches = list(
            AlternateSelf.objects.filter(
                character_id=sheet.pk,
                display_name__iexact=self._name,
            )
        )
        if not matches and self._name.isdigit():
            instance = AlternateSelf.objects.filter(
                character_id=sheet.pk,
                pk=int(self._name),
            ).first()
            if instance is not None:
                matches = [instance]

        if not matches:
            available = ", ".join(
                a.display_name
                for a in AlternateSelf.objects.filter(character_id=sheet.pk)
                if a.display_name
            )
            msg = f"No alternate self named '{self._name}'. Available: {available}."
            raise CommandError(msg)
        if len(matches) > 1:
            names = ", ".join(a.display_name for a in matches)
            msg = f"Multiple alternate selves match '{self._name}': {names}. Be more specific."
            raise CommandError(msg)
        return {"alternate_self_id": matches[0].pk}

    # -- helpers ------------------------------------------------------------------

    def _show_hub(self) -> None:
        """Render the caller's active alternate self + available list."""
        from world.forms.models import AlternateSelf  # noqa: PLC0415

        sheet = self.caller.sheet_data
        lines: list[str] = [self._active_self_line(sheet)]

        alts = list(AlternateSelf.objects.filter(character_id=sheet.pk).order_by("display_name"))
        if alts:
            lines.append("Available alternate selves:")
            lines.extend(f"  {self._alt_label(alt)}" for alt in alts)
        else:
            lines.append("You have no alternate selves.")

        if not sheet.in_control:
            lines.append("You are not in control — revert is blocked.")

        self.msg("\n".join(lines))

    @staticmethod
    def _active_self_line(sheet: Any) -> str:
        """One line naming the active alternate self, or the true self."""
        from world.forms.models import ActiveAlternateSelf  # noqa: PLC0415

        active = (
            ActiveAlternateSelf.objects.filter(character=sheet)
            .select_related("alternate_self")
            .first()
        )
        if active is not None and active.alternate_self is not None:
            name = active.alternate_self.display_name or "an alternate self"
            return f"You are in {name}."
        return "You are in your true self."

    @staticmethod
    def _alt_label(alt: Any) -> str:
        """Display label for one alternate self, annotated with its facets."""
        label = alt.display_name or "unnamed"
        facets: list[str] = []
        if alt.persona is not None:
            facets.append(f"persona {alt.persona.name}")
        if alt.form_id is not None:
            facets.append("form")
        if alt.combat_profile_id is not None:
            facets.append("combat profile")
        if facets:
            label += f" ({', '.join(facets)})"
        return label
