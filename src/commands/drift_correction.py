"""Telnet command for the drift correction rite (#4733, slice 4 of #4672).

``drift`` shows the open conversion offer, ``drift convert <from>=<into> [<amount>]
[with <item>]`` performs the rite and ``drift decline`` lets the offer go. Thin: every rule
lives in the actions and ``world.magic.services.drift_correction``.

An item that counts only by the facet or keepsake route is offered only when the player
names it with ``with``: the rite spends the first item that counts, and a worn faceted
cloak or a keepsake must never go without being chosen. An item that counts by the
material route (tied to the target resonance) is offered by default, even when it is
also a keepsake.
"""

from __future__ import annotations

import re
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
    from world.magic.types.drift import QualifyingComponent

_USAGE = (
    "Usage: drift | drift convert <from resonance>=<into resonance> [<amount>] "
    "[with <item>] | drift decline"
)
_NO_OFFER = "You have no open chance to correct drift."
_DECLINE = "decline"
_CONVERT = "convert"
# `` with <item>`` after the target; a bare trailing ``with`` is caught too, to refuse it.
_WITH = re.compile(r"\s+with(?:\s+|$)", re.IGNORECASE)


def _own_sheet(caller: ObjectDB) -> CharacterSheet:
    sheet = caller.character_sheet
    if sheet is None:
        msg = "You don't have a character sheet."
        raise CommandError(msg)
    return sheet


def _open_offer(sheet: CharacterSheet) -> DriftConversionOffer:
    """The character's open offer: one whose scene has not finished, wherever they stand.

    A character in two live scenes holds two offers (one per scene); the most recent one
    is used, the same order the web inbox lists them in.
    """
    from world.magic.models import DriftConversionOffer  # noqa: PLC0415

    offer = (
        DriftConversionOffer.objects.filter(
            character_sheet=sheet, scene__is_active=True, scene__date_finished__isnull=True
        )
        .order_by("-created_at", "-pk")
        .first()
    )
    if offer is None:
        raise CommandError(_NO_OFFER)
    return offer


def _require_rite_ready() -> None:
    """Refuse, the way the rite itself does, while staff have not set the rite up."""
    from world.magic.services.drift_correction import (  # noqa: PLC0415
        RITE_NOT_READY_MESSAGE,
        rite_is_ready,
    )

    if not rite_is_ready():
        raise CommandError(RITE_NOT_READY_MESSAGE)


def _carried(caller: ObjectDB, sheet: CharacterSheet) -> list[ItemInstance]:
    """The caller's own items among what they carry (as ``CmdRitual`` gathers them).

    Only items the caller's sheet holds: an unrelated object in their hands is not an
    offering, and would make the action refuse the whole list.
    """
    items = []
    for obj in caller.contents:
        instance = obj.item_instance_or_none
        if instance is not None and instance.holder_character_sheet_id == sheet.pk:
            items.append(instance)
    return items


def _named_item(carried: list[ItemInstance], typed: str) -> ItemInstance:
    """Resolve a typed item name among the caller's own carried items.

    An exact name (any case) wins; otherwise a name that contains the typed text. Nothing
    or several things matching is a ``CommandError`` naming them.
    """
    wanted = typed.strip().lower()
    exact = [item for item in carried if item.display_name.lower() == wanted]
    matches = exact or [item for item in carried if wanted in item.display_name.lower()]
    if not matches:
        msg = f"You carry nothing called '{typed.strip()}'."
        raise CommandError(msg)
    if len(matches) > 1:
        names = ", ".join(item.display_name for item in matches)
        msg = f"More than one thing you carry matches '{typed.strip()}': {names}. Name one."
        raise CommandError(msg)
    return matches[0]


def _offering(
    sheet: CharacterSheet, target: Resonance, carried: list[ItemInstance], named: str | None
) -> list[ItemInstance]:
    """The carried items to offer toward ``target``.

    With no name: everything carried except the items that count only as a facet or a
    keepsake, so a plain material is what the rite spends. With a name: that item, which
    must count toward ``target``, and nothing else that counts.
    """
    from world.magic.constants import ComponentMode  # noqa: PLC0415
    from world.magic.services.drift_correction import offered_components  # noqa: PLC0415

    qualifying = {q.item.pk: q.mode for q in offered_components(sheet, target, carried)}
    if named is None:
        return [
            item for item in carried if qualifying.get(item.pk) in (None, ComponentMode.MATERIAL)
        ]
    chosen = _named_item(carried, named)
    if chosen.pk not in qualifying:
        msg = f"{chosen.display_name} does not count as an offering for {target.name}."
        raise CommandError(msg)
    return [item for item in carried if item.pk not in qualifying] + [chosen]


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
        drift convert <from resonance>=<into resonance> [<amount>] [with <item>]
        drift decline

    Bare `drift` shows your open chance: what you may convert, at what rate, and the
    items you carry that count as the offering. `convert` performs the rite; with no
    amount it converts the most you may. It spends a plain material you carry; to spend
    a faceted item or a keepsake instead, name it with `with <item>`. `decline` lets the
    chance pass. While staff have not set the rite up, `drift` and `drift convert` say so.
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
            offer = _open_offer(sheet)
            _require_rite_ready()
            self.msg(self._describe_offer(offer, sheet))
        elif word.lower() == _DECLINE and not rest.strip():
            result = self.decline_action.run(actor=self.caller, offer=_open_offer(sheet))
            self.send_result(result.message or "", failed=not result.success)
        elif word.lower() == _CONVERT:
            result = self.action.run(actor=self.caller, **self.resolve_action_args())
            self.send_result(result.message or "", failed=not result.success)
        else:
            raise CommandError(_USAGE)

    def resolve_action_args(self) -> dict:
        """Parse ``convert <from>=<into> [<amount>] [with <item>]`` into the action's kwargs."""
        from world.magic.services.drift_correction import preview_conversion  # noqa: PLC0415

        _, _, rest = (self.args or "").strip().partition(" ")
        source_text, sep, target_part = rest.partition("=")
        if not sep or not source_text.strip() or not target_part.strip():
            raise CommandError(_USAGE)
        named: str | None = None
        split = _WITH.search(target_part)
        if split is not None:
            named = target_part[split.end() :].strip()
            target_part = target_part[: split.start()]
            if not named:
                raise CommandError(_USAGE)
        target_text, amount = _split_amount(target_part.strip())
        sheet = _own_sheet(self.caller)
        offer = _open_offer(sheet)
        _require_rite_ready()
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
            "components_provided": _offering(sheet, target, _carried(self.caller, sheet), named),
        }

    def _describe_offer(self, offer: DriftConversionOffer, sheet: CharacterSheet) -> str:
        from world.magic.constants import ComponentMode  # noqa: PLC0415
        from world.magic.services.drift_correction import offer_options  # noqa: PLC0415

        lines = [
            "You may correct drift. Use |wdrift convert <from>=<into> [<amount>] [with <item>]|n."
        ]
        for option in offer_options(offer, _carried(self.caller, sheet)):
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
            spent = [q for q in option.qualifying if q.mode == ComponentMode.MATERIAL]
            chosen = [q for q in option.qualifying if q.mode != ComponentMode.MATERIAL]
            if spent:
                lines.append(f"  Offering you carry: {_listed(spent)}.")
            if chosen:
                lines.append(f"  Spent only if named (|wwith <item>|n): {_listed(chosen)}.")
            if not option.qualifying:
                lines.append("  You carry nothing that counts as the offering.")
        return "\n".join(lines)


def _listed(components: list[QualifyingComponent]) -> str:
    return ", ".join(f"{q.item.display_name} ({q.mode.value})" for q in components)
