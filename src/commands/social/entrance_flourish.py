"""Telnet commands for the scene-entrance + entry-flourish loop (#1339)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.definitions.social import EntranceAction, ResolveFlourishOfferAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.magic.entry_flourish import PendingEntryFlourishOffer

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance


def _resolve_resonance(arg: str, sheet: CharacterSheet) -> Resonance:
    """Resolve a resonance by numeric ID or name from the character's claimed set.

    - If `arg` is numeric: try exact PK match first.
    - Otherwise (or if PK miss): case-insensitive name match.
    - On miss: list the character's claimed resonance names and raise CommandError.
    """
    from world.magic.models import CharacterResonance, Resonance  # noqa: PLC0415

    resonance: Resonance | None = None
    if arg.isdigit():
        resonance = Resonance.objects.filter(pk=int(arg)).first()
    if resonance is None:
        resonance = Resonance.objects.filter(name__iexact=arg).first()
    if resonance is not None:
        return resonance
    claimed_names = list(
        CharacterResonance.objects.filter(character_sheet=sheet).values_list(
            "resonance__name", flat=True
        )
    )
    if claimed_names:
        names_str = ", ".join(sorted(claimed_names))
        msg = f"No resonance '{arg}' found. Your claimed resonances: {names_str}"
        raise CommandError(msg)
    msg = "You have no claimed resonances."
    raise CommandError(msg)


class CmdEnter(ArxCommand):
    """Make a dramatic entrance into the scene.

    Usage: enter
    """

    key = "enter"
    locks = "cmd:all()"
    action = EntranceAction()

    def resolve_action_args(self) -> dict:
        return {}


class CmdFlourish(ArxCommand):
    """Broadcast a resonance from your pending entry-flourish offer.

    Usage: flourish <resonance name or id>
    """

    key = "flourish"
    locks = "cmd:all()"
    action = ResolveFlourishOfferAction()

    def resolve_action_args(self) -> dict:
        arg = self.require_args("Flourish with which resonance? Usage: flourish <name or id>")
        sheet = self.caller.sheet_data
        if sheet is None:
            msg = "You don't have a character sheet."
            raise CommandError(msg)
        offer = PendingEntryFlourishOffer.objects.filter(character_sheet=sheet).first()
        if offer is None:
            msg = "You have no pending flourish offer."
            raise CommandError(msg)
        resonance = _resolve_resonance(arg, sheet)
        return {"offer": offer, "resonance": resonance}
