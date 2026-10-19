"""An item that has fed its wearer outfit resonance keeps that history (#4461).

``ResonanceGrant.outfit_item_facet`` is required non-null on every OUTFIT_TRICKLE
grant (``res_grant_outfit_trickle_shape``). Giving the item up or removing the facet
used to delete the ItemFacet and ask Postgres to SET NULL the grant's FK, which the
check constraint rejects. The history now survives: a given-up item is soft-destroyed
and a removed facet is stamped ``removed_at``, never deleted.

Tagged ``postgres``: the reproduction was written against, and is meant to run on, the
parity tier.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import ProtectedError
from django.test import TestCase, tag
from django.utils import timezone

from world.ceremonies.services import give_up_item
from world.items.models import ItemFacet, ItemInstance
from world.items.services.cleanup import purge_expired_soft_deleted_items
from world.items.services.facets import attach_facet_to_item, remove_facet_from_item
from world.magic.constants import GainSource
from world.magic.models import ResonanceGrant
from world.magic.services.gain import outfit_daily_trickle_for_character
from world.magic.tests.integration.test_outfit_resonance_trickle_pipeline import (
    _build_sheet_with_equipped_facet_item,
)
from world.worship.factories import WorshippedBeingFactory


@tag("postgres")
class OutfitGrantHistorySurvivesTests(TestCase):
    def setUp(self) -> None:
        self.sheet, self.resonance, self.facet, self.item_facet, _thread = (
            _build_sheet_with_equipped_facet_item()
        )
        self.item = self.item_facet.item_instance
        self.assertEqual(outfit_daily_trickle_for_character(self.sheet), 1)
        self.grant = ResonanceGrant.objects.get(source=GainSource.OUTFIT_TRICKLE)

    def _assert_history_intact(self) -> None:
        self.grant.refresh_from_db()
        self.assertEqual(self.grant.outfit_item_facet_id, self.item_facet.pk)
        self.assertTrue(ItemFacet.objects.filter(pk=self.item_facet.pk).exists())

    def test_giving_up_a_worn_item_soft_destroys_it_and_keeps_the_grant(self) -> None:
        being = WorshippedBeingFactory()

        give_up_item(self.item, being, facet=None, granted_by=self.sheet, reason="test")

        stored = ItemInstance.objects.get(pk=self.item.pk)
        self.assertIsNotNone(stored.destroyed_at)
        self._assert_history_intact()
        self.assertFalse(self.sheet.character.equipped_items.item_facets_for(self.facet))

    def test_removing_the_facet_stamps_it_and_keeps_the_grant(self) -> None:
        remove_facet_from_item(item_facet=self.item_facet)

        self.item_facet.refresh_from_db()
        self.assertIsNotNone(self.item_facet.removed_at)
        self._assert_history_intact()

    def test_a_removed_facet_stops_granting(self) -> None:
        remove_facet_from_item(item_facet=self.item_facet)
        before = ResonanceGrant.objects.count()

        self.assertEqual(outfit_daily_trickle_for_character(self.sheet), 0)

        self.assertEqual(ResonanceGrant.objects.count(), before)

    def test_a_removed_facet_stops_counting_against_capacity_and_can_be_reattached(self) -> None:
        template = self.item.template
        template.facet_capacity = 1
        template.save(update_fields=["facet_capacity"])
        remove_facet_from_item(item_facet=self.item_facet)
        self.assertEqual(self.item.cached_item_facets, [])

        again = attach_facet_to_item(
            crafter=None,
            item_instance=self.item,
            facet=self.facet,
            attachment_quality_tier=self.item_facet.attachment_quality_tier,
        )

        self.assertNotEqual(again.pk, self.item_facet.pk)
        self.assertEqual(outfit_daily_trickle_for_character(self.sheet), 1)

    def test_a_deleted_item_facet_with_grants_is_refused_not_nulled(self) -> None:
        """The database refuses the bare delete; nothing silently nulls the history."""
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.item_facet.delete()
        self._assert_history_intact()

    def test_purge_never_hard_deletes_an_item_whose_facets_have_grants(self) -> None:
        remove_facet_from_item(item_facet=self.item_facet)
        self.item.destroyed_at = timezone.now() - timedelta(days=3650)
        self.item.save(update_fields=["destroyed_at"])

        # No ProtectedError warning either: the eligibility filter skips the item, the
        # PROTECT foreign key is only the backstop behind it.
        with self.assertNoLogs("world.items.services.cleanup", level="WARNING"):
            purge_expired_soft_deleted_items()

        self.assertTrue(ItemInstance.objects.filter(pk=self.item.pk).exists())
        self._assert_history_intact()

    def test_merging_facets_hands_a_dropped_rows_grants_to_the_surviving_row(self) -> None:
        from world.items.factories import ItemFacetFactory
        from world.magic.factories import FacetFactory
        from world.magic.services.facets import merge_facets

        loser = FacetFactory()
        loser_row = ItemFacetFactory(item_instance=self.item, facet=loser)
        grant = ResonanceGrant.objects.create(
            character_sheet=self.sheet,
            resonance=self.resonance,
            amount=5,
            source=GainSource.OUTFIT_TRICKLE,
            outfit_item_facet=loser_row,
        )

        merge_facets(self.facet, [loser])

        grant.refresh_from_db()
        self.assertEqual(grant.outfit_item_facet_id, self.item_facet.pk)
        self.assertFalse(ItemFacet.objects.filter(pk=loser_row.pk).exists())

    def test_the_staff_merge_action_keeps_the_grant_history(self) -> None:
        from django.urls import reverse

        from evennia_extensions.factories import AccountFactory
        from world.items.factories import ItemFacetFactory
        from world.magic.factories import FacetFactory

        loser = FacetFactory(name="Silks")
        loser_row = ItemFacetFactory(item_instance=self.item, facet=loser)
        grant = ResonanceGrant.objects.create(
            character_sheet=self.sheet,
            resonance=self.resonance,
            amount=5,
            source=GainSource.OUTFIT_TRICKLE,
            outfit_item_facet=loser_row,
        )
        self.client.force_login(AccountFactory(is_staff=True, is_superuser=True))
        selected = {
            "action": "merge_into",
            "_selected_action": [self.facet.pk, loser.pk],
            "apply": "1",
            "winner": self.facet.pk,
        }

        response = self.client.post(reverse("admin:arxii_facet_changelist"), selected)

        self.assertEqual(response.status_code, 302)
        grant.refresh_from_db()
        self.assertEqual(grant.outfit_item_facet_id, self.item_facet.pk)
