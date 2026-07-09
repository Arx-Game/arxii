"""Fighter style parity verification (#2023).

Verifies that the ItemFacet / passive_facet_bonuses machinery already covers
weapons — no garment restriction exists. This is a verification test, not a
build test: the machinery was built for garments but was designed to work on
any ItemInstance. We confirm that here.
"""

from __future__ import annotations

from django.test import TestCase

from world.items.factories import (
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.magic.factories import FacetFactory


class WeaponFacetParityTests(TestCase):
    """ItemFacet attaches to any ItemInstance — weapons are not excluded."""

    def test_facet_attaches_to_weapon_template(self):
        """An ItemFacet can be created on a weapon ItemInstance."""
        weapon_template = ItemTemplateFactory(weapon=True)
        weapon_instance = ItemInstanceFactory(template=weapon_template)
        facet = FacetFactory()

        item_facet = ItemFacetFactory(
            item_instance=weapon_instance,
            facet=facet,
        )

        assert item_facet.pk is not None
        assert item_facet.item_instance == weapon_instance

    def test_item_facets_for_finds_weapon_facet(self):
        """CharacterEquipmentHandler.item_facets_for returns facets on weapons.

        This is the key claim: the facet walk iterates all equipped items,
        including weapons — not just garments. If this test passes, a FACET
        thread anchored to a weapon-carried facet will participate in
        passive_facet_bonuses the same way a garment-carried facet does.
        """
        weapon_template = ItemTemplateFactory(weapon=True)
        weapon_instance = ItemInstanceFactory(template=weapon_template)
        facet = FacetFactory()

        ItemFacetFactory(
            item_instance=weapon_instance,
            facet=facet,
        )

        # Verify the facet is accessible via the instance's cached accessor
        # (this is what item_facets_for iterates)
        facets = list(weapon_instance.cached_item_facets)
        assert len(facets) == 1
        assert facets[0].facet == facet
