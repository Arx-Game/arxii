"""Telnet command for the aura: being unsettled and the rite of settling (#4733, #5123, #5124).

``aura`` shows the aura in words, whether the character is unsettled, the reflections waiting
for the rite, the deeds not yet reflected on and the open chance to atone; ``aura settle
<offering>`` performs the rite of settling with the named carried item as its offering. Thin:
every rule lives in ``PerformSettlingRiteAction`` and ``world.magic.services``.

The rite spends only the item the player names, so a worn faceted cloak or a keepsake never
goes without being chosen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.definitions.drift_correction import PerformSettlingRiteAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance

_USAGE = "Usage: aura | aura settle <offering>"
_SETTLE = "settle"


def _own_sheet(caller: ObjectDB) -> CharacterSheet:
    sheet = caller.character_sheet
    if sheet is None:
        msg = "You don't have a character sheet."
        raise CommandError(msg)
    return sheet


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


class CmdAura(ArxCommand):
    """See your aura and the reflections waiting, or perform the rite of settling.

    Usage:
        aura
        aura settle <offering>

    Bare `aura` shows who you are in words, whether you are unsettled, the reflections you
    have written that wait for the rite, the deeds you have not reflected on yet, and your
    open chance to atone. `settle` performs the rite of settling: it takes the carried item
    you name as its offering, rolls once, and carries out every waiting reflection by what
    the roll earns. It needs at least one waiting reflection. Write a reflection with
    `pose/reflect` or `journal/reflect` (see `reflect`). While staff have not set the rite
    up, `aura` and `aura settle` say so.
    """

    key = "aura"
    locks = "cmd:all()"
    action = PerformSettlingRiteAction()

    def _execute(self) -> None:
        args = (self.args or "").strip()
        word, _, rest = args.partition(" ")
        sheet = _own_sheet(self.caller)
        if not args:
            self.msg(self._describe_aura(sheet))
        elif word.lower() == _SETTLE and rest.strip():
            result = self.action.run(actor=self.caller, **self._settle_args(sheet, rest))
            self.send_result(result.message or "", failed=not result.success)
        else:
            raise CommandError(_USAGE)

    def _settle_args(self, sheet: CharacterSheet, offering: str) -> dict[str, Any]:
        """The action's kwargs for ``settle <offering>``: the named carried item, which must
        count as the rite's offering for what is waiting."""
        from world.magic.exceptions import NoWaitingReflectionError  # noqa: PLC0415
        from world.magic.services.drift_correction import (  # noqa: PLC0415
            RITE_NOT_READY_MESSAGE,
            offerings_for,
            rite_is_ready,
            waiting_reflections,
        )

        reflections = waiting_reflections(sheet)
        if not reflections:
            raise CommandError(NoWaitingReflectionError.user_message)
        if not rite_is_ready():
            raise CommandError(RITE_NOT_READY_MESSAGE)
        carried = _carried(self.caller, sheet)
        chosen = _named_item(carried, offering)
        if chosen.pk not in {
            o.component.item.pk for o in offerings_for(sheet, reflections, carried)
        }:
            msg = f"{chosen.display_name} does not count as an offering for what you are settling."
            raise CommandError(msg)
        return {"components_provided": [chosen]}

    def _describe_aura(self, sheet: CharacterSheet) -> str:
        """The aura in words, the unsettled line, the waiting reflections and the open chance."""
        from world.magic.services.drift import (  # noqa: PLC0415
            drift_for,
            share_in_words,
            unsettled_line,
        )

        lines = []
        aura = sheet.aura_or_none
        shares = sorted(
            (share for share in (aura.cached_shares if aura else []) if share.percent > 0),
            key=lambda share: (-share.percent, share.affinity_id),
        )
        if shares:
            held = ", ".join(
                f"{share.affinity.name} ({share_in_words(share.percent)})" for share in shares
            )
            lines.append(f"Your aura: {held}.")
        else:
            lines.append("Your aura has not taken shape yet.")
        reading = drift_for(sheet)
        unsettled = unsettled_line(reading)
        if unsettled:
            lines.append(unsettled)
        lines.extend(self._describe_rite(sheet))
        return "\n".join(lines)

    def _describe_rite(self, sheet: CharacterSheet) -> list[str]:
        """The waiting reflections, the offerings that count, the deeds not yet reflected on."""
        from world.magic.services.reflection import reflectable_for  # noqa: PLC0415
        from world.magic.services.settling_preview import (  # noqa: PLC0415
            open_cap_line,
            settling_rite_reading,
        )

        reading = settling_rite_reading(sheet, _carried(self.caller, sheet))
        lines = []
        if reading.reflections:
            lines.append("Your reflections, waiting for the rite of settling:")
            for row in reading.reflections:
                where = f" ({row.where})" if row.where else ""
                lines.append(f"  {row.title}{where}. {row.effect_line}")
            if not reading.rite_ready:
                lines.append(reading.not_ready_message)
            elif reading.offerings:
                names = ", ".join(o.component.item.display_name for o in reading.offerings)
                lines.append(f"Offering you carry: {names}. Use |waura settle <offering>|n.")
            else:
                lines.append("You carry nothing that counts as the offering.")
        else:
            lines.append("You have no reflections waiting.")
        deeds = reflectable_for(sheet).deeds
        if deeds:
            lines.append("Deeds not yet reflected on:")
            lines.extend(f"  #{deed.grant.pk} {deed.label}" for deed in deeds)
        chance = open_cap_line(sheet)
        if chance:
            lines.append(chance)
        return lines
