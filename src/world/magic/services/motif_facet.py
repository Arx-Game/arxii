"""Player-facing Motif facet-binding services (#5021).

A player ties a staff-authored ``Facet`` (Wolf, Silk, Scythe) to one of their *claimed*
resonances, writing the ``MotifResonanceAssociation`` row four readers already use: the
facet gate on signature flourishes (``SignatureMotifBonus.qualifies_for``), the facet
route for ritual offerings (``services/drift.py``), the cast-narration fallback and the
sheet's Motif section. The sibling of ``services/motif_style.py``, with two differences
the owner ruled (#5021): one facet may sit on several of a character's resonances (no
move semantics), and a facet a signed flourish needs cannot be removed until that
flourish is cleared. Binding and unbinding are free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.magic.exceptions import (
    FacetBindingCapExceeded,
    FacetNeededByFlourish,
    FacetNotBound,
    StyleResonanceUnclaimed,
)
from world.magic.models import (
    CharacterResonance,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Facet, Resonance


def bind_motif_facet(
    sheet: CharacterSheet, facet: Facet, resonance: Resonance
) -> MotifResonanceAssociation:
    """Tie *facet* to *resonance* on *sheet*'s motif, creating the substrate lazily.

    Idempotent when the facet is already tied there. Raises ``StyleResonanceUnclaimed``
    when the character hasn't claimed the resonance and ``FacetBindingCapExceeded`` at the
    per-resonance cap (``MotifResonanceAssociation.MAX_PER_RESONANCE``).
    """
    if not CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).exists():
        raise StyleResonanceUnclaimed

    with transaction.atomic():
        motif, _ = Motif.objects.get_or_create(character=sheet)
        motif_resonance, _ = MotifResonance.objects.get_or_create(motif=motif, resonance=resonance)
        existing = MotifResonanceAssociation.objects.filter(
            motif_resonance=motif_resonance, facet=facet
        ).first()
        if existing is not None:
            return existing
        try:
            return MotifResonanceAssociation.objects.create(
                motif_resonance=motif_resonance, facet=facet
            )
        except ValidationError as exc:
            raise FacetBindingCapExceeded from exc


def unbind_motif_facet(sheet: CharacterSheet, facet: Facet, resonance: Resonance) -> None:
    """Remove *sheet*'s tie of *facet* to *resonance*.

    Raises ``FacetNotBound`` when there is no such tie, and ``FacetNeededByFlourish`` when
    it is the motif's last tie of that facet and a live thread is signed with a flourish
    gated on it (the flourish would stop qualifying).
    """
    association = MotifResonanceAssociation.objects.filter(
        motif_resonance__motif__character=sheet,
        motif_resonance__resonance=resonance,
        facet=facet,
    ).first()
    if association is None:
        raise FacetNotBound
    still_carried = (
        MotifResonanceAssociation.objects.filter(
            motif_resonance__motif__character=sheet, facet=facet
        )
        .exclude(pk=association.pk)
        .exists()
    )
    if not still_carried:
        _refuse_if_a_signed_flourish_needs(sheet, facet)
    association.delete()


def _refuse_if_a_signed_flourish_needs(sheet: CharacterSheet, facet: Facet) -> None:
    from world.magic.models import Thread  # noqa: PLC0415

    signed = (
        Thread.objects.filter(
            owner=sheet,
            retired_at__isnull=True,
            signature_bonus__required_facet=facet,
        )
        .select_related("signature_bonus")
        .first()
    )
    if signed is not None:
        raise FacetNeededByFlourish(signed.signature_bonus.name)


def tie_creation_facets(
    motif_resonance: MotifResonance, facet_ids: list[int]
) -> list[MotifResonanceAssociation]:
    """Tie a new character's creation facet picks to their gift resonance (CG finalize).

    ``motif_resonance`` is the one ``seed_motif_from_gift_resonance`` returned. The picks
    were validated on the draft (distinct, existing, at most the cap); a facet deleted
    since is skipped. Idempotent.
    """
    from world.magic.models import Facet  # noqa: PLC0415

    facets = Facet.objects.in_bulk(facet_ids)
    return [
        MotifResonanceAssociation.objects.get_or_create(
            motif_resonance=motif_resonance, facet=facets[facet_id]
        )[0]
        for facet_id in facet_ids
        if facet_id in facets
    ]


def motif_facet_bindings(sheet: CharacterSheet) -> list[MotifResonanceAssociation]:
    """Return the sheet's facet ties (empty when no Motif exists)."""
    return list(
        MotifResonanceAssociation.objects.filter(motif_resonance__motif__character=sheet)
        .select_related("facet", "motif_resonance__resonance")
        .order_by("motif_resonance__resonance__name", "facet__name")
    )
