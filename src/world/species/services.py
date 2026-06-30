"""Species-gift provisioning (#1580, ADR-0050). Called from CG finalize."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.species.models import SpeciesGiftGrant

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.gifts import CharacterGift


def _species_and_ancestors(species):
    """Return [species, parent, grandparent, ...] walking the parent chain.

    Assumes an acyclic parent chain (data-hygiene invariant); the while is bounded.
    """
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
    from world.magic.specialization.services import grant_gift_to_character  # noqa: PLC0415

    if sheet.species_id is None:
        return []

    species_pks = [s.pk for s in _species_and_ancestors(sheet.species)]
    grants = SpeciesGiftGrant.objects.filter(species_id__in=species_pks).select_related(
        "gift", "drawback_condition"
    )
    minted: list[CharacterGift] = []
    for grant in grants:
        res = resonance or grant.gift.resonances.first()
        cg, _ = grant_gift_to_character(sheet, grant.gift, resonance=res)
        minted.append(cg)
        if grant.drawback_condition_id is not None:
            from world.conditions.models import ConditionInstance  # noqa: PLC0415

            already_applied = ConditionInstance.objects.filter(
                target=sheet.character,
                condition=grant.drawback_condition,
                resolved_at__isnull=True,
            ).exists()
            if not already_applied:
                apply_condition(sheet.character, grant.drawback_condition)
    return minted
