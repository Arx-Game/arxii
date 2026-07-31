"""Natural key round-trip tests for CovenantRoleGiftGrant (#2847).

Every model that enters ``CONTENT_MODELS`` must have ``NaturalKeyMixin`` with a
stable, non-pk natural key. These tests prove the composite key
``[covenant_role, gift]`` round-trips through ``get_by_natural_key`` and
serializes with natural foreign keys (no raw pks).
"""

from django.core import serializers
from django.test import TestCase

from world.covenants.factories import CovenantRoleFactory
from world.covenants.models import CovenantRoleGiftGrant
from world.magic.factories import GiftFactory


class CovenantRoleGiftGrantNaturalKeyTests(TestCase):
    """CovenantRoleGiftGrant natural key round-trip for content pipeline (#2847)."""

    def test_natural_key_is_role_and_gift(self):
        role = CovenantRoleFactory()
        gift = GiftFactory()
        grant = CovenantRoleGiftGrant.objects.create(
            covenant_role=role, gift=gift, unlock_thread_level=0
        )
        self.assertEqual(grant.natural_key(), (role.natural_key()[0], gift.natural_key()[0]))

    def test_round_trip(self):
        role = CovenantRoleFactory()
        gift = GiftFactory()
        grant = CovenantRoleGiftGrant.objects.create(
            covenant_role=role, gift=gift, unlock_thread_level=3
        )
        resolved = CovenantRoleGiftGrant.objects.get_by_natural_key(*grant.natural_key())
        self.assertEqual(resolved.pk, grant.pk)

    def test_serializes_with_natural_keys(self):
        role = CovenantRoleFactory()
        gift = GiftFactory()
        grant = CovenantRoleGiftGrant.objects.create(
            covenant_role=role, gift=gift, unlock_thread_level=0
        )
        data = serializers.serialize(
            "json", [grant], use_natural_foreign_keys=True, use_natural_primary_keys=True
        )
        self.assertNotIn(f'"pk": {grant.pk}', data)
