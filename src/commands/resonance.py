"""Telnet ``resonance`` command (#2032) — spendable resonance balances + grant history.

Telnet players could earn and spend resonance (thread pulls, imbuing, sanctum weaving,
entry flourishes, pose endorsements, ...) but had no surface at all showing
``CharacterResonance.balance``. This is the read-only telnet face of the same data the
sheet's ``sheet/magic`` section (``_build_magic_resonances``) and the web audit ledger
(``ResonanceGrantViewSet`` / ``resonance_grant_history_for_sheet``) read — no parallel
query pipeline.

    resonance                    — your claimed resonances: balance + lifetime earned
    resonance history [<name>]   — your last 10 ResonanceGrant rows, newest first,
                                    optionally narrowed to one claimed resonance

Namespaced subverb (``resonance history``) mirrors ``CmdDurance``/``CmdSanctum`` — avoids
a bare top-level ``history`` key that could collide with exits/channels/aliases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

_HISTORY_SUBVERB = "history"
_HISTORY_LIMIT = 10
_NO_IDENTITY = "You have no active character to check resonance with."


class CmdResonance(ArxCommand):
    """Check your spendable resonance balances and grant history.

    Usage:
        resonance                  — list your claimed resonances (balance + lifetime earned)
        resonance history          — your last 10 resonance grants, newest first
        resonance history <name>   — same, narrowed to one claimed resonance
    """

    key = "resonance"
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        """Bare ``resonance`` shows balances; ``resonance history [<name>]`` shows the ledger."""
        try:
            sheet = self._viewer_sheet()
        except CommandError as err:
            self.caller.msg(str(err))
            return

        raw = (self.args or "").strip()
        if not raw:
            self._balances(sheet)
            return

        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        try:
            if subverb == _HISTORY_SUBVERB:
                self._history(sheet, rest)
            else:
                self.caller.msg(f"Unknown resonance action '{subverb}'. Try: history.")
        except CommandError as err:
            self.caller.msg(str(err))

    def _viewer_sheet(self) -> CharacterSheet:
        """The caller's own sheet. Raises ``CommandError`` if the caller has none."""
        sheet = self.caller.character_sheet
        if sheet is None:
            raise CommandError(_NO_IDENTITY)
        return sheet

    def _balances(self, sheet: CharacterSheet) -> None:
        """List the caller's claimed resonances with balance + lifetime earned."""
        from world.character_sheets.serializers import (  # noqa: PLC0415
            _build_magic_resonances,
        )

        entries = _build_magic_resonances(sheet.character)
        if not entries:
            self.caller.msg("You have not claimed any resonance yet.")
            return

        lines = ["|wYour resonance:|n"]
        lines.extend(
            f"  {entry['name']}: {entry['balance']} (lifetime {entry['lifetime_earned']})"
            for entry in entries
        )
        self.caller.msg("\n".join(lines))

    def _history(self, sheet: CharacterSheet, name: str) -> None:
        """Show the caller's last ``_HISTORY_LIMIT`` grants, newest first."""
        from world.magic.models import Resonance  # noqa: PLC0415
        from world.magic.services.gain import resonance_grant_history_for_sheet  # noqa: PLC0415

        resonance = None
        if name:
            try:
                resonance = Resonance.objects.get(name__iexact=name)
            except Resonance.DoesNotExist as exc:
                msg = f"No such resonance '{name}'."
                raise CommandError(msg) from exc

        grants = resonance_grant_history_for_sheet(sheet, resonance=resonance, limit=_HISTORY_LIMIT)
        if not grants:
            scope = f" for {resonance.name}" if resonance else ""
            self.caller.msg(f"No resonance grants{scope} yet.")
            return

        header = (
            f"|wYour resonance history ({resonance.name}):|n"
            if resonance
            else ("|wYour resonance history:|n")
        )
        lines = [header]
        lines.extend(
            f"  {grant.granted_at:%Y-%m-%d %H:%M} — {grant.resonance.name} "
            f"+{grant.amount} ({grant.get_source_display()})"
            for grant in grants
        )
        self.caller.msg("\n".join(lines))
