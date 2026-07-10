"""Motif style-binding telnet command — the ``motif`` namespace (#2030).

A single command routes the three player-facing motif style-binding verbs
through the shared ``dispatch_player_action`` seam. No game logic lives here;
the command only parses telnet text and resolves objects before dispatching
to the REGISTRY actions in ``actions/definitions/motif_style.py``. Claim
validation (unclaimed resonance, per-resonance binding cap) stays in the
service layer — the command never duplicates it.

The verbs live under the ``motif`` namespace to avoid broad one-word key
collisions with exits/channels/aliases (same reasoning as ``CmdSignature`` /
``CmdSanctum``). Style/resonance lookup uses exact-name matching (case
insensitive) because Evennia's partial/fuzzy search is broken on PostgreSQL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# Subverb name constants (used in comparisons — avoids STRING_LITERAL lint).
_SUBVERB_LIST = "list"
_SUBVERB_BINDSTYLE = "bindstyle"
_SUBVERB_UNBINDSTYLE = "unbindstyle"

# subverb → registry action key.
_SUBVERBS: dict[str, str] = {
    _SUBVERB_BINDSTYLE: "bind_motif_style",
    _SUBVERB_UNBINDSTYLE: "unbind_motif_style",
    _SUBVERB_LIST: "list_motif_styles",
}


class CmdMotif(DispatchCommand):
    """Bind or unbind a Style to one of your claimed resonances.

    Usage:
        motif                                    — list your style bindings
        motif list                               — (same)
        motif bindstyle <style>=<resonance>      — bind a style to a resonance
        motif unbindstyle <style>                — remove a style binding
    """

    key = "motif"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``motif`` / ``motif list`` shows bindings."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _SUBVERB_LIST:
            self._subverb = _SUBVERB_LIST
            self._rest = ""
            super().func()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(_SUBVERBS)
            self.msg(f"Unknown motif action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        if self._subverb == _SUBVERB_LIST:
            return {}
        if self._subverb == _SUBVERB_BINDSTYLE:
            return self._args_bindstyle()
        if self._subverb == _SUBVERB_UNBINDSTYLE:
            return self._args_unbindstyle()
        return {}  # unreachable — func() gates on _SUBVERBS

    # -- resolution helpers -----------------------------------------------

    def _require_style(self, name: str) -> Any:
        """Resolve *name* to a Style (iexact), or raise CommandError."""
        from world.items.models import Style  # noqa: PLC0415

        style = Style.objects.filter(name__iexact=name).first()
        if style is None:
            msg = f"There is no style called '{name}'."
            raise CommandError(msg)
        return style

    def _require_resonance(self, name: str) -> Any:
        """Resolve *name* to a Resonance (iexact), or raise CommandError."""
        from world.magic.models import Resonance  # noqa: PLC0415

        resonance = Resonance.objects.filter(name__iexact=name).first()
        if resonance is None:
            msg = f"There is no resonance called '{name}'."
            raise CommandError(msg)
        return resonance

    # -- per-subverb argument resolvers ------------------------------------

    def _args_bindstyle(self) -> dict[str, Any]:
        """Resolve bindstyle args: ``<style>=<resonance>``."""
        style_part, sep, resonance_part = self._rest.partition("=")
        style_name = style_part.strip()
        resonance_name = resonance_part.strip()
        if not sep or not style_name or not resonance_name:
            msg = "Usage: motif bindstyle <style>=<resonance>."
            raise CommandError(msg)
        style = self._require_style(style_name)
        resonance = self._require_resonance(resonance_name)
        return {"style": style, "resonance": resonance}

    def _args_unbindstyle(self) -> dict[str, Any]:
        """Resolve unbindstyle args: the rest is the style name."""
        style_name = self._rest.strip()
        if not style_name:
            msg = "Usage: motif unbindstyle <style>."
            raise CommandError(msg)
        style = self._require_style(style_name)
        return {"style": style}
