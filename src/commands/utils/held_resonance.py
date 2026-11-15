"""Resolve a player-typed resonance name among the resonances the character holds (#5123).

One lookup and one refusal for every verb that names a resonance a character must hold:
``aura atone``, ``imbue ... resonance=`` and ``pull=<thread>:<resonance>``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance


def held_resonance(sheet: CharacterSheet, typed: str) -> Resonance:
    """The resonance named ``typed`` (any case) that ``sheet`` holds.

    Raises:
        CommandError: Nothing was named, or the character holds no resonance by that name;
            the refusal lists the resonances they do hold.
    """
    from world.magic.models import CharacterResonance  # noqa: PLC0415

    typed = typed.strip()
    if not typed:
        msg = "Name the resonance."
        raise CommandError(msg)
    row = (
        CharacterResonance.objects.filter(character_sheet=sheet, resonance__name__iexact=typed)
        .select_related("resonance__affinity")
        .first()
    )
    if row is not None:
        return row.resonance
    held = sorted(
        CharacterResonance.objects.filter(character_sheet=sheet).values_list(
            "resonance__name", flat=True
        )
    )
    suffix = f" Your resonances: {', '.join(held)}." if held else ""
    msg = f"You hold no resonance called '{typed}'.{suffix}"
    raise CommandError(msg)
