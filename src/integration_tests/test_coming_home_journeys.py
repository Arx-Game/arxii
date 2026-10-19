"""Journeys through ``home`` (#3657, tranche 9).

Ysmay makes a room her home and recalls to it. Each journey types what a player
types through the command handler and asserts what she was told and what the rows
hold.
"""

from __future__ import annotations

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.locations.constants import HolderType, LocationParentType, LocationRole
from world.locations.models import LocationTenancy
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class ComingHome(JourneyCase):
    """Ysmay has nowhere to recall to until a house she belongs to lets her settle in."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.ysmay.home = None
        self.ysmay.save()
        self.watch(self.hobb)

    def test_she_has_no_home_until_she_has_standing_somewhere(self) -> None:
        self.assertIn("You have no home set.", self.telnet(self.ysmay, "home"))
        self.assertIn("You have no standing in this room.", self.telnet(self.ysmay, "home/set"))
        self.assertIsNone(self.ysmay.home)

        # Her house rents the lodging; a member of the house may call it home.
        profile = RoomProfileFactory()
        lodging = profile.objectdb
        house = OrganizationFactory(name="House Vane")
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=profile,
            tenant_type=HolderType.ORGANIZATION,
            tenant_organization=house,
            kind=LocationRole.TENANT,
        )
        OrganizationMembershipFactory(
            organization=house, persona=self.ysmay.sheet_data.primary_persona
        )
        self.ysmay.location = lodging
        self.ysmay.save()
        self.assertIn("This is home now.", self.telnet(self.ysmay, "home/set"))
        self.assertEqual(self.ysmay.home, lodging)
        self.assertEqual(self.ysmay.sheet_data.current_residence_id, profile.pk)
        self.assertTrue(
            LocationTenancy.objects.filter(
                tenant_persona=self.ysmay.sheet_data.primary_persona, room_profile=profile
            ).exists()
        )

        # From the Lantern, `home` (and its alias) carries her back; the Lantern sees her go.
        self.ysmay.location = self.lantern
        self.ysmay.save()
        self.telnet(self.ysmay, "home")
        self.assertEqual(self.ysmay.location, lodging)
        self.ysmay.location = self.lantern
        self.ysmay.save()
        self.telnet(self.ysmay, "recall")
        self.assertEqual(self.ysmay.location, lodging)
        self.assertTold(self.hobb, "Ysmay")
