from django.db import IntegrityError, transaction
from django.test import TestCase

from world.magic.factories import PortalAnchorFactory


class PortalAnchorFixtureKeyTests(TestCase):
    def test_fixture_key_defaults_to_none(self) -> None:
        anchor = PortalAnchorFactory()
        self.assertIsNone(anchor.fixture_key)

    def test_fixture_key_is_settable_and_unique(self) -> None:
        PortalAnchorFactory(fixture_key="arx-city/golden-hart-taproom/mirror")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PortalAnchorFactory(fixture_key="arx-city/golden-hart-taproom/mirror")
