"""Telnet command for the drift correction rite (#4733, slice 4 of #4672).

``drift`` shows the open conversion offer, ``drift convert <from>=<into> [<amount>]`` performs
the rite and ``drift decline`` lets the offer go. Thin: every rule lives in the actions and
``world.magic.services.drift_correction``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.definitions.drift_correction import (
    DeclineDriftCorrectionAction,
    PerformDriftCorrectionAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models import DriftConversionOffer, Resonance

_USAGE = "Usage: drift | drift convert <from resonance>=<into resonance> [<amount>] | drift decline"
_NO_OFFER = "You have no open chance to correct drift."
_DECLINE = "decline"
_CONVERT = "convert"


def _own_sheet(caller: ObjectDB) -> CharacterSheet:
    sheet = caller.sheet_data
    if sheet is None:
        msg = "You don't have a character sheet."
        raise CommandError(msg)
    return sheet


def _open_offer(caller: ObjectDB, sheet: CharacterSheet) -> DriftConversionOffer:
    """The caller's offer for the scene they stand in (a scene's offer lapses with it)."""
    from world.magic.models import DriftConversionOffer  # noqa: PLC0415
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    scene = None if caller.location is None else get_active_scene(caller.location)
    offer = (
        None
        if scene is None
        else DriftConversionOffer.objects.filter(character_sheet=sheet, scene=scene).first()
    )
    if offer is None:
        raise CommandError(_NO_OFFER)
    return offer


def _carried(caller: ObjectDB) -> list[ItemInstance]:
    """The ``ItemInstance`` rows the caller carries (as ``CmdRitual`` gathers them)."""
    items = []
    for obj in caller.contents:
        instance = obj.item_instance_or_none
        if instance is not None:
            items.append(instance)
    return items


def _own_resonance(sheet: CharacterSheet, typed: str) -> Resonance:
    """Resolve a player-typed resonance name among the resonances the character holds."""
    from world.magic.models import CharacterResonance  # noqa: PLC0415

    row = (
        CharacterResonance.objects.filter(character_sheet=sheet, resonance__name__iexact=typed)
        .select_related("resonance__affinity")
        .first()
    )
    if row is None:
        held = sorted(
            CharacterResonance.objects.filter(character_sheet=sheet).values_list(
                "resonance__name", flat=True
            )
        )
        suffix = f" Your resonances: {', '.join(held)}" if held else ""
        msg = f"You hold no resonance called '{typed}'.{suffix}"
        raise CommandError(msg)
    return row.resonance


def _split_amount(text: str) -> tuple[str, int | None]:
    """Split ``<resonance name> [<amount>]`` on a trailing whole number."""
    name, _, last = text.rpartition(" ")
    if name and last.isdigit():
        return name.strip(), int(last)
    return text.strip(), None


class CmdDrift(ArxCommand):
    """Correct drift: convert resonance held off your aura toward one you are growing.

    Usage:
        drift
        drift convert <from resonance>=<into resonance> [<amount>]
        drift decline

    Bare `drift` shows your open chance: what you may convert, at what rate, and the
    items you carry that count as the offering. `convert` performs the rite; with no
    amount it converts the most you may. `decline` lets the chance pass.
    """

    key = "drift"
    locks = "cmd:all()"
    action = PerformDriftCorrectionAction()
    decline_action = DeclineDriftCorrectionAction()

    def _execute(self) -> None:
        args = (self.args or "").strip()
        word, _, rest = args.partition(" ")
        sheet = _own_sheet(self.caller)
        if not args:
            self.msg(self._describe_offer(_open_offer(self.caller, sheet)))
        elif word.lower() == _DECLINE and not rest.strip():
            result = self.decline_action.run(
                actor=self.caller, offer=_open_offer(self.caller, sheet)
            )
            self.send_result(result.message or "", failed=not result.success)
        elif word.lower() == _CONVERT:
            result = self.action.run(actor=self.caller, **self.resolve_action_args())
            self.send_result(result.message or "", failed=not result.success)
        else:
            raise CommandError(_USAGE)

    def resolve_action_args(self) -> dict:
        """Parse ``convert <from>=<into> [<amount>]`` into the rite action's kwargs."""
        from world.magic.services.drift_correction import preview_conversion  # noqa: PLC0415

        _, _, rest = (self.args or "").strip().partition(" ")
        source_text, sep, target_part = rest.partition("=")
        if not sep or not source_text.strip() or not target_part.strip():
            raise CommandError(_USAGE)
        target_text, amount = _split_amount(target_part.strip())
        sheet = _own_sheet(self.caller)
        offer = _open_offer(self.caller, sheet)
        source = _own_resonance(sheet, source_text.strip())
        target = _own_resonance(sheet, target_text)
        if amount is None:
            option = next(
                (
                    o
                    for o in preview_conversion(offer, target).sources
                    if o.resonance_id == source.pk
                ),
                None,
            )
            if option is None or option.max_amount <= 0:
                msg = "That resonance is not drift you can convert toward that one."
                raise CommandError(msg)
            amount = option.max_amount
        return {
            "offer": offer,
            "source_resonance": source,
            "target_resonance": target,
            "amount": amount,
            "components_provided": _carried(self.caller),
        }

    def _describe_offer(self, offer: DriftConversionOffer) -> str:
        from world.magic.services.drift_correction import offer_options  # noqa: PLC0415

        lines = ["You may correct drift. Use |wdrift convert <from>=<into> [<amount>]|n."]
        for option in offer_options(offer, _carried(self.caller)):
            preview = option.preview
            lines.append(f"Toward {option.target_resonance.name}: up to {preview.cap_remaining}.")
            lines.extend(
                f"  From {source.resonance_name}: you hold {source.balance}, "
                f"{source.conversion_type} at {source.multiplier}. Converting "
                f"{source.max_amount} would give {source.projected_output}."
                for source in preview.sources
            )
            if not preview.sources:
                lines.append("  You hold no drift you can convert toward it.")
            if preview.focus_bonus > 0:
                lines.append(f"  Your focus adds {preview.focus_bonus} to the rite.")
            if option.qualifying:
                carried = ", ".join(
                    f"{q.item.display_name} ({q.mode.value})" for q in option.qualifying
                )
                lines.append(f"  Offering you carry: {carried}.")
            else:
                lines.append("  You carry nothing that counts as the offering.")
        return "\n".join(lines)
