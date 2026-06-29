"""Species-gift provisioning (#1580, ADR-0050). Called from CG finalize."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.species.models import SpeciesGiftGrant

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.gifts import CharacterGift


def _species_and_ancestors(species):
    """Return [species, parent, grandparent, ...] walking the parent chain."""
    chain, node = [], species
    while node is not None:
        chain.append(node)
        node = node.parent
    return chain


def provision_species_gifts(sheet: CharacterSheet, *, resonance=None) -> list[CharacterGift]:
    """Mint the species' Minor Gift(s) + latent GIFT thread + any drawback. Idempotent.

    ``resonance`` is the player's CG-chosen gift resonance (the same value the Major-gift
    block resolves). When None, falls back to each gift's first supported resonance.

    Called from finalize_magic_data after the Major-gift cantrip block so the species
    gift thread anchors to the same resonance as the player's Major-gift thread.
    """
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.magic.models.gifts import CharacterGift  # noqa: PLC0415
    from world.magic.specialization.services import provision_latent_gift_thread  # noqa: PLC0415

    if sheet.species_id is None:
        return []

    species_pks = [s.pk for s in _species_and_ancestors(sheet.species)]
    grants = SpeciesGiftGrant.objects.filter(species_id__in=species_pks).select_related(
        "gift", "drawback_condition"
    )
    minted: list[CharacterGift] = []
    for grant in grants:
        cg, _ = CharacterGift.objects.get_or_create(character=sheet, gift=grant.gift)
        minted.append(cg)
        res = resonance or grant.gift.resonances.first()
        if res is not None:
            provision_latent_gift_thread(sheet, grant.gift, resonance=res)
        if grant.drawback_condition_id is not None:
            apply_condition(sheet.character, grant.drawback_condition)
    return minted
