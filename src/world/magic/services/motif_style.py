"""Player-facing Motif style-binding services (#2030).

A player binds a staff-curated ``Style`` word to one of their *claimed*
resonances, creating the ``MotifResonanceStyle`` row the coherence walker
(``world.mechanics.services.passive_motif_style_bonuses``) and the peer style
endorsement grant (``world.magic.services.gain``) already read. Nothing else
creates ``Motif``/``MotifResonance`` rows in production, so ``bind`` lazily
establishes the substrate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.magic.exceptions import (
    StyleBindingCapExceeded,
    StyleNotBound,
    StyleResonanceUnclaimed,
)
from world.magic.models import (
    CharacterResonance,
    Motif,
    MotifResonance,
    MotifResonanceStyle,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import Style
    from world.magic.models import Resonance


def bind_motif_style(
    sheet: CharacterSheet, style: Style, resonance: Resonance
) -> MotifResonanceStyle:
    """Bind *style* to *resonance* on *sheet*'s motif, creating substrate lazily.

    Replace semantics: a style already bound to another of the character's
    resonances is moved. Binding a style where it already is is idempotent.
    Raises ``StyleResonanceUnclaimed`` when the character hasn't claimed the
    resonance and ``StyleBindingCapExceeded`` at the per-resonance cap.
    """
    if not CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).exists():
        raise StyleResonanceUnclaimed

    with transaction.atomic():
        motif, _ = Motif.objects.get_or_create(character=sheet)
        motif_resonance, _ = MotifResonance.objects.get_or_create(motif=motif, resonance=resonance)
        existing = MotifResonanceStyle.objects.filter(
            motif_resonance__motif=motif, style=style
        ).first()
        if existing is not None:
            if existing.motif_resonance_id == motif_resonance.pk:
                return existing
            existing.delete()
        try:
            return MotifResonanceStyle.objects.create(motif_resonance=motif_resonance, style=style)
        except ValidationError as exc:
            raise StyleBindingCapExceeded from exc


def unbind_motif_style(sheet: CharacterSheet, style: Style) -> None:
    """Remove *sheet*'s binding of *style*, or raise ``StyleNotBound``."""
    deleted, _ = MotifResonanceStyle.objects.filter(
        motif_resonance__motif__character=sheet, style=style
    ).delete()
    if not deleted:
        raise StyleNotBound


def motif_style_bindings(sheet: CharacterSheet) -> list[MotifResonanceStyle]:
    """Return the sheet's style bindings (empty when no Motif exists)."""
    return list(
        MotifResonanceStyle.objects.filter(motif_resonance__motif__character=sheet)
        .select_related("style", "motif_resonance__resonance")
        .order_by("motif_resonance__resonance__name", "style__name")
    )
