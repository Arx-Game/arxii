"""API contract tests for player channels (#3299).

Only the contract points no player journey reaches (``integration_tests/
test_channels_journeys.py`` covers the rest): the message list requires ``?channel=``,
and moderation is staff-only while another account's subscription is not found.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.channels.factories import ChannelMessageFactory, ChannelSubscriptionFactory
from world.channels.services import ensure_public_channel, provision_org_channel
from world.roster.factories import PlayerDataFactory, RosterTenureFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class ChannelApiContractTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.house = OrganizationFactory()
        cls.org_channel = provision_org_channel(cls.house)
        cls.public = ensure_public_channel()

        cls.player = PlayerDataFactory()
        cls.account = cls.player.account
        cls.member = RosterTenureFactory(player_data=cls.player, player_number=1)
        OrganizationMembershipFactory(
            organization=cls.house,
            persona=cls.member.roster_entry.character_sheet.primary_persona,
        )

        other = PlayerDataFactory()
        cls.outsider = other.account
        cls.foreign_subscription = ChannelSubscriptionFactory(
            account=cls.outsider, channel=cls.public
        )
        cls.org_message = ChannelMessageFactory(channel=cls.org_channel, author_tenure=cls.member)
        cls.staff = AccountFactory(is_staff=True)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def test_message_list_requires_channel(self) -> None:
        response = self.client.get("/api/channels/messages/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("channel", response.json())

    def test_moderation_is_staff_only_and_others_rows_are_not_found(self) -> None:
        message_url = f"/api/channels/messages/{self.org_message.pk}/"

        delete = self.client.delete(message_url)
        ban = self.client.post(f"{message_url}ban/", {}, format="json")
        patch = self.client.patch(
            f"/api/channels/subscriptions/{self.foreign_subscription.pk}/",
            {"muted": True},
            format="json",
        )

        self.assertEqual((delete.status_code, ban.status_code), (403, 403))
        self.assertEqual(patch.status_code, 404)
